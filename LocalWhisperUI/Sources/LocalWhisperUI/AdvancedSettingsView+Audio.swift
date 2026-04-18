import SwiftUI

extension AdvancedSettingsView {
    var audioProcessingSection: some View {
        Section("Audio Processing") {
            Toggle("Voice activity detection", isOn: Binding(
                get: { appState.config.audio.vadEnabled },
                set: { newValue in
                    appState.config.audio.vadEnabled = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "audio", key: "vad_enabled", value: newValue)
                }
            ))
            .help("Detects when speech is present and trims silence from recordings using adaptive RMS thresholding")

            Toggle("Noise reduction", isOn: Binding(
                get: { appState.config.audio.noiseReduction },
                set: { newValue in
                    appState.config.audio.noiseReduction = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "audio", key: "noise_reduction", value: newValue)
                }
            ))
            .help("Applies spectral gating to reduce background noise before transcription")

            Toggle("Normalize audio", isOn: Binding(
                get: { appState.config.audio.normalizeAudio },
                set: { newValue in
                    appState.config.audio.normalizeAudio = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "audio", key: "normalize_audio", value: newValue)
                }
            ))
            .help("Adjusts recording volume to a consistent level. Target RMS 0.05. Primary cap +10dB; if a recording is still below −10dBFS an adaptive stage adds up to another +6dB with clip-guard.")

            LabeledContent("Pre-buffer") {
                HStack {
                    Slider(
                        value: Binding(
                            get: { appState.config.audio.preBuffer },
                            set: { newValue in
                                appState.config.audio.preBuffer = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "audio", key: "pre_buffer", value: newValue)
                            }
                        ),
                        in: 0...1,
                        step: 0.05
                    )
                    Text(String(format: "%.2fs", appState.config.audio.preBuffer))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, alignment: .trailing)
                }
            }
            .help("Audio captured before you press the hotkey, so the start of your speech is never cut off. 0 disables.")

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
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 40, alignment: .trailing)
                }
            }
            .help("Recordings shorter than this are discarded as accidental taps")

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
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, alignment: .trailing)
                }
            }
            .help("Recordings quieter than this RMS energy are discarded. Raise if you get false positives from ambient noise.")

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
        }
    }
}
