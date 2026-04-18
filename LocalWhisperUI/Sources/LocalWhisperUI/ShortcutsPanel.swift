import SwiftUI

// MARK: - Shortcuts panel

struct ShortcutsPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            Form {
                masterSection
                if appState.config.shortcuts.enabled {
                    keysSection
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
            .help("Select text in any app and press a shortcut to proofread, rewrite, or convert it into a prompt.")
        } header: {
            SettingsSectionHeader(
                symbol: "wand.and.stars",
                title: "Text transforms",
                description: "Operate on the current text selection in any app."
            )
        }
    }

    // MARK: - Per-shortcut keys

    private var keysSection: some View {
        Section {
            shortcutRow(
                title: "Proofread",
                description: "Mechanical fixes: spelling, punctuation, capitalisation.",
                icon: "checkmark.seal.fill",
                tint: .green,
                value: appState.config.shortcuts.proofread,
                onCommit: { v in
                    appState.config.shortcuts.proofread = v
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "proofread", value: v)
                }
            )
            shortcutRow(
                title: "Rewrite",
                description: "Smooths sentences while preserving meaning.",
                icon: "pencil.and.scribble",
                tint: .blue,
                value: appState.config.shortcuts.rewrite,
                onCommit: { v in
                    appState.config.shortcuts.rewrite = v
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "rewrite", value: v)
                }
            )
            shortcutRow(
                title: "Prompt engineer",
                description: "Turns the selection into a structured prompt.",
                icon: "sparkles",
                tint: .purple,
                value: appState.config.shortcuts.promptEngineer,
                onCommit: { v in
                    appState.config.shortcuts.promptEngineer = v
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "prompt_engineer", value: v)
                }
            )

            InlineNotice(
                kind: .info,
                text: "Format: modifier+key. Examples: ctrl+shift+g, alt+t, cmd+shift+p."
            )
        } header: {
            SettingsSectionHeader(symbol: "command", title: "Keybindings")
        }
    }

    @ViewBuilder
    private func shortcutRow(title: String, description: String, icon: String, tint: Color, value: String, onCommit: @escaping (String) -> Void) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            HStack(alignment: .top, spacing: Theme.Spacing.s) {
                Image(systemName: icon)
                    .foregroundStyle(tint)
                    .symbolRenderingMode(.hierarchical)
                    .frame(width: 18)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(Theme.Typography.body)
                    Text(description)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: Theme.Spacing.s)
                HStack(spacing: 4) {
                    ForEach(KeyboardGlyph.tokens(for: value), id: \.self) { token in
                        KeyCap(label: token)
                    }
                }
                .accessibilityLabel("Current shortcut: \(KeyboardGlyph.display(value))")
            }
            DeferredTextField(label: "modifier+key", initialValue: value, onCommit: onCommit)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: .infinity)
                .disableAutocorrection(true)
                .labelsHidden()
        }
        .padding(.vertical, 2)
    }

    // MARK: - Cheatsheet

    private var cheatsheetSection: some View {
        Section {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                cheatRow(label: "Start / stop recording", keys: triggerKeys)
                cheatRow(label: "Cancel recording",       keys: ["⎋"])
                cheatRow(label: "Read selection aloud",   keys: KeyboardGlyph.tokens(for: appState.config.tts.speakShortcut))
                cheatRow(label: "Stop speaking",           keys: ["⎋"])
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
