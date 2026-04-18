import SwiftUI
import AppKit
import UserNotifications

// MARK: - Menu bar dropdown

struct MenuBarView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        // Status line + active config subtitle. When the service is unreachable
        // we surface that prominently so users don't think the UI is just stale.
        if appState.connectionState != .connected {
            Text(connectionLabel)
                .font(Theme.Typography.bodyEmphasized)
                .foregroundStyle(connectionTone)
                .accessibilityLabel("Local Whisper service: \(connectionLabel)")
        } else {
            Text(appState.menuStatusLabel)
                .font(Theme.Typography.bodyEmphasized)
                .foregroundStyle(statusColor)
                .accessibilityLabel(accessibilityStatusLabel)
        }

        Text(activeConfigSubtitle)
            .font(Theme.Typography.caption)
            .foregroundStyle(.secondary)

        Divider()

        // Engine + grammar pickers (live in their own grouped submenus)
        Picker(engineMenuTitle, selection: engineBinding) {
            Text("Qwen3-ASR (in-process)").tag("qwen3_asr")
            Text("WhisperKit (server)").tag("whisperkit")
        }

        Picker(grammarMenuTitle, selection: grammarBinding) {
            Text("Apple Intelligence").tag("apple_intelligence")
            Text("Ollama").tag("ollama")
            Text("LM Studio").tag("lm_studio")
            Divider()
            Text("Disabled").tag("none")
        }

        Toggle(replacementsMenuTitle, isOn: Binding(
            get: { appState.config.replacements.enabled },
            set: { newValue in
                appState.config.replacements.enabled = newValue
                appState.ipcClient?.sendConfigUpdate(section: "replacements", key: "enabled", value: newValue)
            }
        ))

        Divider()

        // Quick actions
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
        Menu(transcriptionsMenuTitle) {
            if appState.history.isEmpty {
                Text("No transcriptions yet")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(appState.history.prefix(min(20, appState.config.backup.historyLimit)))) { entry in
                    Button {
                        copyEntry(entry.text)
                    } label: {
                        Text("\(timeAgo(entry.timestamp))  \(truncated(entry.text, limit: 60))")
                    }
                }
            }
            Divider()
            Button("Open History Folder") {
                NSWorkspace.shared.open(URL(fileURLWithPath: AppDirectories.text))
            }
        }

        Menu(recordingsMenuTitle) {
            if appState.historyWithAudio.isEmpty {
                Text("No recordings yet")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(appState.historyWithAudio.prefix(min(20, appState.config.backup.historyLimit)))) { entry in
                    Button {
                        appState.ipcClient?.sendAction("reveal", id: entry.id)
                    } label: {
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

        // Settings
        SettingsLink {
            Text("Settings…")
        }
        .simultaneousGesture(TapGesture().onEnded {
            NSApp.activate(ignoringOtherApps: true)
        })
        .keyboardShortcut(",", modifiers: .command)

        // System actions submenu groups the destructive / admin items together.
        Menu("Service") {
            Button("Restart") {
                appState.ipcClient?.sendAction("restart")
            }
            .keyboardShortcut("r", modifiers: [.command, .shift])

            Button("Check for Updates") {
                appState.ipcClient?.sendAction("update")
            }
            .keyboardShortcut("u", modifiers: [.command, .shift])

            Divider()

            Button("Open Service Log") {
                let path = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/service.log")
                NSWorkspace.shared.open(URL(fileURLWithPath: path))
            }
        }

        Divider()

        Button("Quit Local Whisper") {
            appState.ipcClient?.sendAction("quit")
            NSApplication.shared.terminate(nil)
        }
        .keyboardShortcut("q", modifiers: .command)
    }

    // MARK: - Bindings

    private var grammarBinding: Binding<String> {
        Binding(
            get: { appState.config.grammar.enabled ? appState.config.grammar.backend : "none" },
            set: { newValue in
                if newValue == "none" {
                    appState.config.grammar.enabled = false
                } else {
                    appState.config.grammar.backend = newValue
                    appState.config.grammar.enabled = true
                }
                appState.ipcClient?.sendBackendSwitch(newValue)
            }
        )
    }

    private var engineBinding: Binding<String> {
        Binding(
            get: { appState.config.transcription.engine },
            set: { newValue in
                appState.config.transcription.engine = newValue
                appState.ipcClient?.sendEngineSwitch(newValue)
            }
        )
    }

    // MARK: - Labels

    private var statusColor: Color {
        switch appState.phase {
        case .idle: return .secondary
        case .recording: return .red
        case .processing: return .secondary
        case .done: return .green
        case .error: return .orange
        case .speaking: return .accentColor
        }
    }

    private var connectionLabel: String {
        switch appState.connectionState {
        case .connecting:   return "Connecting to service…"
        case .connected:    return appState.menuStatusLabel
        case .disconnected: return "Service not running"
        }
    }

    private var connectionTone: Color {
        switch appState.connectionState {
        case .connecting:   return .secondary
        case .connected:    return .primary
        case .disconnected: return .orange
        }
    }

    private var activeConfigSubtitle: String {
        let engineName = engineDisplayName(appState.config.transcription.engine)
        let backendName = grammarBackendName
        return "\(engineName) · \(backendName)"
    }

    private func engineDisplayName(_ id: String) -> String {
        switch id {
        case "qwen3_asr":  return "Qwen3-ASR"
        case "whisperkit": return "WhisperKit"
        default:           return id
        }
    }

    private var grammarBackendName: String {
        guard appState.config.grammar.enabled else { return "Grammar off" }
        switch appState.config.grammar.backend {
        case "apple_intelligence": return "Apple Intelligence"
        case "ollama":             return "Ollama"
        case "lm_studio":          return "LM Studio"
        default:                   return appState.config.grammar.backend
        }
    }

    private var engineMenuTitle: String {
        "Engine: \(engineDisplayName(appState.config.transcription.engine))"
    }

    private var grammarMenuTitle: String {
        guard appState.config.grammar.enabled else { return "Grammar: Disabled" }
        return "Grammar: \(grammarBackendName)"
    }

    private var replacementsMenuTitle: String {
        let count = appState.config.replacements.rules.count
        if count == 0 { return "Replacements" }
        return "Replacements (\(count) rule\(count == 1 ? "" : "s"))"
    }

    private var transcriptionsMenuTitle: String {
        let count = appState.history.count
        if count == 0 { return "Transcriptions" }
        return "Transcriptions (\(count))"
    }

    private var recordingsMenuTitle: String {
        let count = appState.historyWithAudio.count
        if count == 0 { return "Recordings" }
        return "Recordings (\(count))"
    }

    private var accessibilityStatusLabel: String {
        switch appState.phase {
        case .idle: return "Local Whisper: Ready"
        case .recording: return "Local Whisper: Recording, \(String(format: "%.0f", appState.durationSeconds)) seconds"
        case .processing: return "Local Whisper: Processing transcription"
        case .done: return "Local Whisper: Transcription copied"
        case .error: return "Local Whisper: Error"
        case .speaking: return "Local Whisper: Speaking"
        }
    }

    // MARK: - Actions

    private func copyEntry(_ text: String) {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)
        showCopiedNotification()
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
        URL(fileURLWithPath: path).lastPathComponent
    }

    private func truncated(_ s: String, limit: Int) -> String {
        let collapsed = s.replacingOccurrences(of: "\n", with: " ")
        if collapsed.count <= limit { return collapsed }
        return collapsed.prefix(limit).trimmingCharacters(in: .whitespaces) + "…"
    }
}
