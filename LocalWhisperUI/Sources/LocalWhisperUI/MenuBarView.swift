import SwiftUI
import AppKit
import UserNotifications

// MARK: - Menu bar content

struct MenuBarView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        // Status row
        Text(appState.menuStatusLabel)
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(statusColor)
            .accessibilityLabel(accessibilityStatusLabel)

        Divider()

        // Grammar submenu — Picker renders native radio checkmarks automatically
        Picker(grammarMenuTitle, selection: grammarBinding) {
            Text("Apple Intelligence").tag("apple_intelligence")
            Text("Ollama").tag("ollama")
            Text("LM Studio").tag("lm_studio")
            Divider()
            Text("Disabled").tag("")
        }

        Divider()

        Button("Retry Last") {
            appState.ipcClient?.sendAction("retry")
        }
        .disabled(!appState.hasHistory)
        .keyboardShortcut("r", modifiers: .command)

        Button("Copy Last") {
            appState.ipcClient?.sendAction("copy")
        }
        .disabled(!appState.hasHistory)
        .keyboardShortcut("c", modifiers: [.command, .shift])

        Divider()

        // Transcriptions submenu
        Menu("Transcriptions") {
            if appState.history.isEmpty {
                Text("No transcriptions yet")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(appState.history.prefix(min(20, appState.config.backup.historyLimit)))) { entry in
                    Button(action: {
                        let pasteboard = NSPasteboard.general
                        pasteboard.clearContents()
                        pasteboard.setString(entry.text, forType: .string)
                        showCopiedNotification()
                    }) {
                        Text("\(timeAgo(entry.timestamp))  \(String(entry.text.prefix(50)))")
                    }
                }
            }
            Divider()
            Button("Open History Folder") {
                NSWorkspace.shared.open(URL(fileURLWithPath: AppDirectories.text))
            }
        }

        // Recordings submenu
        Menu("Recordings") {
            if appState.historyWithAudio.isEmpty {
                Text("No recordings yet")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(appState.historyWithAudio.prefix(min(20, appState.config.backup.historyLimit)))) { entry in
                    Button(action: {
                        appState.ipcClient?.sendAction("reveal", id: entry.id)
                    }) {
                        Text("\(timeAgo(entry.timestamp))  \(audioFilename(entry.audioPath ?? ""))")
                    }
                }
            }
            Divider()
            Button("Open Audio Folder") {
                NSWorkspace.shared.open(URL(fileURLWithPath: AppDirectories.audio))
            }
        }

        Divider()

        SettingsLink {
            Text("Settings...")
        }
        .simultaneousGesture(TapGesture().onEnded {
            NSApp.activate(ignoringOtherApps: true)
        })
        .keyboardShortcut(",", modifiers: .command)

        Button("Restart Service") {
            appState.ipcClient?.sendAction("restart")
        }
        .keyboardShortcut("r", modifiers: [.command, .shift])

        Button("Check for Updates") {
            appState.ipcClient?.sendAction("update")
        }
        .keyboardShortcut("u", modifiers: [.command, .shift])

        Divider()

        Button("Quit") {
            appState.ipcClient?.sendAction("quit")
            NSApplication.shared.terminate(nil)
        }
        .keyboardShortcut("q", modifiers: .command)
    }

    // MARK: - Grammar binding

    /// Unified selection: backend id when enabled, "" when disabled.
    private var grammarBinding: Binding<String> {
        Binding(
            get: {
                appState.config.grammar.enabled ? appState.config.grammar.backend : ""
            },
            set: { newValue in
                if newValue.isEmpty {
                    appState.config.grammar.enabled = false
                    appState.ipcClient?.sendBackendSwitch("none")
                } else {
                    appState.config.grammar.backend = newValue
                    appState.config.grammar.enabled = true
                    appState.ipcClient?.sendBackendSwitch(newValue)
                }
            }
        )
    }

    // MARK: - Helpers

    private var statusColor: Color {
        switch appState.phase {
        case .idle: return .secondary
        case .recording: return .primary
        case .processing: return .secondary
        case .done: return .green
        case .error: return .orange
        }
    }

    private var grammarMenuTitle: String {
        guard appState.config.grammar.enabled else { return "Grammar: Disabled" }
        switch appState.config.grammar.backend {
        case "apple_intelligence": return "Grammar: Apple Intelligence"
        case "ollama": return "Grammar: Ollama"
        case "lm_studio": return "Grammar: LM Studio"
        default: return "Grammar"
        }
    }

    private var accessibilityStatusLabel: String {
        switch appState.phase {
        case .idle: return "Local Whisper: Ready"
        case .recording: return "Local Whisper: Recording, \(String(format: "%.0f", appState.durationSeconds)) seconds"
        case .processing: return "Local Whisper: Processing transcription"
        case .done: return "Local Whisper: Transcription copied"
        case .error: return "Local Whisper: Error"
        }
    }

    private func showCopiedNotification() {
        let content = UNMutableNotificationContent()
        content.title = "Copied"
        content.body = "Transcription copied to clipboard."
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    private static let dateFormatter: DateFormatter = {
        let fmt = DateFormatter()
        fmt.dateFormat = "MMM d"
        return fmt
    }()

    private func timeAgo(_ timestamp: Double) -> String {
        let elapsed = Date().timeIntervalSince1970 - timestamp
        if elapsed < 60 { return "\(Int(elapsed))s ago" }
        if elapsed < 3600 { return "\(Int(elapsed / 60))m ago" }
        if elapsed < 86400 { return "\(Int(elapsed / 3600))h ago" }
        if elapsed < 172800 { return "Yesterday" }
        if elapsed < 2592000 { return "\(Int(elapsed / 86400))d ago" }
        let date = Date(timeIntervalSince1970: timestamp)
        return Self.dateFormatter.string(from: date)
    }

    private func audioFilename(_ path: String) -> String {
        return URL(fileURLWithPath: path).lastPathComponent
    }
}
