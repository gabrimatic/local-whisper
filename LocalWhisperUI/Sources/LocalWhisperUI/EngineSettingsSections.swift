import SwiftUI

// MARK: - Per-engine settings sections
//
// Split out of TranscriptionPanel so the panel can focus on model management
// and stay under the 700-line guideline. Each section owns a single engine's
// knobs and is rendered by TranscriptionPanel below the active engine card.

// MARK: - Parakeet-TDT

struct ParakeetSection: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Section {
            LabeledContent("Model") {
                DeferredTextField(
                    label: "Model",
                    initialValue: appState.config.parakeet.model
                ) { value in
                    appState.config.parakeet.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }
            .help("Hugging Face model ID. Use an mlx-community/parakeet-* checkpoint.")

            RestartNote()

            DisclosureGroup("Chunking") {
                LabeledContent("Chunk duration") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.parakeet.chunkDuration },
                            set: { v in
                                appState.config.parakeet.chunkDuration = v
                                appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "chunk_duration", value: v)
                            }
                        ), in: 0...600, step: 15)
                        .labelsHidden()
                        Text(appState.config.parakeet.chunkDuration <= 0 ? "Off" : "\(Int(appState.config.parakeet.chunkDuration))s")
                            .monoStat(width: 60)
                    }
                }
                .help("Split long audio into overlapping windows. 0 disables chunking (requires local attention for very long audio). Default 120s.")

                LabeledContent("Overlap") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.parakeet.overlapDuration },
                            set: { v in
                                appState.config.parakeet.overlapDuration = v
                                appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "overlap_duration", value: v)
                            }
                        ), in: 0...60, step: 5)
                        .labelsHidden()
                        Text("\(Int(appState.config.parakeet.overlapDuration))s")
                            .monoStat(width: 60)
                    }
                }
                .help("Overlap between consecutive chunks. Default 15s.")
            }

            DisclosureGroup("Decoding") {
                Picker("Strategy", selection: Binding(
                    get: { appState.config.parakeet.decoding },
                    set: { v in
                        appState.config.parakeet.decoding = v
                        appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "decoding", value: v)
                    }
                )) {
                    Text("Greedy (fast)").tag("greedy")
                    Text("Beam (slower, slight quality gain)").tag("beam")
                }
                .help("Greedy picks the top token at each step. Beam explores multiple hypotheses.")

                if appState.config.parakeet.decoding == "beam" {
                    LabeledContent("Beam size") {
                        HStack {
                            Stepper("", value: Binding(
                                get: { appState.config.parakeet.beamSize },
                                set: { v in
                                    appState.config.parakeet.beamSize = v
                                    appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "beam_size", value: v)
                                }
                            ), in: 1...16, step: 1)
                            .labelsHidden()
                            Text("\(appState.config.parakeet.beamSize)")
                                .monoStat(width: 44)
                        }
                    }

                    LabeledContent("Length penalty") {
                        HStack {
                            Slider(value: Binding(
                                get: { appState.config.parakeet.lengthPenalty },
                                set: { v in
                                    appState.config.parakeet.lengthPenalty = v
                                    appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "length_penalty", value: v)
                                }
                            ), in: 0...1, step: 0.01)
                            Text(String(format: "%.3f", appState.config.parakeet.lengthPenalty))
                                .monoStat(width: 60)
                        }
                    }

                    LabeledContent("Patience") {
                        HStack {
                            Slider(value: Binding(
                                get: { appState.config.parakeet.patience },
                                set: { v in
                                    appState.config.parakeet.patience = v
                                    appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "patience", value: v)
                                }
                            ), in: 1...10, step: 0.1)
                            Text(String(format: "%.1f", appState.config.parakeet.patience))
                                .monoStat(width: 44)
                        }
                    }

                    LabeledContent("Duration reward") {
                        HStack {
                            Slider(value: Binding(
                                get: { appState.config.parakeet.durationReward },
                                set: { v in
                                    appState.config.parakeet.durationReward = v
                                    appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "duration_reward", value: v)
                                }
                            ), in: 0...1, step: 0.01)
                            Text(String(format: "%.2f", appState.config.parakeet.durationReward))
                                .monoStat(width: 44)
                        }
                    }
                    .help("<0.5 favors token logprobs, >0.5 favors duration logprobs. Default 0.67.")
                }

                LabeledContent("Timeout") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.parakeet.timeout },
                            set: { v in
                                appState.config.parakeet.timeout = v
                                appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "timeout", value: v)
                            }
                        ), in: 0...600, step: 10)
                        .labelsHidden()
                        Text(appState.config.parakeet.timeout == 0 ? "Unlimited" : "\(Int(appState.config.parakeet.timeout))s")
                            .monoStat(width: 70)
                    }
                }
                .help("Maximum seconds to wait for transcription. 0 = no limit.")
            }

            DisclosureGroup("Advanced") {
                Toggle("Local attention", isOn: Binding(
                    get: { appState.config.parakeet.localAttention },
                    set: { v in
                        appState.config.parakeet.localAttention = v
                        appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "local_attention", value: v)
                    }
                ))
                .help("Reduces peak memory for very long unchunked audio. Leave off unless chunk duration is 0.")

                if appState.config.parakeet.localAttention {
                    LabeledContent("Context size") {
                        HStack {
                            Stepper("", value: Binding(
                                get: { appState.config.parakeet.localAttentionContextSize },
                                set: { v in
                                    appState.config.parakeet.localAttentionContextSize = v
                                    appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "local_attention_context_size", value: v)
                                }
                            ), in: 64...2048, step: 64)
                            .labelsHidden()
                            Text("\(appState.config.parakeet.localAttentionContextSize)")
                                .monoStat(width: 60)
                        }
                    }
                }
            }
        } header: {
            SettingsSectionHeader(
                symbol: "waveform.badge.mic",
                title: "Parakeet-TDT v3 settings",
                description: "Tuning knobs for the active engine."
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
                title: "Qwen3-ASR settings",
                description: "Tuning knobs for the active engine."
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
                title: "WhisperKit settings",
                description: "Posts 30-second clips to a local server. Supports many languages."
            )
        }
    }
}
