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
                self.receiveNext()
            case .failed, .cancelled:
                if self.isRunning {
                    self.scheduleReconnect()
                }
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

    func send<T: Encodable & Sendable>(_ message: T) {
        queue.async { [weak self] in
            guard let self else { return }
            do {
                var data = try JSONEncoder().encode(message)
                data.append(0x0A)
                self.connection?.send(content: data, completion: .idempotent)
            } catch {
                ipcLogger.error("IPC encode failed: \(error.localizedDescription)")
            }
        }
    }

    func sendAction(_ action: String, id: String? = nil) {
        send(ActionMessage(action: action, id: id))
    }

    func sendEngineSwitch(_ engine: String) {
        send(EngineSwitchMessage(engine: engine))
    }

    func sendBackendSwitch(_ backend: String) {
        send(BackendSwitchMessage(backend: backend))
    }

    func sendConfigUpdate<T: Encodable>(section: String, key: String, value: T) {
        send(ConfigUpdateMessage(section: section, key: key, value: AnyEncodable(value)))
    }

    func sendReplacementAdd(spoken: String, replacement: String) {
        send(ReplacementAddMessage(spoken: spoken, replacement: replacement))
    }

    func sendReplacementRemove(spoken: String) {
        send(ReplacementRemoveMessage(spoken: spoken))
    }
}
