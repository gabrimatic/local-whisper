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
                            appState.ipcClient?.sendConfigUpdate(section: "grammar", key: "enabled", value: newValue)
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
                            get: { appState.config.qwen3Tts.speaker },
                            set: { newValue in
                                appState.config.qwen3Tts.speaker = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_tts", key: "speaker", value: newValue)
                            }
                        )) {
                            Text("Aiden (American male)").tag("Aiden")
                            Text("Ryan (English male)").tag("Ryan")
                            Text("Serena (Chinese female)").tag("Serena")
                            Text("Vivian (Chinese female)").tag("Vivian")
                            Text("Ono_Anna (Japanese female)").tag("Ono_Anna")
                            Text("Sohee (Korean female)").tag("Sohee")
                            Text("Uncle_Fu (Chinese male)").tag("Uncle_Fu")
                            Text("Dylan (Beijing male)").tag("Dylan")
                            Text("Eric (Sichuan male)").tag("Eric")
                        }

                        Picker("Language", selection: Binding(
                            get: { appState.config.qwen3Tts.language },
                            set: { newValue in
                                appState.config.qwen3Tts.language = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_tts", key: "language", value: newValue)
                            }
                        )) {
                            Text("Auto-detect").tag("Auto")
                            Text("English").tag("English")
                            Text("Chinese").tag("Chinese")
                            Text("Japanese").tag("Japanese")
                            Text("Korean").tag("Korean")
                            Text("German").tag("German")
                            Text("French").tag("French")
                            Text("Spanish").tag("Spanish")
                            Text("Italian").tag("Italian")
                            Text("Portuguese").tag("Portuguese")
                            Text("Russian").tag("Russian")
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
