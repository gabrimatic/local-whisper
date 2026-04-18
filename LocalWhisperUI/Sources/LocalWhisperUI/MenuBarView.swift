import SwiftUI
import AppKit
import UserNotifications

// MARK: - Menu bar dropdown

struct MenuBarView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        // === STATUS ===
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

        // === RECENT ACTIONS ===
        // Operating on the most recent transcription. Plain-English labels so
        // there's no ambiguity about what "last" refers to.
        Button("Retry last transcription") {
            appState.ipcClient?.sendAction("retry")
        }
        .disabled(!appState.hasHistory)
        .keyboardShortcut("r", modifiers: .command)

        Button("Copy last transcription") {
            appState.ipcClient?.sendAction("copy")
        }
        .disabled(!appState.hasHistory)
        .keyboardShortcut("c", modifiers: [.command, .shift])

        Divider()

        // === DICTATION (voice -> text) ===
        // All the pieces that turn a recording into clean text.
        Picker(transcriptionModelMenuTitle, selection: engineBinding) {
            Text("Parakeet-TDT v3 (multilingual)").tag("parakeet_v3")
            Text("Qwen3-ASR (English only)").tag("qwen3_asr")
            Text("WhisperKit (local server)").tag("whisperkit")
        }
        .help("The AI model that converts your speech into text.")

        Picker(grammarMenuTitle, selection: grammarBinding) {
            Text("Apple Intelligence").tag("apple_intelligence")
            Text("Ollama").tag("ollama")
            Text("LM Studio").tag("lm_studio")
            Divider()
            Text("Off").tag("none")
        }
        .help("Cleans up punctuation, capitalization, and obvious mistakes after transcription.")

        Toggle(replacementsMenuTitle, isOn: Binding(
            get: { appState.config.replacements.enabled },
            set: { newValue in
                appState.config.replacements.enabled = newValue
                appState.ipcClient?.sendConfigUpdate(section: "replacements", key: "enabled", value: newValue)
            }
        ))
        .help("Rewrites specific words after transcription (for example, \"open ai\" -> \"OpenAI\").")

        Divider()

        // === READ ALOUD (text -> voice) ===
        // A separate feature from dictation: it outputs voice instead of
        // producing text. Given its own section so users don't confuse it with
        // the transcription pipeline above.
        Toggle(readAloudMenuTitle, isOn: Binding(
            get: { appState.config.tts.enabled },
            set: { newValue in
                appState.config.tts.enabled = newValue
                appState.ipcClient?.sendConfigUpdate(section: "tts", key: "enabled", value: newValue)
            }
        ))
        .help("Select text in any app and press ⌥T to hear it spoken. First use downloads a local voice model (~170 MB).")

        Divider()

        // === HISTORY ===
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
            Button("Open transcripts folder") {
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
            Button("Open audio folder") {
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

        Button("Check for updates…") {
            appState.ipcClient?.sendAction("update")
        }
        .keyboardShortcut("u", modifiers: [.command, .shift])

        Button("Restart background service") {
            appState.ipcClient?.sendAction("restart")
        }
        .keyboardShortcut("r", modifiers: [.command, .shift])
        .help("Relaunch the headless recording / transcription service in the background. Use if the app stops responding.")

        Button("Open service log") {
            let path = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/service.log")
            NSWorkspace.shared.open(URL(fileURLWithPath: path))
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
        case "parakeet_v3": return "Parakeet-TDT v3"
        case "qwen3_asr":   return "Qwen3-ASR"
        case "whisperkit":  return "WhisperKit"
        default:            return id
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

    private var transcriptionModelMenuTitle: String {
        // STT acronym spelled out in the label so users learn what this feature
        // is. Model name follows so they also see what's actively loaded.
        "Speech-to-text (STT): \(engineDisplayName(appState.config.transcription.engine))"
    }

    private var grammarMenuTitle: String {
        guard appState.config.grammar.enabled else { return "Grammar correction: Off" }
        return "Grammar correction: \(grammarBackendName)"
    }

    private var replacementsMenuTitle: String {
        let count = appState.config.replacements.rules.count
        if count == 0 { return "Text replacements" }
        return "Text replacements (\(count) rule\(count == 1 ? "" : "s"))"
    }

    private var readAloudMenuTitle: String {
        // TTS acronym spelled out so the feature category is unambiguous.
        // Shortcut inline so users know what triggers it.
        "Text-to-speech (TTS) — ⌥T on selection"
    }

    private var transcriptionsMenuTitle: String {
        let count = appState.history.count
        if count == 0 { return "Saved transcriptions" }
        return "Saved transcriptions (\(count))"
    }

    private var recordingsMenuTitle: String {
        let count = appState.historyWithAudio.count
        if count == 0 { return "Saved audio recordings" }
        return "Saved audio recordings (\(count))"
    }

    private var accessibilityStatusLabel: String {
        // Must NOT depend on durationSeconds / rmsLevel — see AppState.menuStatusLabel.
        switch appState.phase {
        case .idle: return "Local Whisper: Ready"
        case .recording: return "Local Whisper: Recording"
        case .processing: return "Local Whisper: Transcribing"
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
