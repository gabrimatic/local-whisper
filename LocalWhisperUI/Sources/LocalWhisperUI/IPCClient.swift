import Foundation
import Network
import os

// MARK: - IPCClient

private let ipcLogger = Logger(subsystem: "com.local-whisper", category: "ipc")
private let maxBufferBytes = 4 * 1024 * 1024

final class IPCClient: @unchecked Sendable {
    private let socketPath = AppDirectories.ipcSocket
    private let queue = DispatchQueue(label: "com.local-whisper.ipc-client")
    private var connection: NWConnection?
    private var reconnectDelay: Double = 0.5
    private let maxReconnectDelay: Double = 10.0
    private var buffer = Data()
    private var isRunning = false
    private var isReady = false
    // Writes issued while the service is down/restarting queue here and
    // flush on reconnect — otherwise a toggle flipped during the ~3s restart
    // gap silently vanished and snapped back on the next snapshot.
    private var pendingOutgoing: [Data] = []
    private let maxPendingOutgoing = 128
    private weak var appState: AppState?

    // Serial queue so state_update ordering survives even when multiple
    // messages arrive within one receive callback. `Task { @MainActor in … }`
    // per message does NOT preserve order; this continuation does.
    private let messageQueue: AsyncStream<IncomingMessage>
    private let messageSink: AsyncStream<IncomingMessage>.Continuation

    init(appState: AppState) {
        self.appState = appState
        let (stream, continuation) = AsyncStream.makeStream(of: IncomingMessage.self)
        self.messageQueue = stream
        self.messageSink = continuation
        // The consumer task must not retain `self`, otherwise the client
        // outlives the process despite the @unchecked Sendable dance.
        Task { @MainActor [weak appState] in
            for await message in stream {
                appState?.apply(message)
            }
        }
    }

    deinit {
        messageSink.finish()
    }

    func start() {
        queue.async { [weak self] in
            guard let self else { return }
            self.isRunning = true
            self.connect()
        }
    }

    func stop() {
        queue.async { [weak self] in
            guard let self else { return }
            self.isRunning = false
            self.connection?.cancel()
            self.connection = nil
        }
        messageSink.finish()
    }

    /// Blocks until the queue drains. Use only from applicationWillTerminate.
    func stopSync() {
        queue.sync {
            self.isRunning = false
            self.connection?.cancel()
            self.connection = nil
        }
        messageSink.finish()
    }

    private func connect() {
        let endpoint = NWEndpoint.unix(path: socketPath)
        let conn = NWConnection(to: endpoint, using: .tcp)
        connection = conn

        conn.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                self.reconnectDelay = 0.5
                self.buffer = Data()
                self.isReady = true
                self.publishConnectionState(.connected)
                self.flushPendingOutgoing()
                self.receiveNext()
            case .failed, .cancelled:
                self.isReady = false
                self.publishConnectionState(.disconnected)
                if self.isRunning {
                    self.scheduleReconnect()
                }
            case .preparing, .setup, .waiting:
                self.isReady = false
                self.publishConnectionState(.connecting)
            default:
                break
            }
        }

        conn.start(queue: queue)
    }

    private func receiveNext() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            if let data {
                self.buffer.append(data)
                if self.buffer.count > maxBufferBytes {
                    ipcLogger.error("IPC buffer exceeded \(maxBufferBytes) bytes; dropping connection")
                    self.connection?.cancel()
                    return
                }
                self.processBuffer()
            }
            if isComplete || error != nil {
                if self.isRunning {
                    self.scheduleReconnect()
                }
                return
            }
            self.receiveNext()
        }
    }

    private func processBuffer() {
        while let newlineRange = buffer.range(of: Data([0x0A])) {
            let lineData = buffer.subdata(in: buffer.startIndex..<newlineRange.lowerBound)
            buffer.removeSubrange(buffer.startIndex...newlineRange.lowerBound)
            if !lineData.isEmpty {
                handleLine(lineData)
            }
        }
    }

    private func handleLine(_ data: Data) {
        do {
            let message = try decodeIncomingMessage(data)
            messageSink.yield(message)
        } catch {
            ipcLogger.warning("IPC decode failed: \(error.localizedDescription)")
        }
    }

    private func scheduleReconnect() {
        let delay = reconnectDelay
        reconnectDelay = min(reconnectDelay * 2, maxReconnectDelay)
        connection?.cancel()
        connection = nil
        queue.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self, self.isRunning else { return }
            self.connect()
        }
    }

    // MARK: - Sending

    /// `queueWhenDisconnected` must ONLY be set for idempotent config-style
    /// writes (config_update, replacement/dictation edits). One-shot actions
    /// (quit, restart, update, engine_switch, testers) are dropped while
    /// disconnected — replaying a stale "quit" minutes later against a
    /// freshly started service would be far worse than losing the click.
    func send<T: Encodable & Sendable>(_ message: T, queueWhenDisconnected: Bool = false) {
        queue.async { [weak self] in
            guard let self else { return }
            do {
                var data = try JSONEncoder().encode(message)
                data.append(0x0A)
                if self.isReady, let connection = self.connection {
                    connection.send(content: data, completion: .idempotent)
                } else if queueWhenDisconnected {
                    // Service down/restarting: hold the write and replay it
                    // on reconnect instead of silently dropping the edit.
                    if self.pendingOutgoing.count < self.maxPendingOutgoing {
                        self.pendingOutgoing.append(data)
                    } else {
                        ipcLogger.error("IPC outgoing queue full; dropping message")
                    }
                } else {
                    ipcLogger.warning("IPC not connected; dropping one-shot message")
                }
            } catch {
                ipcLogger.error("IPC encode failed: \(error.localizedDescription)")
            }
        }
    }

    private func flushPendingOutgoing() {
        guard !pendingOutgoing.isEmpty, let connection else { return }
        let queued = pendingOutgoing
        pendingOutgoing = []
        ipcLogger.info("Flushing \(queued.count) queued IPC message(s) after reconnect")
        for data in queued {
            connection.send(content: data, completion: .idempotent)
        }
    }

    func sendAction(_ action: String, id: String? = nil) {
        send(ActionMessage(action: action, id: id))
    }

    func sendEngineSwitch(_ engine: String) {
        send(EngineSwitchMessage(engine: engine))
    }

    func sendEngineRemoveCache(_ engine: String) {
        send(EngineRemoveCacheMessage(engine: engine))
    }

    func sendBackendSwitch(_ backend: String) {
        send(BackendSwitchMessage(backend: backend))
    }

    func sendConfigUpdate<T: Encodable>(section: String, key: String, value: T) {
        send(ConfigUpdateMessage(section: section, key: key, value: AnyEncodable(value)), queueWhenDisconnected: true)
    }

    func sendReplacementAdd(spoken: String, replacement: String) {
        send(ReplacementAddMessage(spoken: spoken, replacement: replacement), queueWhenDisconnected: true)
    }

    func sendReplacementRemove(spoken: String) {
        send(ReplacementRemoveMessage(spoken: spoken), queueWhenDisconnected: true)
    }

    func sendReplacementImport(rules: [String: String]) {
        send(ReplacementImportMessage(rules: rules), queueWhenDisconnected: true)
    }

    func sendReplacementTest(text: String) {
        send(ReplacementTestMessage(text: text))
    }

    func sendDictationCommandAdd(spoken: String, replacement: String) {
        send(DictationCommandAddMessage(spoken: spoken, replacement: replacement), queueWhenDisconnected: true)
    }

    func sendDictationCommandRemove(spoken: String) {
        send(DictationCommandRemoveMessage(spoken: spoken), queueWhenDisconnected: true)
    }

    func sendDictationTest(text: String) {
        send(DictationTestMessage(text: text))
    }

    // MARK: - Connection state plumbing

    private func publishConnectionState(_ state: ConnectionState) {
        Task { @MainActor [weak appState] in
            appState?.connectionState = state
        }
    }
}
