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
                    text: "Activating Read selected text aloud downloads Kokoro-82M (~170 MB) and uses espeak-ng plus the spaCy en_core_web_sm dictionary. The download starts the moment you flip this toggle on."
                )
            }

            if let progress = appState.downloadStates["kokoro_tts"] {
                DownloadProgressBar(progress: progress)
            }

            if appState.config.tts.enabled {
                ShortcutRecorderField(
                    title: "Speak shortcut",
                    description: "Reads the current selection aloud; press again to stop.",
                    icon: "speaker.wave.2.fill",
                    tint: .teal,
                    value: appState.config.tts.speakShortcut,
                    defaultValue: "alt+t",
                    conflicts: ttsConflicts,
                    onCommit: { v in
                        appState.config.tts.speakShortcut = v
                        appState.ipcClient?.sendConfigUpdate(section: "tts", key: "speak_shortcut", value: v)
                    }
                )

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

    private var ttsConflicts: [String: String] {
        var map: [String: String] = [:]
        let bindings: [(String, String)] = [
            (appState.config.shortcuts.proofread, "Proofread"),
            (appState.config.shortcuts.rewrite, "Rewrite"),
            (appState.config.shortcuts.promptEngineer, "Prompt engineer"),
        ]
        for (combo, owner) in bindings where !combo.isEmpty {
            map[combo] = owner
        }
        return map
    }

    private var ttsAdvancedSection: some View {
        Section {
            LabeledContent("Model") {
                DeferredTextField(label: "mlx-community/Kokoro-…", initialValue: appState.config.kokoroTts.model) { v in
                    appState.config.kokoroTts.model = v
                    appState.ipcClient?.sendConfigUpdate(section: "kokoro_tts", key: "model", value: v)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }
            .help("Hugging Face model ID. Default mlx-community/Kokoro-82M-bf16 runs offline after setup. A changed model downloads on the next speak.")
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

            Toggle("Remove speech fillers (um, uh, er…)", isOn: Binding(
                get: { appState.config.dictation.stripFillers },
                set: { v in
                    appState.config.dictation.stripFillers = v
                    appState.ipcClient?.sendConfigUpdate(section: "dictation", key: "strip_fillers", value: v)
                }
            ))
            .help("The filler list is English. Turn this off when dictating in languages where those are real words (German \"er\", \"um\").")

            if appState.config.dictation.enabled {
                DictationCommandsEditor()
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

// MARK: - Dictation commands editor

struct DictationCommandsEditor: View {
    @Environment(AppState.self) private var appState
    @Environment(\.colorScheme) private var colorScheme

    @State private var newPhrase: String = ""
    @State private var newReplacement: String = ""
    @State private var showAllDefaults = false
    @State private var testInput: String = ""
    @FocusState private var focusReplacement: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m - 2) {
            commandGrid
            addRow
            testRow
        }
    }

    // MARK: Grid

    private var visibleCommands: [(phrase: String, replacement: String, isCustom: Bool)] {
        let all = appState.config.dictation.effectiveCommands
        if all.isEmpty {
            // Older service that doesn't send defaults yet: show user
            // commands only.
            return appState.config.dictation.commands
                .sorted { $0.key < $1.key }
                .map { (phrase: $0.key, replacement: $0.value, isCustom: true) }
        }
        if showAllDefaults {
            return all
        }
        // Compact view: customs + a handful of representative defaults.
        let highlights: Set<String> = [
            "new line", "new paragraph", "period", "comma",
            "question mark", "open quote", "close quote", "scratch that",
        ]
        return all.filter { $0.isCustom || highlights.contains($0.phrase) }
    }

    private var commandGrid: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Grid(alignment: .leading, horizontalSpacing: Theme.Spacing.l + 2, verticalSpacing: Theme.Spacing.xs + 1) {
                ForEach(visibleCommands, id: \.phrase) { command in
                    GridRow {
                        Text(command.phrase)
                            .font(Theme.Typography.body)
                            .foregroundStyle(command.isCustom ? .primary : .secondary)
                        KeyCap(label: visualize(command.replacement))
                        HStack(spacing: Theme.Spacing.xs) {
                            if command.isCustom {
                                Text("custom")
                                    .font(Theme.Typography.captionEmphasized)
                                    .foregroundStyle(Theme.Brand.sky)
                                Button {
                                    appState.config.dictation.commands.removeValue(forKey: command.phrase)
                                    appState.ipcClient?.sendDictationCommandRemove(spoken: command.phrase)
                                } label: {
                                    Image(systemName: "minus.circle.fill")
                                        .foregroundStyle(Theme.Tone.danger.color(for: colorScheme))
                                        .symbolRenderingMode(.hierarchical)
                                }
                                .buttonStyle(.plain)
                                .help("Remove custom command \"\(command.phrase)\".")
                                .accessibilityLabel("Remove command \(command.phrase)")
                            } else {
                                Button {
                                    newPhrase = command.phrase
                                    newReplacement = displayEscape(command.replacement)
                                    focusReplacement = true
                                } label: {
                                    Image(systemName: "pencil.circle")
                                        .foregroundStyle(.secondary)
                                        .symbolRenderingMode(.hierarchical)
                                }
                                .buttonStyle(.plain)
                                .help("Override the default \"\(command.phrase)\" command.")
                                .accessibilityLabel("Override command \(command.phrase)")
                            }
                        }
                    }
                }
            }

            if !appState.config.dictation.defaults.isEmpty {
                Button(showAllDefaults ? "Show fewer" : "Show all \(appState.config.dictation.effectiveCommands.count) commands") {
                    showAllDefaults.toggle()
                }
                .buttonStyle(.link)
                .font(Theme.Typography.caption)
            }
        }
    }

    // MARK: Add / override row

    private var addRow: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Divider()
            HStack(spacing: Theme.Spacing.s) {
                TextField("Spoken phrase (e.g. next bullet)", text: $newPhrase)
                    .textFieldStyle(.roundedBorder)
                    .disableAutocorrection(true)
                Image(systemName: "arrow.right")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                TextField("Replacement (\\n = new line, empty = remove)", text: $newReplacement)
                    .textFieldStyle(.roundedBorder)
                    .focused($focusReplacement)
                    .disableAutocorrection(true)
                    .onSubmit { commitCommand() }
                Button("Add") { commitCommand() }
                    .buttonStyle(.borderedProminent)
                    .disabled(newPhrase.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            Text("Overrides a default when the phrase matches. Use \\n for a new line, \\t for a tab.")
                .font(Theme.Typography.caption)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: Tester

    private var testRow: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Divider()
            HStack(spacing: Theme.Spacing.s) {
                TextField("Try it: \"hello comma world period\"", text: $testInput)
                    .textFieldStyle(.roundedBorder)
                    .disableAutocorrection(true)
                    .onSubmit { runTest() }
                Button("Test") { runTest() }
                    .disabled(testInput.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if let result = appState.dictationTestResult {
                HStack(alignment: .top, spacing: Theme.Spacing.s) {
                    Text("Out")
                        .font(Theme.Typography.captionEmphasized)
                        .foregroundStyle(.secondary)
                    Text(result.output.isEmpty ? "(empty)" : result.output)
                        .font(Theme.Typography.bodyEmphasized)
                        .textSelection(.enabled)
                }
            }
        }
    }

    // MARK: Helpers

    private func commitCommand() {
        let phrase = newPhrase.trimmingCharacters(in: .whitespaces).lowercased()
        guard !phrase.isEmpty else { return }
        let replacement = inputUnescape(newReplacement)
        appState.config.dictation.commands[phrase] = replacement
        appState.ipcClient?.sendDictationCommandAdd(spoken: phrase, replacement: replacement)
        newPhrase = ""
        newReplacement = ""
    }

    private func runTest() {
        let text = testInput.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        appState.ipcClient?.sendDictationTest(text: text)
    }

    /// Typed "\n"/"\t" become real control characters.
    private func inputUnescape(_ s: String) -> String {
        s.replacingOccurrences(of: "\\n", with: "\n")
            .replacingOccurrences(of: "\\t", with: "\t")
    }

    /// Real control characters render as typeable escapes in the edit field.
    private func displayEscape(_ s: String) -> String {
        s.replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\t", with: "\\t")
    }

    private func visualize(_ s: String) -> String {
        let mapped = s
            .replacingOccurrences(of: "\n\n", with: "¶¶")
            .replacingOccurrences(of: "\n", with: "¶")
            .replacingOccurrences(of: "\t", with: "→")
        return mapped.isEmpty ? "removed" : mapped
    }
}
