import SwiftUI

extension AdvancedSettingsView {
    var whisperKitSection: some View {
        Section("WhisperKit") {
            LabeledContent("Server URL") {
                DeferredTextField(
                    label: "URL",
                    initialValue: appState.config.whisper.url
                ) { value in
                    appState.config.whisper.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Check URL") {
                DeferredTextField(
                    label: "http://localhost:50060/",
                    initialValue: appState.config.whisper.checkUrl
                ) { value in
                    appState.config.whisper.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "check_url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            RestartNote()

            LabeledContent("Model") {
                DeferredTextField(
                    label: "Model",
                    initialValue: appState.config.whisper.model
                ) { value in
                    appState.config.whisper.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            Picker("Language", selection: Binding(
                get: { appState.config.whisper.language },
                set: { newValue in
                    appState.config.whisper.language = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "language", value: newValue)
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

            LabeledContent("Temperature") {
                HStack {
                    Slider(
                        value: Binding(
                            get: { appState.config.whisper.temperature },
                            set: { newValue in
                                appState.config.whisper.temperature = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "temperature", value: newValue)
                            }
                        ),
                        in: 0...1,
                        step: 0.05
                    )
                    Text(String(format: "%.2f", appState.config.whisper.temperature))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, alignment: .trailing)
                }
            }
            .help("Sampling temperature. Higher values make output more random. Default 0.0")

            LabeledContent("Compression ratio threshold") {
                HStack {
                    Slider(
                        value: Binding(
                            get: { appState.config.whisper.compressionRatioThreshold },
                            set: { newValue in
                                appState.config.whisper.compressionRatioThreshold = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "compression_ratio_threshold", value: newValue)
                            }
                        ),
                        in: 1...5,
                        step: 0.1
                    )
                    Text(String(format: "%.1f", appState.config.whisper.compressionRatioThreshold))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, alignment: .trailing)
                }
            }
            .help("Segments with compression ratio above this are filtered as likely repetitive or hallucinated. Lower values filter more aggressively. Default 2.4")

            LabeledContent("No-speech threshold") {
                HStack {
                    Slider(
                        value: Binding(
                            get: { appState.config.whisper.noSpeechThreshold },
                            set: { newValue in
                                appState.config.whisper.noSpeechThreshold = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "no_speech_threshold", value: newValue)
                            }
                        ),
                        in: 0...1,
                        step: 0.05
                    )
                    Text(String(format: "%.2f", appState.config.whisper.noSpeechThreshold))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, alignment: .trailing)
                }
            }
            .help("Segments with no-speech probability above this threshold are filtered out. Default 0.6")

            LabeledContent("Log probability threshold") {
                HStack {
                    Slider(
                        value: Binding(
                            get: { appState.config.whisper.logprobThreshold },
                            set: { newValue in
                                appState.config.whisper.logprobThreshold = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "logprob_threshold", value: newValue)
                            }
                        ),
                        in: -2...0,
                        step: 0.05
                    )
                    Text(String(format: "%.2f", appState.config.whisper.logprobThreshold))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, alignment: .trailing)
                }
            }
            .help("Segments with average log probability below this are filtered. More negative = less filtering. Default -1.0")

            Stepper(
                "Temperature fallback count: \(appState.config.whisper.temperatureFallbackCount)",
                value: Binding(
                    get: { appState.config.whisper.temperatureFallbackCount },
                    set: { newValue in
                        appState.config.whisper.temperatureFallbackCount = newValue
                        appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "temperature_fallback_count", value: newValue)
                    }
                ),
                in: 1...10
            )
            .help("How many times to retry with a higher temperature when the initial decode is filtered. Default 5")

            Picker("Prompt preset", selection: Binding(
                get: { appState.config.whisper.promptPreset },
                set: { newValue in
                    appState.config.whisper.promptPreset = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "prompt_preset", value: newValue)
                }
            )) {
                Text("None").tag("none")
                Text("Technical").tag("technical")
                Text("Dictation").tag("dictation")
                Text("Custom").tag("custom")
            }
            .help("Vocabulary hint sent to WhisperKit to improve recognition of specific terms")

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

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.whisper.timeout },
                        set: { v in
                            appState.config.whisper.timeout = v
                            appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "timeout", value: v)
                        }
                    ), in: 0...300, step: 5)
                    Text(appState.config.whisper.timeout == 0 ? "Unlimited" : "\(Int(appState.config.whisper.timeout))s")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }
            .help("Maximum seconds to wait for a transcription response from the WhisperKit server. 0 means no limit.")
        }
    }

    var qwen3Section: some View {
        Section("Qwen3-ASR") {
            LabeledContent("Model") {
                DeferredTextField(
                    label: "Model",
                    initialValue: appState.config.qwen3Asr.model
                ) { value in
                    appState.config.qwen3Asr.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }
            .help("Hugging Face model ID for Qwen3-ASR. Must be an MLX-quantized variant.")
            RestartNote()

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

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.qwen3Asr.timeout },
                        set: { v in
                            appState.config.qwen3Asr.timeout = v
                            appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "timeout", value: v)
                        }
                    ), in: 0...600, step: 10)
                    Text(appState.config.qwen3Asr.timeout == 0 ? "Unlimited" : "\(Int(appState.config.qwen3Asr.timeout))s")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }
            .help("Maximum seconds to wait for Qwen3-ASR to finish. 0 means no limit. Long audio may take more time.")

            LabeledContent("Prefill step size") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.qwen3Asr.prefillStepSize },
                        set: { v in
                            appState.config.qwen3Asr.prefillStepSize = v
                            appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "prefill_step_size", value: v)
                        }
                    ), in: 512...16384, step: 512)
                    Text("\(appState.config.qwen3Asr.prefillStepSize)")
                        .font(.system(size: 12, design: .monospaced)).foregroundStyle(.secondary).frame(width: 60, alignment: .trailing)
                }
            }
            .help("Controls audio encoding batch size for MLX on Apple Silicon. Higher values process audio faster but use more memory. Default 4096.")

            LabeledContent("Temperature") {
                HStack {
                    Slider(
                        value: Binding(
                            get: { appState.config.qwen3Asr.temperature },
                            set: { newValue in
                                appState.config.qwen3Asr.temperature = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "temperature", value: newValue)
                            }
                        ),
                        in: 0...1,
                        step: 0.05
                    )
                    Text(String(format: "%.2f", appState.config.qwen3Asr.temperature))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, alignment: .trailing)
                }
            }
            .help("Sampling temperature. 0.0 is greedy/deterministic. Higher values increase randomness. Default 0.0.")

            LabeledContent("Top P") {
                HStack {
                    Slider(
                        value: Binding(
                            get: { appState.config.qwen3Asr.topP },
                            set: { newValue in
                                appState.config.qwen3Asr.topP = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "top_p", value: newValue)
                            }
                        ),
                        in: 0...1,
                        step: 0.05
                    )
                    Text(String(format: "%.2f", appState.config.qwen3Asr.topP))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, alignment: .trailing)
                }
            }
            .help("Nucleus sampling threshold. Only active when temperature > 0. Default 1.0 (disabled).")

            LabeledContent("Top K") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.qwen3Asr.topK },
                        set: { v in
                            appState.config.qwen3Asr.topK = v
                            appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "top_k", value: v)
                        }
                    ), in: 0...200, step: 1)
                    Text(appState.config.qwen3Asr.topK == 0 ? "Off" : "\(appState.config.qwen3Asr.topK)")
                        .font(.system(size: 12, design: .monospaced)).foregroundStyle(.secondary).frame(width: 44, alignment: .trailing)
                }
            }
            .help("Top-K sampling. Only active when temperature > 0. 0 disables. Default 0.")

            LabeledContent("Repetition context") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.qwen3Asr.repetitionContextSize },
                        set: { v in
                            appState.config.qwen3Asr.repetitionContextSize = v
                            appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "repetition_context_size", value: v)
                        }
                    ), in: 1...500, step: 10)
                    Text("\(appState.config.qwen3Asr.repetitionContextSize)")
                        .font(.system(size: 12, design: .monospaced)).foregroundStyle(.secondary).frame(width: 44, alignment: .trailing)
                }
            }
            .help("Number of recent tokens considered when applying the repetition penalty. Default 100.")

            LabeledContent("Repetition penalty") {
                HStack {
                    Slider(
                        value: Binding(
                            get: { appState.config.qwen3Asr.repetitionPenalty },
                            set: { newValue in
                                appState.config.qwen3Asr.repetitionPenalty = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "repetition_penalty", value: newValue)
                            }
                        ),
                        in: 1.0...2.0,
                        step: 0.05
                    )
                    Text(String(format: "%.2f", appState.config.qwen3Asr.repetitionPenalty))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 44, alignment: .trailing)
                }
            }
            .help("Penalty applied to repeated tokens to reduce looping. 1.0 disables the penalty. Default 1.2.")

            LabeledContent("Chunk duration") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.qwen3Asr.chunkDuration },
                        set: { v in
                            appState.config.qwen3Asr.chunkDuration = v
                            appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "chunk_duration", value: v)
                        }
                    ), in: 60...3600, step: 60)
                    Text("\(Int(appState.config.qwen3Asr.chunkDuration))s")
                        .font(.system(size: 12, design: .monospaced)).foregroundStyle(.secondary).frame(width: 60, alignment: .trailing)
                }
            }
            .help("Maximum chunk size in seconds for very long audio. Default 1200s (20 minutes).")
        }
    }
}
