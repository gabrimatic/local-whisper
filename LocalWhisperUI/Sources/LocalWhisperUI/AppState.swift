import Foundation
import SwiftUI

// MARK: - AppState

@Observable
@MainActor
final class AppState {
    var phase: AppPhase = .idle
    var durationSeconds: Double = 0.0
    var rmsLevel: Double = 0.0
    var lastText: String? = nil
    var statusText: String = "Starting..."
    var history: [HistoryEntry] = []
    var config: AppConfig = .defaultConfig

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
            self.phase = phase
            self.statusText = statusText ?? defaultStatusText(for: phase)
            if let text {
                self.lastText = text
            }
            self.rmsLevel = rms
            self.durationSeconds = duration

            if phase != oldPhase {
                onPhaseChange?(phase)
            }

        case .historyUpdate(let entries):
            self.history = entries
        }
    }

    private func defaultStatusText(for phase: AppPhase) -> String {
        switch phase {
        case .idle: return ""
        case .recording: return "Recording..."
        case .processing: return "Transcribing..."
        case .done: return "Done"
        case .error: return "Error"
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
            return statusText.isEmpty ? "Processing..." : statusText
        case .done:
            return "Copied!"
        case .error:
            return statusText.isEmpty ? "Error" : statusText
        }
    }

    var menuBarIconName: String {
        switch phase {
        case .idle: return "waveform"
        case .recording: return "waveform.badge.mic"
        case .processing: return "ellipsis"
        case .done: return "checkmark.circle"
        case .error: return "xmark.circle"
        }
    }

    var hasHistory: Bool {
        !history.isEmpty
    }

    var historyWithAudio: [HistoryEntry] {
        history.filter { $0.audioPath != nil }
    }
}
