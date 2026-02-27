import SwiftUI
import AppKit

// TextEditor variant for the WhisperKit custom prompt.
private struct DeferredTextEditor: View {
    let onCommit: (String) -> Void

    @State private var localValue: String
    @FocusState private var isFocused: Bool

    init(initialValue: String, onCommit: @escaping (String) -> Void) {
        self.onCommit = onCommit
        _localValue = State(initialValue: initialValue)
    }

    var body: some View {
        TextEditor(text: $localValue)
            .focused($isFocused)
            .onChange(of: isFocused) { _, focused in
                if !focused { onCommit(localValue) }
            }
    }
}

// MARK: - Advanced settings tab

struct AdvancedSettingsView: View {
    @Environment(AppState.self) private var appState

    @State private var ollamaModels: [String] = []
    @State private var ollamaFetchError: String? = nil
    @State private var ollamaFetching = false

    var body: some View {
        ScrollView {
            Form {
                audioProcessingSection
                whisperKitSection
                qwen3Section
                ollamaSection
                lmStudioSection
                appleIntelligenceSection
                shortcutsSection
                ttsSection
                storageSection
            }
            .formStyle(.grouped)
            .onAppear {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                    NSApp.keyWindow?.makeFirstResponder(nil)
                }
            }
        }
    }

    // MARK: - Audio Processing

    private var audioProcessingSection: some View {
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
            .help("Adjusts recording volume to a consistent level. Target RMS 0.05, max +10dB gain")

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

    // MARK: - WhisperKit

    private var whisperKitSection: some View {
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

    // MARK: - Qwen3-ASR

    private var qwen3Section: some View {
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

    // MARK: - Ollama

    private var ollamaSection: some View {
        Section("Ollama") {
            LabeledContent("URL") {
                DeferredTextField(
                    label: "URL",
                    initialValue: appState.config.ollama.url
                ) { value in
                    appState.config.ollama.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Check URL") {
                DeferredTextField(
                    label: "http://localhost:11434/",
                    initialValue: appState.config.ollama.checkUrl
                ) { value in
                    appState.config.ollama.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "check_url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Model") {
                HStack(spacing: 6) {
                    if !ollamaModels.isEmpty {
                        Picker("", selection: Binding(
                            get: { appState.config.ollama.model },
                            set: { newValue in
                                appState.config.ollama.model = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: newValue)
                            }
                        )) {
                            ForEach(ollamaModels, id: \.self) { model in
                                Text(model).tag(model)
                            }
                        }
                        .frame(maxWidth: 220)
                    } else {
                        DeferredTextField(
                            label: "Model",
                            initialValue: appState.config.ollama.model
                        ) { value in
                            appState.config.ollama.model = value
                            appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: value)
                        }
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 220)
                    }
                    Button(ollamaFetching ? "Fetching…" : "Fetch Models") {
                        Task { await fetchOllamaModels() }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(ollamaFetching)
                }
            }

            if let error = ollamaFetchError {
                HStack {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            LabeledContent("Context window") {
                DeferredIntTextField(
                    label: "0 = default",
                    initialValue: appState.config.ollama.numCtx
                ) { value in
                    appState.config.ollama.numCtx = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "num_ctx", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 100)
            }
            .help("Number of tokens the model can hold in context at once. 0 uses the model default. Larger values use more RAM.")

            LabeledContent("Keep alive") {
                DeferredTextField(
                    label: "e.g. 60m",
                    initialValue: appState.config.ollama.keepAlive
                ) { value in
                    appState.config.ollama.keepAlive = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "keep_alive", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 100)
            }
            .help("How long Ollama keeps the model loaded after the last request. Examples: 30s, 5m, 1h")

            LabeledContent("Max predict") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.ollama.maxPredict },
                        set: { v in appState.config.ollama.maxPredict = v; appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "max_predict", value: v) }
                    ), in: 0...32000, step: 100)
                    Text(appState.config.ollama.maxPredict == 0 ? "Default" : "\(appState.config.ollama.maxPredict)")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 60, alignment: .trailing)
                }
            }
            .help("Maximum number of tokens to generate. 0 uses the model default. Limits how long the grammar-corrected output can be.")

            LabeledContent("Max characters") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.ollama.maxChars },
                        set: { v in appState.config.ollama.maxChars = v; appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "max_chars", value: v) }
                    ), in: 0...50000, step: 500)
                    Text(appState.config.ollama.maxChars == 0 ? "Unlimited" : "\(appState.config.ollama.maxChars)")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }
            .help("Transcriptions longer than this are not sent for grammar correction. 0 means no limit.")

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.ollama.timeout },
                        set: { v in appState.config.ollama.timeout = v; appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "timeout", value: v) }
                    ), in: 0...300, step: 5)
                    Text(appState.config.ollama.timeout == 0 ? "Unlimited" : "\(Int(appState.config.ollama.timeout))s")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }

            Toggle("Unload model on quit", isOn: Binding(
                get: { appState.config.ollama.unloadOnExit },
                set: { v in appState.config.ollama.unloadOnExit = v; appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "unload_on_exit", value: v) }
            ))
            .help("Sends a keep_alive=0 request to Ollama when the app quits, freeing RAM immediately")
        }
    }

    // MARK: - LM Studio

    private var lmStudioSection: some View {
        Section("LM Studio") {
            LabeledContent("URL") {
                DeferredTextField(
                    label: "URL",
                    initialValue: appState.config.lmStudio.url
                ) { value in
                    appState.config.lmStudio.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Check URL") {
                DeferredTextField(
                    label: "http://localhost:1234/",
                    initialValue: appState.config.lmStudio.checkUrl
                ) { value in
                    appState.config.lmStudio.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "check_url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Model") {
                DeferredTextField(
                    label: "Model",
                    initialValue: appState.config.lmStudio.model
                ) { value in
                    appState.config.lmStudio.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Max characters") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.lmStudio.maxChars },
                        set: { v in appState.config.lmStudio.maxChars = v; appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "max_chars", value: v) }
                    ), in: 0...50000, step: 500)
                    Text(appState.config.lmStudio.maxChars == 0 ? "Unlimited" : "\(appState.config.lmStudio.maxChars)")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }
            .help("Transcriptions longer than this are not sent for grammar correction. 0 means no limit.")

            LabeledContent("Max tokens") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.lmStudio.maxTokens },
                        set: { v in appState.config.lmStudio.maxTokens = v; appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "max_tokens", value: v) }
                    ), in: 0...32000, step: 100)
                    Text(appState.config.lmStudio.maxTokens == 0 ? "Default" : "\(appState.config.lmStudio.maxTokens)")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 60, alignment: .trailing)
                }
            }
            .help("Maximum tokens to generate in the response. 0 uses the model default.")

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.lmStudio.timeout },
                        set: { v in appState.config.lmStudio.timeout = v; appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "timeout", value: v) }
                    ), in: 0...300, step: 5)
                    Text(appState.config.lmStudio.timeout == 0 ? "Unlimited" : "\(Int(appState.config.lmStudio.timeout))s")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }
        }
    }

    // MARK: - Apple Intelligence

    private var appleIntelligenceSection: some View {
        Section("Apple Intelligence") {
            LabeledContent("Max characters") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.appleIntelligence.maxChars },
                        set: { v in
                            appState.config.appleIntelligence.maxChars = v
                            appState.ipcClient?.sendConfigUpdate(section: "apple_intelligence", key: "max_chars", value: v)
                        }
                    ), in: 0...50000, step: 500)
                    Text(appState.config.appleIntelligence.maxChars == 0 ? "Unlimited" : "\(appState.config.appleIntelligence.maxChars)")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .frame(width: 70, alignment: .trailing)
                }
            }
            .help("Transcriptions longer than this are not sent for grammar correction. 0 means no limit.")

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.appleIntelligence.timeout },
                        set: { v in
                            appState.config.appleIntelligence.timeout = v
                            appState.ipcClient?.sendConfigUpdate(section: "apple_intelligence", key: "timeout", value: v)
                        }
                    ), in: 0...300, step: 5)
                    Text(appState.config.appleIntelligence.timeout == 0 ? "Unlimited" : "\(Int(appState.config.appleIntelligence.timeout))s")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .frame(width: 70, alignment: .trailing)
                }
            }
        }
    }

    // MARK: - Storage

    private var storageSection: some View {
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

    // MARK: - Ollama model fetch

    @MainActor
    private func fetchOllamaModels() async {
        ollamaFetching = true
        ollamaFetchError = nil

        let baseUrl = appState.config.ollama.checkUrl
            .trimmingCharacters(in: .init(charactersIn: "/"))
        let urlString = "\(baseUrl)/api/tags"

        guard let url = URL(string: urlString) else {
            ollamaFetchError = "Invalid check URL: \(urlString)"
            ollamaFetching = false
            return
        }

        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                ollamaFetchError = "Server returned an error. Is Ollama running?"
                ollamaFetching = false
                return
            }

            struct OllamaTagsResponse: Decodable {
                struct Model: Decodable { var name: String }
                var models: [Model]
            }

            let decoded = try JSONDecoder().decode(OllamaTagsResponse.self, from: data)
            let names = decoded.models.map(\.name)
            if names.isEmpty {
                ollamaFetchError = "No models found. Pull one with: ollama pull <model>"
            } else {
                ollamaModels = names
                if !names.contains(appState.config.ollama.model), let first = names.first {
                    appState.config.ollama.model = first
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: first)
                }
            }
        } catch {
            ollamaFetchError = "Could not connect to Ollama: \(error.localizedDescription)"
        }

        ollamaFetching = false
    }

    // MARK: - TTS

    private var ttsSection: some View {
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
                    label: "mlx-community/Qwen3-TTS-...",
                    initialValue: appState.config.qwen3Tts.model
                ) { value in
                    appState.config.qwen3Tts.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "qwen3_tts", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 300)
            }
            .help("Qwen3-TTS model from mlx-community. VoiceDesign variants use free-form voice descriptions. CustomVoice variants use preset speakers.")

            RestartNote()
        }
    }

    // MARK: - Shortcuts

    private var shortcutsSection: some View {
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
}
