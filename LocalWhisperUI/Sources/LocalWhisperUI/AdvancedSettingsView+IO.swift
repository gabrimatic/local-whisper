import SwiftUI

extension AdvancedSettingsView {
    var shortcutsSection: some View {
        Section("Keyboard Shortcuts") {
            LabeledContent("Proofread") {
                DeferredTextField(
                    label: "e.g. ctrl+shift+g",
                    initialValue: appState.config.shortcuts.proofread
                ) { value in
                    appState.config.shortcuts.proofread = value
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "proofread", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 180)
            }
            .help("Key combination to proofread selected text. Format: modifier+key, e.g. ctrl+shift+g")

            LabeledContent("Rewrite") {
                DeferredTextField(
                    label: "e.g. ctrl+shift+r",
                    initialValue: appState.config.shortcuts.rewrite
                ) { value in
                    appState.config.shortcuts.rewrite = value
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "rewrite", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 180)
            }
            .help("Key combination to rewrite selected text. Format: modifier+key, e.g. ctrl+shift+r")

            LabeledContent("Prompt engineer") {
                DeferredTextField(
                    label: "e.g. ctrl+shift+p",
                    initialValue: appState.config.shortcuts.promptEngineer
                ) { value in
                    appState.config.shortcuts.promptEngineer = value
                    appState.ipcClient?.sendConfigUpdate(section: "shortcuts", key: "prompt_engineer", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 180)
            }
            .help("Key combination to convert selected text into a prompt engineering instruction. Format: modifier+key, e.g. ctrl+shift+p")
        }
    }

    var ttsSection: some View {
        Section("Text to Speech") {
            LabeledContent("Speak shortcut") {
                DeferredTextField(
                    label: "e.g. alt+t",
                    initialValue: appState.config.tts.speakShortcut
                ) { value in
                    appState.config.tts.speakShortcut = value
                    appState.ipcClient?.sendConfigUpdate(section: "tts", key: "speak_shortcut", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 180)
            }
            .help("Key combination to speak selected text. Format: modifier+key, e.g. alt+t (⌥T)")

            LabeledContent("Model") {
                DeferredTextField(
                    label: "mlx-community/Kokoro-...",
                    initialValue: appState.config.kokoroTts.model
                ) { value in
                    appState.config.kokoroTts.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "kokoro_tts", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 300)
            }
            .help("Kokoro model from mlx-community. The default mlx-community/Kokoro-82M-bf16 runs fully offline after setup.")

            RestartNote()
        }
    }

    var storageSection: some View {
        Section("Storage") {
            LabeledContent("Backup directory") {
                DeferredTextField(
                    label: "~/.whisper",
                    initialValue: appState.config.backup.directory
                ) { value in
                    appState.config.backup.directory = value
                    appState.ipcClient?.sendConfigUpdate(section: "backup", key: "directory", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }
            HStack {
                Image(systemName: "info.circle")
                    .foregroundStyle(.secondary)
                Text("Path where transcription history and audio recordings are stored. Restart required after changing.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
