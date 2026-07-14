import SwiftUI

// MARK: - Shortcuts panel

struct ShortcutsPanel: View {
    @Environment(AppState.self) private var appState
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        ScrollView {
            Form {
                masterSection
                if appState.config.shortcuts.enabled {
                    keysSection
                    behaviorSection
                }
                cheatsheetSection
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Master toggle

    private var masterSection: some View {
        Section {
            Toggle("Enable text-transformation shortcuts", isOn: Binding(
                get: { appState.config.shortcuts.enabled },
                set: { v in
                    appState.config.shortcuts.enabled = v
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "enabled", value: v)
                }
            ))
            .help("Select text in any app and press a shortcut to proofread, rewrite, or convert it into a prompt. Changes apply immediately.")

            if appState.config.shortcuts.enabled && !appState.config.grammar.enabled {
                InlineNotice(
                    kind: .warning,
                    text: "These shortcuts need grammar correction. Enable a backend in the Grammar panel or the keys will report \"Backend unavailable\"."
                )
            }
        } header: {
            SettingsSectionHeader(
                symbol: "wand.and.stars",
                title: "Text transforms",
                description: "Operate on the current text selection in any app."
            )
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

    private var keysSection: some View {
        Section {
            ShortcutRecorderField(
                title: "Proofread",
                description: "Mechanical fixes: spelling, punctuation, capitalisation.",
                icon: "checkmark.seal.fill",
                tint: Theme.Tone.success.color(for: colorScheme),
                value: appState.config.shortcuts.proofread,
                defaultValue: "ctrl+shift+g",
                conflicts: conflicts(excluding: "Proofread"),
                onCommit: { v in
                    appState.config.shortcuts.proofread = v
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "proofread", value: v)
                }
            )
            ShortcutRecorderField(
                title: "Rewrite",
                description: "Smooths sentences while preserving meaning.",
                icon: "pencil.and.scribble",
                tint: .blue,
                value: appState.config.shortcuts.rewrite,
                defaultValue: "ctrl+shift+r",
                conflicts: conflicts(excluding: "Rewrite"),
                onCommit: { v in
                    appState.config.shortcuts.rewrite = v
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "rewrite", value: v)
                }
            )
            ShortcutRecorderField(
                title: "Prompt engineer",
                description: "Turns the selection into a structured prompt.",
                icon: "sparkles",
                tint: Theme.Brand.sky,
                value: appState.config.shortcuts.promptEngineer,
                defaultValue: "ctrl+shift+p",
                conflicts: conflicts(excluding: "Prompt engineer"),
                onCommit: { v in
                    appState.config.shortcuts.promptEngineer = v
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "prompt_engineer", value: v)
                }
            )

            InlineNotice(
                kind: .info,
                text: "Click a field and press the new combination. Changes bind immediately — no restart."
            )
        } header: {
            SettingsSectionHeader(symbol: "command", title: "Keybindings")
        }
    }

    // MARK: - Behavior

    private var behaviorSection: some View {
        Section {
            Toggle("Paste result over the selection", isOn: Binding(
                get: { appState.config.shortcuts.pasteResult },
                set: { v in
                    appState.config.shortcuts.pasteResult = v
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "paste_result", value: v)
                }
            ))
            .help("When a transform finishes, the corrected text replaces your selection in place. It is always copied to the clipboard too, so nothing is ever lost.")
        } header: {
            SettingsSectionHeader(
                symbol: "arrow.triangle.2.circlepath",
                title: "Result delivery",
                description: "What happens with the transformed text."
            )
        }
    }

    // MARK: - Cheatsheet

    private var cheatsheetSection: some View {
        Section {
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
                if appState.config.tts.enabled {
                    Divider()
                    cheatRow(label: "Read selection aloud",   keys: KeyboardGlyph.tokens(for: appState.config.tts.speakShortcut))
                    cheatRow(label: "Stop speaking",           keys: ["⎋"])
                }
                Divider()
                cheatRow(label: "Open Settings",          keys: ["⌘", ","])
                cheatRow(label: "Restart Service",        keys: ["⌘", "⇧", "R"])
                cheatRow(label: "Check for Updates",      keys: ["⌘", "⇧", "U"])
                cheatRow(label: "Quit",                    keys: ["⌘", "Q"])
            }
        } header: {
            SettingsSectionHeader(
                symbol: "keyboard",
                title: "Cheatsheet",
                description: "Every shortcut Local Whisper currently responds to."
            )
        }
    }

    private var triggerKeys: [String] {
        // Trigger keys are physical key sides, not standard modifier shortcuts,
        // so render them with the side qualifier next to the symbol.
        switch appState.config.hotkey.key {
        case "alt_r":   return ["⌥", "Right"]
        case "alt_l":   return ["⌥", "Left"]
        case "ctrl_r":  return ["⌃", "Right"]
        case "ctrl_l":  return ["⌃", "Left"]
        case "cmd_r":   return ["⌘", "Right"]
        case "cmd_l":   return ["⌘", "Left"]
        case "shift_r": return ["⇧", "Right"]
        case "shift_l": return ["⇧", "Left"]
        case "caps_lock": return ["⇪"]
        default:        return [appState.config.hotkey.key.uppercased()]
        }
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
