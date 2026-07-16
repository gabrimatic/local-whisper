import SwiftUI

// MARK: - Recording panel

struct RecordingPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        PanelScaffold(
            title: "Recording",
            subtitle: "Trigger key, microphone handling, and audio cleanup."
        ) {
            triggerCard
            audioCard
            durationCard
        }
    }

    // MARK: - Trigger

    private var triggerCard: some View {
        SettingsCard(
            icon: "hand.tap.fill",
            title: "Trigger",
            description: "Press to start. Press again — or release, in hold mode — to stop."
        ) {
            SettingRow(
                title: "Trigger key",
                subtitle: "Double-tap starts a recording; holding past the threshold records until release."
            ) {
                Picker("Trigger key", selection: Binding(
                    get: { appState.config.hotkey.key },
                    set: { newValue in
                        appState.config.hotkey.key = newValue
                        appState.ipcClient?.sendConfigUpdate(section: "hotkey", key: "key", value: newValue)
                    }
                )) {
                    ForEach(HotkeyOption.grouped, id: \.section) { group in
                        Section(group.section) {
                            ForEach(group.options, id: \.tag) { option in
                                Text(option.label).tag(option.tag)
                            }
                        }
                    }
                }
                .pickerStyle(.menu)
                .fixedSize()
            }

            if let conflictNote = triggerConflictNote {
                WideRow {
                    InlineNotice(kind: .warning, text: conflictNote)
                }
            }

            SettingRow(
                title: "Double-tap window",
                subtitle: "Maximum time between two taps to count as a double-tap."
            ) {
                CommitSlider(
                    value: appState.config.hotkey.doubleTapThreshold,
                    in: 0.1...1.0,
                    step: 0.05,
                    onCommit: { newValue in
                        appState.config.hotkey.doubleTapThreshold = newValue
                        appState.ipcClient?.sendConfigUpdate(section: "hotkey", key: "double_tap_threshold", value: newValue)
                    }
                ) { v in
                    Text(String(format: "%.2fs", v)).monoStat(width: 44)
                }
            }

            SettingRow(
                title: "Hold threshold",
                subtitle: "How long the key must stay down before hold-to-record starts. Auto follows the double-tap window."
            ) {
                CommitSlider(
                    value: appState.config.hotkey.holdThreshold,
                    in: 0.0...1.0,
                    step: 0.05,
                    onCommit: { newValue in
                        appState.config.hotkey.holdThreshold = newValue
                        appState.ipcClient?.sendConfigUpdate(section: "hotkey", key: "hold_threshold", value: newValue)
                    }
                ) { v in
                    Text(v <= 0 ? "auto" : String(format: "%.2fs", v)).monoStat(width: 44)
                }
            }
        }
    }

    /// An F-key trigger intercepts its keycode wholesale, silently killing
    /// any transform / TTS combo bound on that key — say so right here.
    private var triggerConflictNote: String? {
        let trigger = appState.config.hotkey.key
        guard ShortcutSpec.functionKeys.contains(trigger) else { return nil }
        let bindings: [(String, String)] = [
            (appState.config.shortcuts.proofread, "Proofread"),
            (appState.config.shortcuts.rewrite, "Rewrite"),
            (appState.config.shortcuts.promptEngineer, "Prompt engineer"),
            (appState.config.tts.speakShortcut, "Read aloud"),
        ]
        let clashing = bindings.filter { combo, _ in
            combo.split(separator: "+").last.map(String.init) == trigger
        }.map(\.1)
        guard !clashing.isEmpty else { return nil }
        return "The \(trigger.uppercased()) trigger intercepts every combo on that key — \(clashing.joined(separator: ", ")) will stop working until rebound in Shortcuts."
    }

    // MARK: - Audio

    private var audioCard: some View {
        SettingsCard(
            icon: "waveform.path",
            title: "Audio cleanup",
            description: "Pre-processing applied before the engine sees the audio."
        ) {
            ToggleRow(
                title: "Voice activity detection",
                subtitle: "Detects speech and trims silence with adaptive thresholding.",
                isOn: appState.config.audio.vadEnabled
            ) { newValue in
                appState.config.audio.vadEnabled = newValue
                appState.ipcClient?.sendConfigUpdate(section: "audio", key: "vad_enabled", value: newValue)
            }

            ToggleRow(
                title: "Noise reduction",
                subtitle: "Spectral gating against constant background noise.",
                isOn: appState.config.audio.noiseReduction
            ) { newValue in
                appState.config.audio.noiseReduction = newValue
                appState.ipcClient?.sendConfigUpdate(section: "audio", key: "noise_reduction", value: newValue)
            }

            ToggleRow(
                title: "Normalize volume",
                subtitle: "Brings every recording to a consistent loudness, so quiet speech transcribes as well as loud.",
                isOn: appState.config.audio.normalizeAudio
            ) { newValue in
                appState.config.audio.normalizeAudio = newValue
                appState.ipcClient?.sendConfigUpdate(section: "audio", key: "normalize_audio", value: newValue)
            }

            SettingRow(
                title: "Pre-buffer",
                subtitle: "Audio captured before you press the hotkey, so your first word is never cut off. 0 disables."
            ) {
                CommitSlider(
                    value: appState.config.audio.preBuffer,
                    in: 0...1,
                    step: 0.05,
                    onCommit: { newValue in
                        appState.config.audio.preBuffer = newValue
                        appState.ipcClient?.sendConfigUpdate(section: "audio", key: "pre_buffer", value: newValue)
                    }
                ) { v in
                    Text(String(format: "%.2fs", v)).monoStat(width: 44)
                }
            }
        }
    }

    // MARK: - Duration

    private var durationCard: some View {
        SettingsCard(
            icon: "ruler",
            title: "Duration limits",
            description: "Guards against accidental taps and runaway sessions."
        ) {
            SettingRow(
                title: "Minimum duration",
                subtitle: "Recordings shorter than this are discarded as accidental taps."
            ) {
                CommitSlider(
                    value: appState.config.audio.minDuration,
                    in: 0...5,
                    step: 0.5,
                    onCommit: { v in
                        appState.config.audio.minDuration = v
                        appState.ipcClient?.sendConfigUpdate(section: "audio", key: "min_duration", value: v)
                    }
                ) { v in
                    Text(String(format: "%.1fs", v)).monoStat(width: 44)
                }
            }

            SettingRow(
                title: "Minimum level",
                subtitle: "Recordings quieter than this RMS level are discarded. Raise it if ambient noise triggers false positives."
            ) {
                CommitSlider(
                    value: appState.config.audio.minRms,
                    in: 0...0.05,
                    step: 0.001,
                    onCommit: { v in
                        appState.config.audio.minRms = v
                        appState.ipcClient?.sendConfigUpdate(section: "audio", key: "min_rms", value: v)
                    }
                ) { v in
                    Text(String(format: "%.3f", v)).monoStat(width: 44)
                }
            }

            SettingRow(
                title: "Maximum duration",
                subtitle: "Recording stops automatically after this long. 0 means unlimited."
            ) {
                StepperRowControl(
                    value: appState.config.audio.maxDuration,
                    range: 0...600,
                    step: 30,
                    display: appState.config.audio.maxDuration == 0 ? "Unlimited" : "\(appState.config.audio.maxDuration)s",
                    displayWidth: 70
                ) { v in
                    appState.config.audio.maxDuration = v
                    appState.ipcClient?.sendConfigUpdate(section: "audio", key: "max_duration", value: v)
                }
            }
        }
    }
}

// MARK: - Hotkey options

private struct HotkeyOption {
    let label: String
    let tag: String

    struct Group {
        let section: String
        let options: [HotkeyOption]
    }

    static let grouped: [Group] = [
        Group(section: "Modifier keys", options: [
            HotkeyOption(label: "Right Option (⌥)",  tag: "alt_r"),
            HotkeyOption(label: "Left Option (⌥)",   tag: "alt_l"),
            HotkeyOption(label: "Right Control (⌃)", tag: "ctrl_r"),
            HotkeyOption(label: "Left Control (⌃)",  tag: "ctrl_l"),
            HotkeyOption(label: "Right Command (⌘)", tag: "cmd_r"),
            HotkeyOption(label: "Left Command (⌘)",  tag: "cmd_l"),
            HotkeyOption(label: "Right Shift (⇧)",   tag: "shift_r"),
            HotkeyOption(label: "Left Shift (⇧)",    tag: "shift_l"),
            HotkeyOption(label: "Caps Lock",         tag: "caps_lock"),
        ]),
        Group(section: "Function keys", options: (1...12).map { n in
            HotkeyOption(label: "F\(n)", tag: "f\(n)")
        }),
    ]
}
