import SwiftUI

// MARK: - Voice & Speech panel

struct VoicePanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            Form {
                ttsSection
                if appState.config.tts.enabled {
                    ttsAdvancedSection
                }
                dictationSection
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - TTS

    private var ttsSection: some View {
        Section {
            Toggle("Read selected text aloud", isOn: Binding(
                get: { appState.config.tts.enabled },
                set: { v in
                    appState.config.tts.enabled = v
                    appState.ipcClient?.sendConfigUpdate(section: "tts", key: "enabled", value: v)
                }
            ))
            .help("Press the speak shortcut in any app to hear the selection. Press it again to stop.")

            if !appState.config.tts.enabled {
                InlineNotice(
                    kind: .info,
                    text: "Activating Read selected text aloud downloads Kokoro-82M (~170 MB) on the first ⌥T press and uses espeak-ng plus the spaCy en_core_web_sm dictionary. Run ./setup.sh while enabled to pre-fetch everything."
                )
            }

            if appState.config.tts.enabled {
                LabeledContent("Shortcut") {
                    HStack(spacing: 4) {
                        ForEach(KeyboardGlyph.tokens(for: appState.config.tts.speakShortcut), id: \.self) { token in
                            KeyCap(label: token)
                        }
                    }
                }

                Picker("Voice", selection: Binding(
                    get: { appState.config.kokoroTts.voice },
                    set: { v in
                        appState.config.kokoroTts.voice = v
                        appState.ipcClient?.sendConfigUpdate(section: "kokoro_tts", key: "voice", value: v)
                    }
                )) {
                    Section("American female") {
                        Text("Heart").tag("af_heart")
                        Text("Bella").tag("af_bella")
                        Text("Nova").tag("af_nova")
                        Text("Sky").tag("af_sky")
                        Text("Sarah").tag("af_sarah")
                        Text("Nicole").tag("af_nicole")
                    }
                    Section("American male") {
                        Text("Adam").tag("am_adam")
                        Text("Echo").tag("am_echo")
                        Text("Eric").tag("am_eric")
                        Text("Liam").tag("am_liam")
                    }
                    Section("British female") {
                        Text("Alice").tag("bf_alice")
                        Text("Emma").tag("bf_emma")
                    }
                    Section("British male") {
                        Text("Daniel").tag("bm_daniel")
                        Text("George").tag("bm_george")
                    }
                }
            }
        } header: {
            SettingsSectionHeader(
                symbol: "speaker.wave.2.fill",
                title: "Text to speech",
                description: "Kokoro-82M runs entirely on-device after the first download."
            )
        }
    }

    private var ttsAdvancedSection: some View {
        Section {
            LabeledContent("Speak shortcut") {
                DeferredTextField(label: "alt+t", initialValue: appState.config.tts.speakShortcut) { v in
                    appState.config.tts.speakShortcut = v
                    appState.ipcClient?.sendConfigUpdate(section: "tts", key: "speak_shortcut", value: v)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 200)
            }
            .help("Format: modifier+key, e.g. alt+t for ⌥T.")

            LabeledContent("Model") {
                DeferredTextField(label: "mlx-community/Kokoro-…", initialValue: appState.config.kokoroTts.model) { v in
                    appState.config.kokoroTts.model = v
                    appState.ipcClient?.sendConfigUpdate(section: "kokoro_tts", key: "model", value: v)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }
            .help("Hugging Face model ID. Default mlx-community/Kokoro-82M-bf16 runs offline after setup.")

            RestartNote()
        } header: {
            SettingsSectionHeader(symbol: "wrench.and.screwdriver", title: "Advanced")
        }
    }

    // MARK: - Dictation commands

    private var dictationSection: some View {
        Section {
            Toggle("Speak punctuation and whitespace", isOn: Binding(
                get: { appState.config.dictation.enabled },
                set: { v in
                    appState.config.dictation.enabled = v
                    appState.ipcClient?.sendConfigUpdate(section: "dictation", key: "enabled", value: v)
                }
            ))
            .help("Replaces phrases like \"new line\" or \"period\" with the literal character before grammar runs.")

            if appState.config.dictation.enabled {
                DictationCommandsHelpView()
            }
        } header: {
            SettingsSectionHeader(
                symbol: "text.cursor",
                title: "Dictation commands",
                description: "Voice phrases that turn into punctuation, whitespace, or text edits."
            )
        }
    }

}

// MARK: - Dictation help (extracted, reused across panels)

struct DictationCommandsHelpView: View {
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
        VStack(alignment: .leading, spacing: Theme.Spacing.m - 2) {
            Grid(alignment: .leading, horizontalSpacing: Theme.Spacing.l + 2, verticalSpacing: Theme.Spacing.xs + 1) {
                ForEach(Self.defaultExamples, id: \.0) { phrase, glyph in
                    GridRow {
                        Text(phrase)
                            .font(Theme.Typography.body)
                            .foregroundStyle(.secondary)
                        KeyCap(label: glyph)
                    }
                }
            }

            if !appState.config.dictation.commands.isEmpty {
                Divider()
                Text("Custom commands (\(appState.config.dictation.commands.count))")
                    .font(Theme.Typography.captionEmphasized)
                    .foregroundStyle(.secondary)
                Grid(alignment: .leading, horizontalSpacing: Theme.Spacing.l + 2, verticalSpacing: Theme.Spacing.xs + 1) {
                    ForEach(Array(appState.config.dictation.commands.sorted(by: { $0.key < $1.key })), id: \.key) { phrase, replacement in
                        GridRow {
                            Text(phrase)
                                .font(Theme.Typography.body)
                                .foregroundStyle(.secondary)
                            KeyCap(label: visualize(replacement))
                        }
                    }
                }
            }

            HStack(spacing: Theme.Spacing.xs + 2) {
                Image(systemName: "text.cursor")
                    .foregroundStyle(.secondary)
                    .symbolRenderingMode(.hierarchical)
                Text(configHint)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func visualize(_ s: String) -> String {
        let mapped = s
            .replacingOccurrences(of: "\n\n", with: "¶¶")
            .replacingOccurrences(of: "\n", with: "¶")
            .replacingOccurrences(of: "\t", with: "→")
        return mapped.isEmpty ? "<removed>" : mapped
    }

    private var configHint: AttributedString {
        var out = AttributedString("Add more under ")
        var c1 = AttributedString("[dictation.commands]")
        c1.font = Theme.Typography.monoSmall
        out.append(c1)
        out.append(AttributedString(" in "))
        var c2 = AttributedString("~/.whisper/config.toml")
        c2.font = Theme.Typography.monoSmall
        out.append(c2)
        out.append(AttributedString("."))
        return out
    }
}
