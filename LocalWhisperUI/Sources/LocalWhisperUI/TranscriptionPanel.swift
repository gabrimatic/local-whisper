import SwiftUI

// MARK: - Transcription panel

struct TranscriptionPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            Form {
                engineSection
                if appState.config.transcription.engine == "qwen3_asr" {
                    Qwen3Section()
                } else if appState.config.transcription.engine == "whisperkit" {
                    WhisperKitSection()
                }
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Engine

    private var engineSection: some View {
        Section {
            Picker("Engine", selection: Binding(
                get: { appState.config.transcription.engine },
                set: { newValue in
                    appState.config.transcription.engine = newValue
                    appState.ipcClient?.sendEngineSwitch(newValue)
                }
            )) {
                Text("Qwen3-ASR (in-process)").tag("qwen3_asr")
                Text("WhisperKit (local server)").tag("whisperkit")
            }
            .pickerStyle(.inline)
            .help("Qwen3-ASR runs fully in-process and handles long audio natively. WhisperKit needs a local server.")
        } header: {
            SettingsSectionHeader(
                symbol: "cpu",
                title: "Engine",
                description: "Speech-to-text model. Switching restarts the service."
            )
        }
    }
}

// MARK: - Qwen3-ASR

struct Qwen3Section: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Section {
            LabeledContent("Model") {
                DeferredTextField(
                    label: "Model",
                    initialValue: appState.config.qwen3Asr.model
                ) { value in
                    appState.config.qwen3Asr.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }
            .help("Hugging Face model ID. Must be an MLX-quantized variant.")

            RestartNote()

            DisclosureGroup("Sampling") {
                LabeledContent("Temperature") {
                    HStack {
                        Slider(value: Binding(
                            get: { appState.config.qwen3Asr.temperature },
                            set: { v in
                                appState.config.qwen3Asr.temperature = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "temperature", value: v)
                            }
                        ), in: 0...1, step: 0.05)
                        Text(String(format: "%.2f", appState.config.qwen3Asr.temperature))
                            .monoStat(width: 44)
                    }
                }
                .help("0.0 is greedy. Higher values increase variation. Default 0.0.")

                LabeledContent("Top P") {
                    HStack {
                        Slider(value: Binding(
                            get: { appState.config.qwen3Asr.topP },
                            set: { v in
                                appState.config.qwen3Asr.topP = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "top_p", value: v)
                            }
                        ), in: 0...1, step: 0.05)
                        Text(String(format: "%.2f", appState.config.qwen3Asr.topP))
                            .monoStat(width: 44)
                    }
                }
                .help("Active when temperature > 0. Default 1.0.")

                LabeledContent("Top K") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.qwen3Asr.topK },
                            set: { v in
                                appState.config.qwen3Asr.topK = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "top_k", value: v)
                            }
                        ), in: 0...200, step: 1)
                        .labelsHidden()
                        Text(appState.config.qwen3Asr.topK == 0 ? "Off" : "\(appState.config.qwen3Asr.topK)")
                            .monoStat(width: 44)
                    }
                }
                .help("Top-K sampling. Active when temperature > 0. 0 disables. Default 0.")
            }

            DisclosureGroup("Decoding") {
                LabeledContent("Repetition penalty") {
                    HStack {
                        Slider(value: Binding(
                            get: { appState.config.qwen3Asr.repetitionPenalty },
                            set: { v in
                                appState.config.qwen3Asr.repetitionPenalty = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "repetition_penalty", value: v)
                            }
                        ), in: 1.0...2.0, step: 0.05)
                        Text(String(format: "%.2f", appState.config.qwen3Asr.repetitionPenalty))
                            .monoStat(width: 44)
                    }
                }
                .help("Penalty for repeated tokens. 1.0 disables. Default 1.2.")

                LabeledContent("Repetition context") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.qwen3Asr.repetitionContextSize },
                            set: { v in
                                appState.config.qwen3Asr.repetitionContextSize = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "repetition_context_size", value: v)
                            }
                        ), in: 1...500, step: 10)
                        .labelsHidden()
                        Text("\(appState.config.qwen3Asr.repetitionContextSize)")
                            .monoStat(width: 44)
                    }
                }
                .help("Tokens of context for the repetition penalty. Default 100.")

                LabeledContent("Chunk duration") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.qwen3Asr.chunkDuration },
                            set: { v in
                                appState.config.qwen3Asr.chunkDuration = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "chunk_duration", value: v)
                            }
                        ), in: 60...3600, step: 60)
                        .labelsHidden()
                        Text("\(Int(appState.config.qwen3Asr.chunkDuration))s")
                            .monoStat(width: 60)
                    }
                }
                .help("Maximum chunk size for very long audio. Default 1200s (20 minutes).")

                LabeledContent("Timeout") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.qwen3Asr.timeout },
                            set: { v in
                                appState.config.qwen3Asr.timeout = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "timeout", value: v)
                            }
                        ), in: 0...600, step: 10)
                        .labelsHidden()
                        Text(appState.config.qwen3Asr.timeout == 0 ? "Unlimited" : "\(Int(appState.config.qwen3Asr.timeout))s")
                            .monoStat(width: 70)
                    }
                }
                .help("Maximum seconds to wait for transcription. 0 = no limit.")
            }
        } header: {
            SettingsSectionHeader(
                symbol: "sparkle",
                title: "Qwen3-ASR",
                description: "MLX-native, English-only, handles long audio in one pass."
            )
        }
    }
}

// MARK: - WhisperKit

struct WhisperKitSection: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Section {
            LabeledContent("Server URL") {
                DeferredTextField(label: "URL", initialValue: appState.config.whisper.url) { value in
                    appState.config.whisper.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }

            LabeledContent("Check URL") {
                DeferredTextField(label: "http://localhost:50060/", initialValue: appState.config.whisper.checkUrl) { value in
                    appState.config.whisper.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "check_url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }

            RestartNote()

            LabeledContent("Model") {
                DeferredTextField(label: "Model", initialValue: appState.config.whisper.model) { value in
                    appState.config.whisper.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }

            Picker("Language", selection: Binding(
                get: { appState.config.whisper.language },
                set: { newValue in
                    appState.config.whisper.language = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "language", value: newValue)
                }
            )) {
                Section("Auto") {
                    Text("Detect from audio").tag("auto")
                }
                Section("Common") {
                    Text("English").tag("en")
                    Text("Spanish").tag("es")
                    Text("French").tag("fr")
                    Text("German").tag("de")
                    Text("Portuguese").tag("pt")
                    Text("Italian").tag("it")
                }
                Section("Other") {
                    Text("Persian").tag("fa")
                    Text("Arabic").tag("ar")
                    Text("Chinese").tag("zh")
                    Text("Japanese").tag("ja")
                    Text("Korean").tag("ko")
                    Text("Russian").tag("ru")
                }
            }

            DisclosureGroup("Decoding") {
                LabeledContent("Temperature") {
                    HStack {
                        Slider(value: Binding(
                            get: { appState.config.whisper.temperature },
                            set: { v in
                                appState.config.whisper.temperature = v
                                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "temperature", value: v)
                            }
                        ), in: 0...1, step: 0.05)
                        Text(String(format: "%.2f", appState.config.whisper.temperature))
                            .monoStat(width: 44)
                    }
                }

                LabeledContent("Compression-ratio threshold") {
                    HStack {
                        Slider(value: Binding(
                            get: { appState.config.whisper.compressionRatioThreshold },
                            set: { v in
                                appState.config.whisper.compressionRatioThreshold = v
                                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "compression_ratio_threshold", value: v)
                            }
                        ), in: 1...5, step: 0.1)
                        Text(String(format: "%.1f", appState.config.whisper.compressionRatioThreshold))
                            .monoStat(width: 44)
                    }
                }
                .help("Filters segments above this ratio as likely repetitive or hallucinated. Default 2.4.")

                LabeledContent("No-speech threshold") {
                    HStack {
                        Slider(value: Binding(
                            get: { appState.config.whisper.noSpeechThreshold },
                            set: { v in
                                appState.config.whisper.noSpeechThreshold = v
                                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "no_speech_threshold", value: v)
                            }
                        ), in: 0...1, step: 0.05)
                        Text(String(format: "%.2f", appState.config.whisper.noSpeechThreshold))
                            .monoStat(width: 44)
                    }
                }
                .help("Filters segments above this no-speech probability. Default 0.6.")

                LabeledContent("Log-probability threshold") {
                    HStack {
                        Slider(value: Binding(
                            get: { appState.config.whisper.logprobThreshold },
                            set: { v in
                                appState.config.whisper.logprobThreshold = v
                                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "logprob_threshold", value: v)
                            }
                        ), in: -2...0, step: 0.05)
                        Text(String(format: "%.2f", appState.config.whisper.logprobThreshold))
                            .monoStat(width: 44)
                    }
                }
                .help("Filters segments below this log-probability. Default -1.0.")

                Stepper("Temperature fallback count: \(appState.config.whisper.temperatureFallbackCount)",
                    value: Binding(
                        get: { appState.config.whisper.temperatureFallbackCount },
                        set: { v in
                            appState.config.whisper.temperatureFallbackCount = v
                            appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "temperature_fallback_count", value: v)
                        }
                    ),
                    in: 1...10
                )
            }

            DisclosureGroup("Vocabulary hints") {
                Picker("Preset", selection: Binding(
                    get: { appState.config.whisper.promptPreset },
                    set: { v in
                        appState.config.whisper.promptPreset = v
                        appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "prompt_preset", value: v)
                    }
                )) {
                    Text("None").tag("none")
                    Text("Technical").tag("technical")
                    Text("Dictation").tag("dictation")
                    Text("Custom").tag("custom")
                }

                if appState.config.whisper.promptPreset == "custom" {
                    LabeledContent("Custom prompt") {
                        DeferredTextEditor(initialValue: appState.config.whisper.prompt) { value in
                            appState.config.whisper.prompt = value
                            appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "prompt", value: value)
                        }
                        .font(.system(size: 12))
                        .frame(height: 60)
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.secondary.opacity(0.3)))
                    }
                }
            }

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.whisper.timeout },
                        set: { v in
                            appState.config.whisper.timeout = v
                            appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "timeout", value: v)
                        }
                    ), in: 0...300, step: 5)
                    .labelsHidden()
                    Text(appState.config.whisper.timeout == 0 ? "Unlimited" : "\(Int(appState.config.whisper.timeout))s")
                        .monoStat(width: 70)
                }
            }
        } header: {
            SettingsSectionHeader(
                symbol: "server.rack",
                title: "WhisperKit",
                description: "Posts 30-second clips to a local server. Supports many languages."
            )
        }
    }
}
