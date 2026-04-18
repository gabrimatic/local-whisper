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
    var history: [HistoryEntry] = []
    var config: AppConfig = .defaultConfig
    var connectionState: ConnectionState = .connecting

    // Called whenever phase changes. Set by OverlayWindowController.
    var onPhaseChange: ((AppPhase) -> Void)?

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

            if phase != oldPhase {
                onPhaseChange?(phase)
            }

        case .historyUpdate(let entries):
            self.history = entries

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
        switch phase {
        case .idle:
            return statusText.isEmpty ? "Ready" : statusText
        case .recording:
            return String(format: "%.1f", durationSeconds) + "s"
        case .processing:
            return statusText.isEmpty ? "Processing…" : statusText
        case .done:
            return "Copied!"
        case .error:
            return statusText.isEmpty ? "Error" : statusText
        case .speaking:
            return statusText.isEmpty ? "Speaking…" : statusText
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
