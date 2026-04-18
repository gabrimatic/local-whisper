import SwiftUI

// MARK: - Recording panel

struct RecordingPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            Form {
                triggerSection
                audioSection
                durationSection
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Trigger

    private var triggerSection: some View {
        Section {
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

            LabeledContent("Double-tap window") {
                HStack {
                    Slider(value: Binding(
                        get: { appState.config.hotkey.doubleTapThreshold },
                        set: { newValue in
                            appState.config.hotkey.doubleTapThreshold = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "hotkey", key: "double_tap_threshold", value: newValue)
                        }
                    ), in: 0.1...1.0, step: 0.05)
                    Text(String(format: "%.2fs", appState.config.hotkey.doubleTapThreshold))
                        .monoStat(width: 48)
                }
            }
            .help("Maximum time between two taps to register as a double-tap. Anything longer becomes hold-to-record.")

            RestartNote()
        } header: {
            SettingsSectionHeader(symbol: "hand.tap.fill", title: "Trigger", description: "Press to start. Press again, or release in hold mode, to stop.")
        }
    }

    // MARK: - Audio

    private var audioSection: some View {
        Section {
            Toggle("Voice activity detection", isOn: Binding(
                get: { appState.config.audio.vadEnabled },
                set: { newValue in
                    appState.config.audio.vadEnabled = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "audio", key: "vad_enabled", value: newValue)
                }
            ))
            .help("Detects speech and trims silence using adaptive RMS thresholding.")

            Toggle("Noise reduction", isOn: Binding(
                get: { appState.config.audio.noiseReduction },
                set: { newValue in
                    appState.config.audio.noiseReduction = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "audio", key: "noise_reduction", value: newValue)
                }
            ))
            .help("Spectral gating to reduce constant background noise.")

            Toggle("Normalize volume", isOn: Binding(
                get: { appState.config.audio.normalizeAudio },
                set: { newValue in
                    appState.config.audio.normalizeAudio = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "audio", key: "normalize_audio", value: newValue)
                }
            ))
            .help("Brings each recording to a consistent loudness so quiet speech transcribes as well as loud.")

            LabeledContent("Pre-buffer") {
                HStack {
                    Slider(value: Binding(
                        get: { appState.config.audio.preBuffer },
                        set: { newValue in
                            appState.config.audio.preBuffer = newValue
                            appState.ipcClient?.sendConfigUpdate(section: "audio", key: "pre_buffer", value: newValue)
                        }
                    ), in: 0...1, step: 0.05)
                    Text(String(format: "%.2fs", appState.config.audio.preBuffer))
                        .monoStat(width: 48)
                }
            }
            .help("Audio captured before you press the hotkey, so the start of your speech is never cut off. 0 disables.")
        } header: {
            SettingsSectionHeader(symbol: "waveform.path", title: "Audio cleanup", description: "Pre-processing applied before the engine sees the audio.")
        }
    }

    // MARK: - Duration

    private var durationSection: some View {
        Section {
            LabeledContent("Min duration") {
                HStack {
                    Slider(value: Binding(
                        get: { appState.config.audio.minDuration },
                        set: { v in
                            appState.config.audio.minDuration = v
                            appState.ipcClient?.sendConfigUpdate(section: "audio", key: "min_duration", value: v)
                        }
                    ), in: 0...5, step: 0.5)
                    Text(String(format: "%.1fs", appState.config.audio.minDuration))
                        .monoStat(width: 44)
                }
            }
            .help("Recordings shorter than this are discarded as accidental taps.")

            LabeledContent("Min RMS level") {
                HStack {
                    Slider(value: Binding(
                        get: { appState.config.audio.minRms },
                        set: { v in
                            appState.config.audio.minRms = v
                            appState.ipcClient?.sendConfigUpdate(section: "audio", key: "min_rms", value: v)
                        }
                    ), in: 0...0.05, step: 0.001)
                    Text(String(format: "%.3f", appState.config.audio.minRms))
                        .monoStat(width: 48)
                }
            }
            .help("Recordings quieter than this are discarded. Raise if ambient noise triggers false positives.")

            Stepper(
                "Max duration: \(appState.config.audio.maxDuration == 0 ? "unlimited" : "\(appState.config.audio.maxDuration)s")",
                value: Binding(
                    get: { appState.config.audio.maxDuration },
                    set: { v in
                        appState.config.audio.maxDuration = v
                        appState.ipcClient?.sendConfigUpdate(section: "audio", key: "max_duration", value: v)
                    }
                ),
                in: 0...600, step: 30
            )
            .help("Recording stops automatically after this many seconds. 0 means unlimited.")
        } header: {
            SettingsSectionHeader(symbol: "ruler", title: "Duration limits", description: "Guards against accidental taps and runaway sessions.")
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
