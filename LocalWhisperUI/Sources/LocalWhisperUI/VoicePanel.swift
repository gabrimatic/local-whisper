import SwiftUI

// MARK: - Voice & Speech panel

struct VoicePanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        PanelScaffold(
            title: "Voice",
            subtitle: "Read text aloud and speak punctuation while dictating."
        ) {
            ttsCard
            if appState.config.tts.enabled {
                ttsAdvancedCard
            }
            dictationCard
        }
    }

    // MARK: - TTS

    private var ttsCard: some View {
        SettingsCard(
            icon: "speaker.wave.2.fill",
            title: "Text to speech",
            description: "Kokoro-82M runs entirely on-device after the first download."
        ) {
            ToggleRow(
                title: "Read selected text aloud",
                subtitle: "Press the speak shortcut in any app to hear the selection. Press it again to stop.",
                isOn: appState.config.tts.enabled
            ) { v in
                appState.config.tts.enabled = v
                appState.ipcClient?.sendConfigUpdate(section: "tts", key: "enabled", value: v)
            }

            if !appState.config.tts.enabled {
                WideRow {
                    InlineNotice(
                        kind: .info,
                        text: "Activating Read selected text aloud downloads Kokoro-82M (~170 MB) and uses espeak-ng plus the spaCy en_core_web_sm dictionary. The download starts the moment you flip this toggle on."
                    )
                }
            }

            if let progress = appState.downloadStates["kokoro_tts"] {
                WideRow {
                    DownloadProgressBar(progress: progress)
                }
            }

            // The recorder stays visible even while TTS is off: the combo
            // still reserves its slot in the conflict map, and freeing it
            // must not require enabling TTS (which starts a model download).
            WideRow {
                ShortcutRecorderField(
                    title: "Speak shortcut",
                    description: appState.config.tts.enabled
                        ? "Reads the current selection aloud; press again to stop."
                        : "Active once Read aloud is on. Recorded now so other shortcuts can't take it.",
                    icon: "speaker.wave.2.fill",
                    tint: Theme.Brand.sky,
                    value: appState.config.tts.speakShortcut,
                    defaultValue: "alt+t",
                    conflicts: ttsConflicts,
                    blockedKeys: blockedTriggerKeys,
                    onCommit: { v in
                        appState.config.tts.speakShortcut = v
                        appState.ipcClient?.sendConfigUpdate(section: "tts", key: "speak_shortcut", value: v)
                    }
                )
            }

            if appState.config.tts.enabled {
                SettingRow(title: "Voice") {
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
                    .pickerStyle(.menu)
                    .fixedSize()
                }
            }
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

    private var blockedTriggerKeys: [String: String] {
        let trigger = appState.config.hotkey.key
        guard ShortcutSpec.functionKeys.contains(trigger) else { return [:] }
        return [trigger: "recording trigger key"]
    }

    private var ttsAdvancedCard: some View {
        SettingsCard(
            icon: "wrench.and.screwdriver",
            title: "Advanced"
        ) {
            SettingRow(
                title: "Model",
                subtitle: "Hugging Face model ID. The default runs offline after setup; a changed model downloads on the next speak."
            ) {
                DeferredTextField(label: "mlx-community/Kokoro-…", initialValue: appState.config.kokoroTts.model) { v in
                    appState.config.kokoroTts.model = v
                    appState.ipcClient?.sendConfigUpdate(section: "kokoro_tts", key: "model", value: v)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 280)
            }
        }
    }

    // MARK: - Dictation commands

    private var dictationCard: some View {
        SettingsCard(
            icon: "text.cursor",
            title: "Dictation commands",
            description: "Voice phrases that turn into punctuation, whitespace, or text edits."
        ) {
            ToggleRow(
                title: "Speak punctuation and whitespace",
                subtitle: "Replaces phrases like \"new line\" or \"period\" with the literal character before grammar runs.",
                isOn: appState.config.dictation.enabled
            ) { v in
                appState.config.dictation.enabled = v
                appState.ipcClient?.sendConfigUpdate(section: "dictation", key: "enabled", value: v)
            }

            // Filler stripping runs inside the dictation-commands pass, so it
            // is honestly disabled when the master toggle is off instead of
            // pretending to be active.
            ToggleRow(
                title: "Remove speech fillers (um, uh, er…)",
                subtitle: appState.config.dictation.enabled
                    ? "The filler list is English. Turn this off when dictating in languages where those are real words."
                    : "Requires \"Speak punctuation and whitespace\" to be on.",
                isOn: appState.config.dictation.stripFillers
            ) { v in
                appState.config.dictation.stripFillers = v
                appState.ipcClient?.sendConfigUpdate(section: "dictation", key: "strip_fillers", value: v)
            }
            .disabled(!appState.config.dictation.enabled)
            .opacity(appState.config.dictation.enabled ? 1.0 : 0.55)

            if appState.config.dictation.enabled {
                WideRow {
                    DictationCommandsEditor()
                }
            }
        }
    }

}

// MARK: - Dictation commands editor

struct DictationCommandsEditor: View {
    @Environment(AppState.self) private var appState

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
                                        .foregroundStyle(Theme.Tone.danger.color)
                                        .symbolRenderingMode(.hierarchical)
                                }
                                .buttonStyle(.plain)
                                .help("Remove custom command \"\(command.phrase)\".")
                                .accessibilityLabel("Remove command \(command.phrase)")
                            } else if command.replacement != scratchSentinel {
                                // The scratch sentinel is engine behavior, not
                                // replaceable text — overriding it would just
                                // break "scratch that".
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

    private var scratchSentinel: String { "__SCRATCH__" }

    private func visualize(_ s: String) -> String {
        if s == scratchSentinel { return "removes last phrase" }
        let mapped = s
            .replacingOccurrences(of: "\n\n", with: "¶¶")
            .replacingOccurrences(of: "\n", with: "¶")
            .replacingOccurrences(of: "\t", with: "→")
        return mapped.isEmpty ? "removed" : mapped
    }
}
