import SwiftUI

// MARK: - General settings tab

struct GeneralSettingsView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            Form {
                Section("Recording") {
                    Picker("Trigger Key", selection: Binding(
                        get: { appState.config.hotkey.key },
                        set: { newValue in
                            appState.config.hotkey.key = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "hotkey", key: "key", value: newValue)
                        }
                    )) {
                        Text("Right Option (⌥)").tag("alt_r")
                        Text("Left Option (⌥)").tag("alt_l")
                        Text("Right Control (⌃)").tag("ctrl_r")
                        Text("Left Control (⌃)").tag("ctrl_l")
                        Text("Right Command (⌘)").tag("cmd_r")
                        Text("Left Command (⌘)").tag("cmd_l")
                        Text("Right Shift (⇧)").tag("shift_r")
                        Text("Left Shift (⇧)").tag("shift_l")
                        Text("Caps Lock").tag("caps_lock")
                        Text("F1").tag("f1")
                        Text("F2").tag("f2")
                        Text("F3").tag("f3")
                        Text("F4").tag("f4")
                        Text("F5").tag("f5")
                        Text("F6").tag("f6")
                        Text("F7").tag("f7")
                        Text("F8").tag("f8")
                        Text("F9").tag("f9")
                        Text("F10").tag("f10")
                        Text("F11").tag("f11")
                        Text("F12").tag("f12")
                    }
                    .accessibilityHint("The key you double-tap to start and stop recording")

                    RestartNote()

                    LabeledContent("Double-tap window") {
                        HStack {
                            Slider(value: Binding(
                                get: { appState.config.hotkey.doubleTapThreshold },
                                set: { newValue in
                                    appState.config.hotkey.doubleTapThreshold = newValue
                                    appState.ipcClient?.sendConfigUpdate(section: "hotkey", key: "double_tap_threshold", value: newValue)
                                }
                            ), in: 0.1...1.0, step: 0.05)
                            .accessibilityHint("Maximum time between two taps to count as a double-tap")
                            Text(String(format: "%.2fs", appState.config.hotkey.doubleTapThreshold))
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .frame(width: 44, alignment: .trailing)
                        }
                    }
                }

                Section("Transcription") {
                    Picker("Engine", selection: Binding(
                        get: { appState.config.transcription.engine },
                        set: { newValue in
                            appState.config.transcription.engine = newValue
                            appState.ipcClient?.sendEngineSwitch(newValue)
                        }
                    )) {
                        Text("Qwen3-ASR").tag("qwen3_asr")
                        Text("WhisperKit").tag("whisperkit")
                    }
                    .accessibilityHint("Qwen3-ASR runs fully in-process. WhisperKit requires a local server.")
                    RestartNote()

                    if appState.config.transcription.engine == "qwen3_asr" {
                        Picker("Language", selection: Binding(
                            get: { appState.config.qwen3Asr.language },
                            set: { newValue in
                                appState.config.qwen3Asr.language = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "language", value: newValue)
                            }
                        )) {
                            Text("Auto-detect").tag("auto")
                            Text("English").tag("en")
                            Text("Persian").tag("fa")
                            Text("Spanish").tag("es")
                            Text("French").tag("fr")
                            Text("German").tag("de")
                            Text("Arabic").tag("ar")
                            Text("Chinese").tag("zh")
                            Text("Japanese").tag("ja")
                            Text("Korean").tag("ko")
                            Text("Italian").tag("it")
                            Text("Portuguese").tag("pt")
                            Text("Russian").tag("ru")
                        }
                    }
                }

                Section("Grammar Correction") {
                    Toggle("Enable grammar correction", isOn: Binding(
                        get: { appState.config.grammar.enabled },
                        set: { newValue in
                            appState.config.grammar.enabled = newValue
                            // Use backend_switch so the service actually initializes or
                            // tears down the backend in-process — a raw config_update
                            // only writes the flag and leaves the loaded model dangling.
                            if newValue {
                                appState.ipcClient?.sendBackendSwitch(appState.config.grammar.backend)
                            } else {
                                appState.ipcClient?.sendBackendSwitch("none")
                            }
                        }
                    ))
                    .accessibilityHint("When enabled, transcribed text is cleaned up by the selected grammar backend before being copied")

                    if appState.config.grammar.enabled {
                        Picker("Backend", selection: Binding(
                            get: { appState.config.grammar.backend },
                            set: { newValue in
                                appState.config.grammar.backend = newValue
                                appState.ipcClient?.sendBackendSwitch(newValue)
                            }
                        )) {
                            Text("Apple Intelligence").tag("apple_intelligence")
                            Text("Ollama").tag("ollama")
                            Text("LM Studio").tag("lm_studio")
                        }
                        .accessibilityHint("The on-device model used to correct grammar and punctuation")
                    }
                }

                Section("Interface") {
                    Toggle("Show overlay during recording", isOn: Binding(
                        get: { appState.config.ui.showOverlay },
                        set: { newValue in
                            appState.config.ui.showOverlay = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "ui", key: "show_overlay", value: newValue)
                        }
                    ))

                    if appState.config.ui.showOverlay {
                        LabeledContent("Overlay opacity") {
                            HStack {
                                Slider(value: Binding(
                                    get: { appState.config.ui.overlayOpacity },
                                    set: { v in
                                        appState.config.ui.overlayOpacity = v
                                        appState.ipcClient?.sendConfigUpdate(section: "ui", key: "overlay_opacity", value: v)
                                    }
                                ), in: 0.3...1.0, step: 0.05)
                                Text(String(format: "%.0f%%", appState.config.ui.overlayOpacity * 100))
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundStyle(.secondary)
                                    .frame(width: 36, alignment: .trailing)
                            }
                        }
                    }

                    Toggle("Play sounds", isOn: Binding(
                        get: { appState.config.ui.soundsEnabled },
                        set: { newValue in
                            appState.config.ui.soundsEnabled = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "ui", key: "sounds_enabled", value: newValue)
                        }
                    ))

                    Toggle("Show notifications", isOn: Binding(
                        get: { appState.config.ui.notificationsEnabled },
                        set: { newValue in
                            appState.config.ui.notificationsEnabled = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "ui", key: "notifications_enabled", value: newValue)
                        }
                    ))

                    Toggle("Auto-paste at cursor", isOn: Binding(
                        get: { appState.config.ui.autoPaste },
                        set: { newValue in
                            appState.config.ui.autoPaste = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "ui", key: "auto_paste", value: newValue)
                        }
                    ))
                    .accessibilityHint("When enabled, transcribed text is pasted directly at the cursor. Your clipboard is left unchanged.")
                }

                Section("Shortcuts") {
                    Toggle("Enable text transformation shortcuts", isOn: Binding(
                        get: { appState.config.shortcuts.enabled },
                        set: { newValue in
                            appState.config.shortcuts.enabled = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "enabled", value: newValue)
                        }
                    ))
                    .accessibilityHint("Allows pressing a keyboard shortcut to proofread or rewrite selected text in any app")

                    if appState.config.shortcuts.enabled {
                        LabeledContent("Proofread") {
                            Text(appState.config.shortcuts.proofread)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(.secondary)
                        }
                        LabeledContent("Rewrite") {
                            Text(appState.config.shortcuts.rewrite)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(.secondary)
                        }
                        LabeledContent("Prompt engineer") {
                            Text(appState.config.shortcuts.promptEngineer)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(.secondary)
                        }
                        HStack {
                            Image(systemName: "info.circle")
                                .foregroundStyle(.secondary)
                            Text("Select text in any app and press the shortcut to transform it. Customize keys in Advanced.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Section("Text to Speech") {
                    Toggle("Enable Text to Speech", isOn: Binding(
                        get: { appState.config.tts.enabled },
                        set: { newValue in
                            appState.config.tts.enabled = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "tts", key: "enabled", value: newValue)
                        }
                    ))
                    .accessibilityHint("Select text in any app and press the shortcut to hear it read aloud")

                    if appState.config.tts.enabled {
                        LabeledContent("Shortcut") {
                            Text(appState.config.tts.speakShortcut)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(.secondary)
                        }

                        Picker("Voice", selection: Binding(
                            get: { appState.config.kokoroTts.voice },
                            set: { newValue in
                                appState.config.kokoroTts.voice = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "kokoro_tts", key: "voice", value: newValue)
                            }
                        )) {
                            Text("Heart — American female").tag("af_heart")
                            Text("Bella — American female").tag("af_bella")
                            Text("Nova — American female").tag("af_nova")
                            Text("Sky — American female").tag("af_sky")
                            Text("Sarah — American female").tag("af_sarah")
                            Text("Nicole — American female").tag("af_nicole")
                            Text("Alice — British female").tag("bf_alice")
                            Text("Emma — British female").tag("bf_emma")
                            Text("Adam — American male").tag("am_adam")
                            Text("Echo — American male").tag("am_echo")
                            Text("Eric — American male").tag("am_eric")
                            Text("Liam — American male").tag("am_liam")
                            Text("Daniel — British male").tag("bm_daniel")
                            Text("George — British male").tag("bm_george")
                        }

                        HStack {
                            Image(systemName: "info.circle")
                                .foregroundStyle(.secondary)
                            Text("Select text in any app and press ⌥T to hear it read aloud. Press ⌥T again to stop.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Section("Dictation Commands") {
                    Toggle("Speak punctuation and whitespace", isOn: Binding(
                        get: { appState.config.dictation.enabled },
                        set: { newValue in
                            appState.config.dictation.enabled = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "dictation", key: "enabled", value: newValue)
                        }
                    ))
                    .accessibilityHint("When enabled, phrases like \"new line\", \"period\", and \"scratch that\" are replaced with literal punctuation or whitespace before grammar correction runs")

                    if appState.config.dictation.enabled {
                        DictationCommandsHelpView()
                    }
                }

                Section("Replacements") {
                    Toggle("Enable text replacements", isOn: Binding(
                        get: { appState.config.replacements.enabled },
                        set: { newValue in
                            appState.config.replacements.enabled = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "replacements", key: "enabled", value: newValue)
                        }
                    ))
                    .accessibilityHint("When enabled, matching words and phrases are automatically replaced after transcription")

                    if appState.config.replacements.enabled {
                        ReplacementRulesView()
                    }
                }

                Section("History") {
                    Stepper(
                        "Keep \(appState.config.backup.historyLimit) entries",
                        value: Binding(
                            get: { appState.config.backup.historyLimit },
                            set: { newValue in
                                appState.config.backup.historyLimit = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "backup", key: "history_limit", value: newValue)
                            }
                        ),
                        in: 1...1000
                    )
                }

                Section {
                    HStack {
                        Image(systemName: "checkmark.icloud")
                            .foregroundStyle(.secondary)
                        Text("Settings save automatically.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .formStyle(.grouped)
        }
    }
}

// MARK: - Dictation commands help

private struct DictationCommandsHelpView: View {
    @Environment(AppState.self) private var appState

    private static let defaultExamples: [(String, String)] = [
        ("new line", "↵"),
        ("new paragraph", "¶"),
        ("period", "."),
        ("comma", ","),
        ("question mark", "?"),
        ("exclamation mark", "!"),
        ("colon", ":"),
        ("semicolon", ";"),
        ("dash", " - "),
        ("open paren / close paren", "( )"),
        ("open quote / close quote", "\" \""),
        ("scratch that", "delete fragment"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "info.circle")
                    .foregroundStyle(.secondary)
                Text("Say these phrases while dictating to insert the literal punctuation or whitespace.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
                ForEach(Self.defaultExamples, id: \.0) { phrase, glyph in
                    GridRow {
                        Text(phrase)
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(.secondary)
                        Text(glyph)
                            .font(.system(size: 12, design: .monospaced))
                    }
                }
            }
            .padding(.leading, 4)

            if !appState.config.dictation.commands.isEmpty {
                Divider()
                Text("Custom commands (\(appState.config.dictation.commands.count))")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
                    ForEach(Array(appState.config.dictation.commands.sorted(by: { $0.key < $1.key })), id: \.key) { phrase, replacement in
                        GridRow {
                            Text(phrase)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(.secondary)
                            Text(visualize(replacement))
                                .font(.system(size: 12, design: .monospaced))
                        }
                    }
                }
                .padding(.leading, 4)
            }

            HStack {
                Image(systemName: "text.cursor")
                    .foregroundStyle(.secondary)
                Text("Add more under `[dictation.commands]` in `~/.whisper/config.toml`.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func visualize(_ s: String) -> String {
        s.replacingOccurrences(of: "\n\n", with: "¶¶")
            .replacingOccurrences(of: "\n", with: "¶")
            .replacingOccurrences(of: "\t", with: "→")
            .ifEmpty("<removed>")
    }
}

private extension String {
    func ifEmpty(_ fallback: String) -> String { isEmpty ? fallback : self }
}

// MARK: - Replacement rules editor

private struct ReplacementRulesView: View {
    @Environment(AppState.self) private var appState
    @State private var newSpoken = ""
    @State private var newReplacement = ""

    private var sortedRules: [(key: String, value: String)] {
        appState.config.replacements.rules.sorted { $0.key.localizedCaseInsensitiveCompare($1.key) == .orderedAscending }
    }

    var body: some View {
        ForEach(sortedRules, id: \.key) { rule in
            HStack {
                Text(rule.key)
                    .foregroundStyle(.secondary)
                Image(systemName: "arrow.right")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                Text(rule.value)
                Spacer()
                Button {
                    appState.config.replacements.rules.removeValue(forKey: rule.key)
                    appState.ipcClient?.sendReplacementRemove(spoken: rule.key)
                } label: {
                    Image(systemName: "minus.circle.fill")
                        .foregroundStyle(.red)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Remove replacement for \(rule.key)")
            }
        }

        HStack(spacing: 8) {
            TextField("Spoken form", text: $newSpoken)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 160)
            Image(systemName: "arrow.right")
                .font(.caption2)
                .foregroundStyle(.tertiary)
            TextField("Replacement", text: $newReplacement)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 160)
            Button {
                let spoken = newSpoken.trimmingCharacters(in: .whitespaces)
                let replacement = newReplacement.trimmingCharacters(in: .whitespaces)
                guard !spoken.isEmpty, !replacement.isEmpty else { return }
                appState.config.replacements.rules[spoken] = replacement
                appState.ipcClient?.sendReplacementAdd(spoken: spoken, replacement: replacement)
                newSpoken = ""
                newReplacement = ""
            } label: {
                Image(systemName: "plus.circle.fill")
                    .foregroundStyle(.green)
            }
            .buttonStyle(.plain)
            .disabled(newSpoken.trimmingCharacters(in: .whitespaces).isEmpty || newReplacement.trimmingCharacters(in: .whitespaces).isEmpty)
            .accessibilityLabel("Add replacement rule")
        }

        HStack {
            Image(systemName: "info.circle")
                .foregroundStyle(.secondary)
            Text("Replacements are applied after transcription and grammar correction. Matching is case-insensitive.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}
