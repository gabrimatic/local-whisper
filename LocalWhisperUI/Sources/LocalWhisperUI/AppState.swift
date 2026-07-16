import Foundation
import SwiftUI
import UserNotifications

// MARK: - AppState

@Observable
@MainActor
final class AppState {
    var phase: AppPhase = .idle
    var durationSeconds: Double = 0.0
    var rmsLevel: Double = 0.0
    var lastText: String? = nil
    var statusText: String = "Starting…"
    // Latched so the idle state_update (sent ~1.5s after done) can't wipe "Copied!"/"Pasted!".
    var doneStatusText: String = ""
    // Latched so errors (e.g. "Update failed: git pull error") stay visible
    // in the menu until the user does something that produces new activity.
    var latchedErrorText: String = ""
    var history: [HistoryEntry] = []
    var config: AppConfig = .defaultConfig
    var engines: [EngineStatus] = []
    var connectionState: ConnectionState = .connecting
    // Keyed by target id: "parakeet_v3", "qwen3_asr", "kokoro_tts". Progress
    // rows listen on this so the bar sits under the section that triggered
    // the download, not in the overlay.
    var downloadStates: [String: DownloadProgress] = [:]
    // Live tester results (Vocabulary / Voice panels).
    var replacementTestResult: PipelineTestResult?
    var dictationTestResult: PipelineTestResult?

    // Called whenever phase changes. Set by OverlayWindowController.
    var onPhaseChange: ((AppPhase) -> Void)?
    // Called for every state_update snapshot, including repeated recording ticks.
    var onStateUpdate: ((AppPhase) -> Void)?

    private(set) var ipcClient: IPCClient?

    init() {}

    func setupIPC() {
        let client = IPCClient(appState: self)
        ipcClient = client
    }

    // MARK: - Incoming message handling

    func apply(_ message: IncomingMessage) {
        switch message {
        case .configSnapshot(let config):
            self.config = config

        case .stateUpdate(let phase, let duration, let rms, let text, let statusText):
            let oldPhase = self.phase
            let normalizedStatus = (statusText ?? defaultStatusText(for: phase)).normalizingEllipsis
            self.phase = phase
            self.statusText = normalizedStatus
            if let text {
                self.lastText = text
            }
            self.rmsLevel = rms
            self.durationSeconds = duration

            switch phase {
            case .done:
                self.doneStatusText = normalizedStatus
            default:
                self.doneStatusText = ""
            }

            switch phase {
            case .error:
                self.latchedErrorText = normalizedStatus
            case .recording, .processing, .speaking, .done:
                // Any new activity — including a successful result — replaces
                // the stale error. (Done used to preserve it, so "Copied!"
                // flipped back to an old failure message afterwards.)
                self.latchedErrorText = ""
            case .idle:
                // Preserve the latched error through the trailing idle tick.
                break
            }

            if phase != oldPhase {
                onPhaseChange?(phase)
            }
            onStateUpdate?(phase)

        case .historyUpdate(let entries):
            self.history = entries

        case .enginesStatus(let engines):
            // Stable order: active first, then registry order.
            self.engines = engines.sorted { a, b in
                if a.active != b.active { return a.active && !b.active }
                return a.id < b.id
            }

        case .downloadProgress(let progress):
            // Keep terminal states ("ready"/"canceled") around briefly so the
            // UI can flash the outcome. Before removing, verify the stored
            // snapshot is still the same terminal one — a NEW download for
            // the same target started within the delay must not have its
            // fresh progress bar deleted by this stale cleanup task.
            downloadStates[progress.target] = progress
            if progress.phase == "ready" || progress.phase == "canceled" {
                let terminalPhase = progress.phase
                Task { @MainActor [weak self] in
                    try? await Task.sleep(nanoseconds: 1_500_000_000)
                    guard let self else { return }
                    if self.downloadStates[progress.target]?.phase == terminalPhase {
                        self.downloadStates.removeValue(forKey: progress.target)
                    }
                }
            }

        case .replacementTestResult(let result):
            self.replacementTestResult = result

        case .dictationTestResult(let result):
            self.dictationTestResult = result

        case .connectionChanged(let state):
            self.connectionState = state
            switch state {
            case .connected:
                // A fresh connection starts clean: errors latched against the
                // previous service instance are no longer meaningful.
                self.latchedErrorText = ""
            case .disconnected:
                // A download that was in flight when the service died will
                // never send another progress message — drop the frozen bars
                // so engine cards don't show a dead "Downloading" state.
                for (target, progress) in self.downloadStates
                where progress.phase == "downloading" || progress.phase == "preparing" || progress.phase == "warming" {
                    self.downloadStates.removeValue(forKey: target)
                }
            case .connecting:
                break
            }

        case .notification(let title, let body):
            let content = UNMutableNotificationContent()
            content.title = title.normalizingEllipsis
            content.body = body.normalizingEllipsis
            content.sound = .default
            let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
            UNUserNotificationCenter.current().add(request)
        }
    }

    private func defaultStatusText(for phase: AppPhase) -> String {
        switch phase {
        case .idle: return ""
        case .recording: return "Recording…"
        case .processing: return "Transcribing…"
        case .done: return "Done"
        case .error: return "Error"
        case .speaking: return "Speaking…"
        }
    }

    // MARK: - Computed

    var menuStatusLabel: String {
        // Intentionally stable strings during recording/processing. If this
        // label changed per state_update (10+/sec during recording), the whole
        // MenuBarView would re-render on every tick, which destroys hover
        // state: the cursor "jumps" and submenus refuse to open. Live duration
        // lives on the overlay pill, not here.
        switch phase {
        case .idle:
            if !latchedErrorText.isEmpty { return latchedErrorText }
            return statusText.isEmpty ? "Ready" : statusText
        case .recording:
            return "Recording…"
        case .processing:
            return "Transcribing…"
        case .done:
            // Shortcut transforms send "Replaced! (+12 chars)", paste-mode
            // dictation sends "Pasted!" — show what actually happened
            // instead of claiming "Copied!" for everything.
            return doneStatusText.isEmpty ? "Copied!" : doneStatusText
        case .error:
            let text = latchedErrorText.isEmpty ? statusText : latchedErrorText
            return text.isEmpty ? "Error" : text
        case .speaking:
            return "Speaking…"
        }
    }

    var menuBarIconName: String {
        switch phase {
        case .idle: return "waveform"
        case .recording: return "waveform.badge.mic"
        case .processing: return "ellipsis"
        case .done: return "checkmark.circle.fill"
        case .error: return "exclamationmark.triangle.fill"
        case .speaking: return "speaker.wave.2.fill"
        }
    }

    var hasHistory: Bool {
        !history.isEmpty
    }

    var historyWithAudio: [HistoryEntry] {
        history.filter { $0.audioPath != nil }
    }
}

// MARK: - Ellipsis normalization

private extension String {
    /// Three-dot ellipses from Python status strings get mapped to the single
    /// Unicode ellipsis so everything the user sees uses one glyph.
    var normalizingEllipsis: String {
        replacingOccurrences(of: "...", with: "…")
    }
}

// MARK: - Connection state

enum ConnectionState: Sendable {
    case connecting
    case connected
    case disconnected

    var label: String {
        switch self {
        case .connecting:   return "Connecting…"
        case .connected:    return "Connected"
        case .disconnected: return "Not running"
        }
    }

    @MainActor
    var tone: Theme.Tone {
        switch self {
        case .connecting:   return .neutral
        case .connected:    return .success
        case .disconnected: return .warning
        }
    }
}
