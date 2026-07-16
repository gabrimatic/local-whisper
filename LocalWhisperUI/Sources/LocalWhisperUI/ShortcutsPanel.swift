import SwiftUI

// MARK: - Shortcuts panel

struct ShortcutsPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        PanelScaffold(
            title: "Shortcuts",
            subtitle: "Global keybindings that transform the current text selection in any app."
        ) {
            masterCard
            if appState.config.shortcuts.enabled {
                keysCard
                behaviorCard
            }
            cheatsheetCard
        }
    }

    // MARK: - Master toggle

    private var masterCard: some View {
        SettingsCard(
            icon: "wand.and.stars",
            title: "Text transforms",
            description: "Operate on the current text selection in any app."
        ) {
            ToggleRow(
                title: "Enable text-transformation shortcuts",
                subtitle: "Select text anywhere and press a shortcut to proofread, rewrite, or convert it into a prompt. Changes apply immediately.",
                isOn: appState.config.shortcuts.enabled
            ) { v in
                appState.config.shortcuts.enabled = v
                appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "enabled", value: v)
            }

            if appState.config.shortcuts.enabled && !appState.config.grammar.enabled {
                WideRow {
                    InlineNotice(
                        kind: .warning,
                        text: "These shortcuts need grammar correction. Enable a backend in the Grammar panel or the keys will report \"Backend unavailable\"."
                    )
                }
            }
        }
    }

    // MARK: - Per-shortcut keys

    /// Combos already taken by OTHER bindings (for conflict refusal),
    /// excluding the one being edited.
    private func conflicts(excluding editing: String) -> [String: String] {
        var map: [String: String] = [:]
        let bindings: [(String, String)] = [
            (appState.config.shortcuts.proofread, "Proofread"),
            (appState.config.shortcuts.rewrite, "Rewrite"),
            (appState.config.shortcuts.promptEngineer, "Prompt engineer"),
            (appState.config.tts.speakShortcut, "Read selection aloud"),
        ]
        for (combo, owner) in bindings where !combo.isEmpty && owner != editing {
            map[combo] = owner
        }
        return map
    }

    /// The dictation trigger intercepts its keycode wholesale, so an F-key
    /// trigger poisons EVERY combo on that key — refuse them up front.
    private var blockedTriggerKeys: [String: String] {
        let trigger = appState.config.hotkey.key
        guard ShortcutSpec.functionKeys.contains(trigger) else { return [:] }
        return [trigger: "recording trigger key"]
    }

    private var keysCard: some View {
        SettingsCard(
            icon: "command",
            title: "Keybindings",
            description: "Click a field and press the new combination. Changes bind immediately — no restart."
        ) {
            WideRow {
                ShortcutRecorderField(
                    title: "Proofread",
                    description: "Mechanical fixes: spelling, punctuation, capitalisation.",
                    icon: "checkmark.seal.fill",
                    tint: Theme.Tone.success.color,
                    value: appState.config.shortcuts.proofread,
                    defaultValue: "ctrl+shift+g",
                    conflicts: conflicts(excluding: "Proofread"),
                    blockedKeys: blockedTriggerKeys,
                    onCommit: { v in
                        appState.config.shortcuts.proofread = v
                        appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "proofread", value: v)
                    }
                )
            }
            WideRow {
                ShortcutRecorderField(
                    title: "Rewrite",
                    description: "Smooths sentences while preserving meaning.",
                    icon: "pencil.and.scribble",
                    tint: Theme.Brand.accent,
                    value: appState.config.shortcuts.rewrite,
                    defaultValue: "ctrl+shift+r",
                    conflicts: conflicts(excluding: "Rewrite"),
                    blockedKeys: blockedTriggerKeys,
                    onCommit: { v in
                        appState.config.shortcuts.rewrite = v
                        appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "rewrite", value: v)
                    }
                )
            }
            WideRow {
                ShortcutRecorderField(
                    title: "Prompt engineer",
                    description: "Turns the selection into a structured prompt.",
                    icon: "sparkles",
                    tint: Theme.Brand.sky,
                    value: appState.config.shortcuts.promptEngineer,
                    defaultValue: "ctrl+shift+p",
                    conflicts: conflicts(excluding: "Prompt engineer"),
                    blockedKeys: blockedTriggerKeys,
                    onCommit: { v in
                        appState.config.shortcuts.promptEngineer = v
                        appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "prompt_engineer", value: v)
                    }
                )
            }
        }
    }

    // MARK: - Behavior

    private var behaviorCard: some View {
        SettingsCard(
            icon: "arrow.triangle.2.circlepath",
            title: "Result delivery",
            description: "What happens with the transformed text."
        ) {
            ToggleRow(
                title: "Paste result over the selection",
                subtitle: "The corrected text replaces your selection in place. It is always copied to the clipboard too, so nothing is ever lost.",
                isOn: appState.config.shortcuts.pasteResult
            ) { v in
                appState.config.shortcuts.pasteResult = v
                appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "paste_result", value: v)
            }
        }
    }

    // MARK: - Cheatsheet

    private var cheatsheetCard: some View {
        SettingsCard(
            icon: "keyboard",
            title: "Cheatsheet",
            description: "Every shortcut Local Whisper currently responds to."
        ) {
            WideRow {
                VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                    cheatRow(label: "Start / stop recording", keys: triggerKeys)
                    cheatRow(label: "Hold to record, release to paste", keys: triggerKeys)
                    cheatRow(label: "Stop recording (alternative)", keys: ["␣"])
                    cheatRow(label: "Cancel recording",       keys: ["⎋"])
                    if appState.config.shortcuts.enabled {
                        Divider()
                        if !appState.config.shortcuts.proofread.isEmpty {
                            cheatRow(label: "Proofread selection", keys: KeyboardGlyph.tokens(for: appState.config.shortcuts.proofread))
                        }
                        if !appState.config.shortcuts.rewrite.isEmpty {
                            cheatRow(label: "Rewrite selection", keys: KeyboardGlyph.tokens(for: appState.config.shortcuts.rewrite))
                        }
                        if !appState.config.shortcuts.promptEngineer.isEmpty {
                            cheatRow(label: "Prompt-engineer selection", keys: KeyboardGlyph.tokens(for: appState.config.shortcuts.promptEngineer))
                        }
                    }
                    if appState.config.tts.enabled && !appState.config.tts.speakShortcut.isEmpty {
                        Divider()
                        cheatRow(label: "Read selection aloud",   keys: KeyboardGlyph.tokens(for: appState.config.tts.speakShortcut))
                        cheatRow(label: "Stop speaking",           keys: ["⎋"])
                    }
                    Divider()
                    cheatRow(label: "Open Settings",          keys: ["⌘", ","])
                    cheatRow(label: "Quit",                    keys: ["⌘", "Q"])
                }
            }
        }
    }

    private var triggerKeys: [String] {
        KeyboardGlyph.triggerTokens(for: appState.config.hotkey.key)
    }

    private func cheatRow(label: String, keys: [String]) -> some View {
        HStack(spacing: Theme.Spacing.s) {
            Text(label)
                .font(Theme.Typography.body)
                .foregroundStyle(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 4) {
                ForEach(Array(keys.enumerated()), id: \.offset) { _, key in
                    KeyCap(label: key)
                }
            }
            .accessibilityLabel(keys.joined(separator: " "))
        }
    }
}
