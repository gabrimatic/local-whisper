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
    private var reconnectScheduled = false
    // Writes issued while the service is down/restarting queue here and
    // flush after reconnect — otherwise a toggle flipped during the ~3s
    // restart gap silently vanished and snapped back on the next snapshot.
    private var pendingOutgoing: [Data] = []
    private let maxPendingOutgoing = 128
    // Messages whose flush failed mid-flight. Completions fire FIFO, so
    // appending here preserves their original order; they are re-prepended
    // to pendingOutgoing as one batch on the next connect. (Per-completion
    // insert(at: 0) REVERSED the order of multiple failures.)
    private var failedFlush: [Data] = []
    // The flush waits for the first config_snapshot of the new connection:
    // flushing at .ready raced the server's connect-time snapshot, which
    // could arrive after the replayed edits and silently revert them.
    private var awaitingSnapshotForFlush = false
    private weak var appState: AppState?

    // Serial queue so message ordering (including connection-state changes)
    // survives even when multiple messages arrive within one receive
    // callback. `Task { @MainActor in … }` per message does NOT preserve
    // order; this continuation does.
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
        // Never leak a previous attempt: an orphaned live NWConnection whose
        // callbacks still fire was the source of dead-"Connected" states.
        connection?.cancel()

        let endpoint = NWEndpoint.unix(path: socketPath)
        let conn = NWConnection(to: endpoint, using: .tcp)
        connection = conn

        conn.stateUpdateHandler = { [weak self, weak conn] state in
            guard let self, let conn, conn === self.connection else { return }
            switch state {
            case .ready:
                self.reconnectDelay = 0.5
                self.buffer = Data()
                self.isReady = true
                if !self.failedFlush.isEmpty {
                    // Edits that failed mid-flush predate anything queued
                    // afterwards — restore chronological order.
                    self.pendingOutgoing = self.failedFlush + self.pendingOutgoing
                    self.failedFlush = []
                }
                self.awaitingSnapshotForFlush = !self.pendingOutgoing.isEmpty
                if self.awaitingSnapshotForFlush {
                    // Fallback: the server always opens with a config_snapshot,
                    // but if that one message is lost or undecodable the queued
                    // edits must not be held hostage forever.
                    self.queue.asyncAfter(deadline: .now() + 2.5) { [weak self, weak conn] in
                        guard let self, let conn, conn === self.connection else { return }
                        if self.awaitingSnapshotForFlush {
                            self.awaitingSnapshotForFlush = false
                            self.flushPendingOutgoing()
                        }
                    }
                }
                self.publishConnectionState(.connected)
                self.receiveNext(on: conn)
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

    private func receiveNext(on conn: NWConnection) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self, weak conn] data, _, isComplete, error in
            guard let self, let conn, conn === self.connection else { return }
            if let data {
                self.buffer.append(data)
                if self.buffer.count > maxBufferBytes {
                    ipcLogger.error("IPC buffer exceeded \(maxBufferBytes) bytes; dropping connection")
                    conn.cancel()
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
            self.receiveNext(on: conn)
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
            // First snapshot of a fresh connection: the server's baseline
            // state is in; now it's safe to replay queued edits on top.
            if case .configSnapshot = message, awaitingSnapshotForFlush {
                awaitingSnapshotForFlush = false
                flushPendingOutgoing()
            }
        } catch {
            ipcLogger.warning("IPC decode failed: \(error.localizedDescription)")
        }
    }

    private func scheduleReconnect() {
        // The receive-EOF path arrives here with the connection still
        // nominally .ready; cancelling below nils `connection` before the
        // .cancelled event fires, so the identity guard would swallow it.
        // Publish the disconnect explicitly (deduped by lastPublishedState).
        isReady = false
        publishConnectionState(.disconnected)

        // Single-flight: receive-completion and stateUpdateHandler both call
        // in here on a dying connection; two timers meant two connections.
        guard !reconnectScheduled else { return }
        reconnectScheduled = true

        let delay = reconnectDelay
        reconnectDelay = min(reconnectDelay * 2, maxReconnectDelay)
        connection?.cancel()
        connection = nil
        queue.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self else { return }
            self.reconnectScheduled = false
            guard self.isRunning else { return }
            self.connect()
        }
    }

    // MARK: - Sending

    /// `queueWhenDisconnected` must ONLY be set for idempotent config-style
    /// writes (config_update, backend_switch, replacement/dictation edits).
    /// One-shot actions (quit, restart, update, engine_switch, testers) are
    /// dropped while disconnected — replaying a stale "quit" minutes later
    /// against a freshly started service would be far worse than losing the
    /// click.
    func send<T: Encodable & Sendable>(_ message: T, queueWhenDisconnected: Bool = false) {
        queue.async { [weak self] in
            guard let self else { return }
            do {
                var data = try JSONEncoder().encode(message)
                data.append(0x0A)
                // The snapshot gate only defers config-style edits (ordering
                // matters for them); one-shot actions like quit or retry go
                // out immediately on a live connection.
                let deferForSnapshot = queueWhenDisconnected && self.awaitingSnapshotForFlush
                if self.isReady, !deferForSnapshot, let connection = self.connection {
                    connection.send(content: data, completion: .idempotent)
                } else if queueWhenDisconnected {
                    // Service down/restarting (or reconnected but the baseline
                    // snapshot hasn't landed yet): hold the write and replay
                    // it in order instead of silently dropping the edit.
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
            connection.send(content: data, completion: .contentProcessed { [weak self] error in
                guard error != nil, let self else { return }
                // Connection died mid-flush: collect the failures (FIFO
                // completions keep original order) for the next reconnect.
                self.queue.async {
                    if self.failedFlush.count < self.maxPendingOutgoing {
                        self.failedFlush.append(data)
                    }
                }
            })
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
        // Queued: switching the grammar backend is an idempotent config-style
        // write. Dropping it while the service restarts left the UI showing a
        // choice the next config_snapshot silently reverted (audit finding).
        send(BackendSwitchMessage(backend: backend), queueWhenDisconnected: true)
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

    private var lastPublishedState: ConnectionState?

    private func publishConnectionState(_ state: ConnectionState) {
        // Through the same ordered stream as wire messages — a detached Task
        // per transition could apply out of order and pin the UI on a stale
        // "Connecting…" after it had already connected.
        guard state != lastPublishedState else { return }
        lastPublishedState = state
        messageSink.yield(.connectionChanged(state))
    }
}
