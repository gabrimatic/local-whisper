import SwiftUI

// MARK: - Per-engine settings cards
//
// Split out of TranscriptionPanel so the panel can focus on model management.
// Each card owns a single engine's knobs and is rendered by TranscriptionPanel
// below the engine cards, for the active engine only.

// MARK: - Parakeet-TDT

struct ParakeetSection: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        SettingsCard(
            icon: "waveform.badge.mic",
            title: "Parakeet-TDT v3 settings",
            description: "Tuning knobs for the active engine."
        ) {
            SettingRow(
                title: "Model",
                subtitle: "Hugging Face model ID. Use an mlx-community/parakeet-* checkpoint."
            ) {
                DeferredTextField(
                    label: "Model",
                    initialValue: appState.config.parakeet.model
                ) { value in
                    appState.config.parakeet.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 280)
            }

            WideRow {
                RestartNote()
            }

            WideRow {
                DisclosureGroup("Chunking") {
                    VStack(spacing: 0) {
                        SettingRow(
                            title: "Chunk duration",
                            subtitle: "Split long audio into overlapping windows. 0 disables chunking. Default 120s."
                        ) {
                            StepperRowControl(
                                value: Int(appState.config.parakeet.chunkDuration),
                                range: 0...600,
                                step: 15,
                                display: appState.config.parakeet.chunkDuration <= 0 ? "Off" : "\(Int(appState.config.parakeet.chunkDuration))s",
                                displayWidth: 56
                            ) { v in
                                appState.config.parakeet.chunkDuration = Double(v)
                                appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "chunk_duration", value: Double(v))
                            }
                        }

                        SettingRow(
                            title: "Overlap",
                            subtitle: "Overlap between consecutive chunks. Default 15s."
                        ) {
                            StepperRowControl(
                                value: Int(appState.config.parakeet.overlapDuration),
                                range: 0...60,
                                step: 5,
                                display: "\(Int(appState.config.parakeet.overlapDuration))s",
                                displayWidth: 56
                            ) { v in
                                appState.config.parakeet.overlapDuration = Double(v)
                                appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "overlap_duration", value: Double(v))
                            }
                        }
                    }
                    .padding(.top, Theme.Spacing.xs)
                }
                .font(Theme.Typography.bodyEmphasized)
            }

            WideRow {
                DisclosureGroup("Decoding") {
                    VStack(spacing: 0) {
                        SettingRow(
                            title: "Strategy",
                            subtitle: "Greedy picks the top token at each step. Beam explores multiple hypotheses."
                        ) {
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
                            .pickerStyle(.menu)
                            .fixedSize()
                        }

                        if appState.config.parakeet.decoding == "beam" {
                            SettingRow(title: "Beam size") {
                                StepperRowControl(
                                    value: appState.config.parakeet.beamSize,
                                    range: 1...16,
                                    step: 1,
                                    display: "\(appState.config.parakeet.beamSize)",
                                    displayWidth: 40
                                ) { v in
                                    appState.config.parakeet.beamSize = v
                                    appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "beam_size", value: v)
                                }
                            }

                            SettingRow(title: "Length penalty") {
                                CommitSlider(
                                    value: appState.config.parakeet.lengthPenalty,
                                    in: 0...1,
                                    step: 0.01,
                                    onCommit: { v in
                                        appState.config.parakeet.lengthPenalty = v
                                        appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "length_penalty", value: v)
                                    }
                                ) { v in
                                    Text(String(format: "%.3f", v)).monoStat(width: 48)
                                }
                            }

                            SettingRow(title: "Patience") {
                                CommitSlider(
                                    value: appState.config.parakeet.patience,
                                    in: 1...10,
                                    step: 0.1,
                                    onCommit: { v in
                                        appState.config.parakeet.patience = v
                                        appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "patience", value: v)
                                    }
                                ) { v in
                                    Text(String(format: "%.1f", v)).monoStat(width: 40)
                                }
                            }

                            SettingRow(
                                title: "Duration reward",
                                subtitle: "Below 0.5 favors token logprobs, above favors duration logprobs. Default 0.67."
                            ) {
                                CommitSlider(
                                    value: appState.config.parakeet.durationReward,
                                    in: 0...1,
                                    step: 0.01,
                                    onCommit: { v in
                                        appState.config.parakeet.durationReward = v
                                        appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "duration_reward", value: v)
                                    }
                                ) { v in
                                    Text(String(format: "%.2f", v)).monoStat(width: 40)
                                }
                            }
                        }

                        SettingRow(
                            title: "Timeout",
                            subtitle: "Maximum seconds to wait for transcription. 0 means no limit."
                        ) {
                            StepperRowControl(
                                value: Int(appState.config.parakeet.timeout),
                                range: 0...600,
                                step: 10,
                                display: appState.config.parakeet.timeout == 0 ? "Unlimited" : "\(Int(appState.config.parakeet.timeout))s"
                            ) { v in
                                appState.config.parakeet.timeout = Double(v)
                                appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "timeout", value: Double(v))
                            }
                        }
                    }
                    .padding(.top, Theme.Spacing.xs)
                }
                .font(Theme.Typography.bodyEmphasized)
            }

            WideRow {
                DisclosureGroup("Advanced") {
                    VStack(spacing: 0) {
                        ToggleRow(
                            title: "Local attention",
                            subtitle: "Reduces peak memory for very long unchunked audio. Leave off unless chunk duration is 0.",
                            isOn: appState.config.parakeet.localAttention
                        ) { v in
                            appState.config.parakeet.localAttention = v
                            appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "local_attention", value: v)
                        }

                        if appState.config.parakeet.localAttention {
                            SettingRow(title: "Context size") {
                                StepperRowControl(
                                    value: appState.config.parakeet.localAttentionContextSize,
                                    range: 64...2048,
                                    step: 64,
                                    display: "\(appState.config.parakeet.localAttentionContextSize)",
                                    displayWidth: 56
                                ) { v in
                                    appState.config.parakeet.localAttentionContextSize = v
                                    appState.ipcClient?.sendConfigUpdate(section: "parakeet_v3", key: "local_attention_context_size", value: v)
                                }
                            }
                        }
                    }
                    .padding(.top, Theme.Spacing.xs)
                }
                .font(Theme.Typography.bodyEmphasized)
            }
        }
    }
}

// MARK: - Qwen3-ASR

struct Qwen3Section: View {
    @Environment(AppState.self) private var appState

    private let modelPresets: [(id: String, label: String)] = [
        ("mlx-community/Qwen3-ASR-1.7B-bf16", "1.7B · Higher quality"),
        ("mlx-community/Qwen3-ASR-0.6B-bf16", "0.6B · Lower memory and latency"),
    ]

    var body: some View {
        SettingsCard(
            icon: "sparkle",
            title: "Qwen3-ASR settings",
            description: "Multilingual local transcription through a community-maintained MLX runtime."
        ) {
            SettingRow(
                title: "Variant",
                subtitle: "1.7B is the higher-quality default. 0.6B uses less memory and responds faster."
            ) {
                Picker("Variant", selection: modelPresetBinding) {
                    ForEach(modelPresets, id: \.id) { preset in
                        Text(preset.label).tag(preset.id)
                    }
                    Text("Custom MLX model").tag("custom")
                }
                .pickerStyle(.menu)
                .fixedSize()
            }

            if modelPresetBinding.wrappedValue == "custom" {
                SettingRow(
                    title: "Model ID",
                    subtitle: "Advanced: enter a qwen3-asr-mlx-compatible Hugging Face model ID."
                ) {
                    DeferredTextField(
                        label: "Model ID",
                        initialValue: appState.config.qwen3Asr.model
                    ) { value in
                        appState.config.qwen3Asr.model = value
                        appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "model", value: value)
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 280)
                }
            }

            WideRow {
                InlineNotice(
                    kind: .info,
                    text: "The MLX conversion and runtime are community maintained, not Qwen's official PyTorch stack. The 1.7B model needs more memory and has higher latency than 0.6B."
                )
            }

            ToggleRow(
                title: "Use Vocabulary as context",
                subtitle: "Pass enabled Vocabulary rules to supported Qwen models as local context and hotwords. Up to 4,096 characters per request.",
                isOn: appState.config.qwen3Asr.useVocabulary
            ) { value in
                appState.config.qwen3Asr.useVocabulary = value
                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "use_vocabulary", value: value)
            }

            WideRow {
                RestartNote()
            }

            WideRow {
                DisclosureGroup("Sampling") {
                    VStack(spacing: 0) {
                        SettingRow(
                            title: "Temperature",
                            subtitle: "0.0 is greedy. Higher values increase variation. Default 0.0."
                        ) {
                            CommitSlider(
                                value: appState.config.qwen3Asr.temperature,
                                in: 0...1,
                                step: 0.05,
                                onCommit: { v in
                                    appState.config.qwen3Asr.temperature = v
                                    appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "temperature", value: v)
                                }
                            ) { v in
                                Text(String(format: "%.2f", v)).monoStat(width: 40)
                            }
                        }

                        SettingRow(
                            title: "Top P",
                            subtitle: "Active when temperature is above 0. Default 1.0."
                        ) {
                            CommitSlider(
                                value: appState.config.qwen3Asr.topP,
                                in: 0...1,
                                step: 0.05,
                                onCommit: { v in
                                    appState.config.qwen3Asr.topP = v
                                    appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "top_p", value: v)
                                }
                            ) { v in
                                Text(String(format: "%.2f", v)).monoStat(width: 40)
                            }
                        }

                        SettingRow(
                            title: "Top K",
                            subtitle: "Top-K sampling when temperature is above 0. 0 disables. Default 0."
                        ) {
                            StepperRowControl(
                                value: appState.config.qwen3Asr.topK,
                                range: 0...200,
                                step: 1,
                                display: appState.config.qwen3Asr.topK == 0 ? "Off" : "\(appState.config.qwen3Asr.topK)",
                                displayWidth: 40
                            ) { v in
                                appState.config.qwen3Asr.topK = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "top_k", value: v)
                            }
                        }
                    }
                    .padding(.top, Theme.Spacing.xs)
                }
                .font(Theme.Typography.bodyEmphasized)
            }

            WideRow {
                DisclosureGroup("Decoding") {
                    VStack(spacing: 0) {
                        SettingRow(
                            title: "Repetition penalty",
                            subtitle: "Penalty for repeated tokens. 1.0 disables. Default 1.2."
                        ) {
                            CommitSlider(
                                value: appState.config.qwen3Asr.repetitionPenalty,
                                in: 1.0...2.0,
                                step: 0.05,
                                onCommit: { v in
                                    appState.config.qwen3Asr.repetitionPenalty = v
                                    appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "repetition_penalty", value: v)
                                }
                            ) { v in
                                Text(String(format: "%.2f", v)).monoStat(width: 40)
                            }
                        }

                        SettingRow(
                            title: "Repetition context",
                            subtitle: "Tokens of context for the repetition penalty. Default 100."
                        ) {
                            StepperRowControl(
                                value: appState.config.qwen3Asr.repetitionContextSize,
                                range: 1...500,
                                step: 10,
                                display: "\(appState.config.qwen3Asr.repetitionContextSize)",
                                displayWidth: 40
                            ) { v in
                                appState.config.qwen3Asr.repetitionContextSize = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "repetition_context_size", value: v)
                            }
                        }

                        SettingRow(
                            title: "Chunk duration",
                            subtitle: "Maximum chunk size for very long audio. Default 1200s."
                        ) {
                            StepperRowControl(
                                value: Int(appState.config.qwen3Asr.chunkDuration),
                                range: 60...3600,
                                step: 60,
                                display: "\(Int(appState.config.qwen3Asr.chunkDuration))s",
                                displayWidth: 56
                            ) { v in
                                appState.config.qwen3Asr.chunkDuration = Double(v)
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "chunk_duration", value: Double(v))
                            }
                        }

                        SettingRow(
                            title: "Max tokens",
                            subtitle: "Maximum decoded tokens per request. 0 uses the engine default."
                        ) {
                            StepperRowControl(
                                value: appState.config.qwen3Asr.maxTokens,
                                range: 0...4096,
                                step: 64,
                                display: appState.config.qwen3Asr.maxTokens == 0 ? "Default" : "\(appState.config.qwen3Asr.maxTokens)"
                            ) { v in
                                appState.config.qwen3Asr.maxTokens = v
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "max_tokens", value: v)
                            }
                        }

                        SettingRow(
                            title: "Timeout",
                            subtitle: "Maximum seconds to wait for transcription. 0 means no limit."
                        ) {
                            StepperRowControl(
                                value: Int(appState.config.qwen3Asr.timeout),
                                range: 0...600,
                                step: 10,
                                display: appState.config.qwen3Asr.timeout == 0 ? "Unlimited" : "\(Int(appState.config.qwen3Asr.timeout))s"
                            ) { v in
                                appState.config.qwen3Asr.timeout = Double(v)
                                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "timeout", value: Double(v))
                            }
                        }
                    }
                    .padding(.top, Theme.Spacing.xs)
                }
                .font(Theme.Typography.bodyEmphasized)
            }
        }
    }

    private var modelPresetBinding: Binding<String> {
        Binding(
            get: {
                modelPresets.contains(where: { $0.id == appState.config.qwen3Asr.model })
                    ? appState.config.qwen3Asr.model
                    : "custom"
            },
            set: { value in
                guard value != "custom" else { return }
                appState.config.qwen3Asr.model = value
                appState.ipcClient?.sendConfigUpdate(section: "qwen3_asr", key: "model", value: value)
            }
        )
    }
}

// MARK: - Apple SpeechTranscriber

struct AppleSpeechSection: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        SettingsCard(
            icon: "apple.logo",
            title: "Apple SpeechTranscriber settings",
            description: "On-device transcription through SpeechAnalyzer on macOS 26 or later."
        ) {
            SettingRow(
                title: "Language",
                subtitle: "BCP 47 locale such as en-US, de-DE, or fa-IR. SpeechTranscriber requires an explicit supported locale."
            ) {
                DeferredTextField(
                    label: "Locale",
                    initialValue: appState.config.appleSpeech.locale
                ) { value in
                    let locale = value.trimmingCharacters(in: .whitespacesAndNewlines)
                    appState.config.appleSpeech.locale = locale
                    appState.ipcClient?.sendConfigUpdate(section: "apple_speech", key: "locale", value: locale)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 140)
            }

            SettingRow(
                title: "Timeout",
                subtitle: "Maximum time to wait for a completed transcription. 0 means no limit."
            ) {
                StepperRowControl(
                    value: Int(appState.config.appleSpeech.timeout),
                    range: 0...3600,
                    step: 30,
                    display: appState.config.appleSpeech.timeout == 0 ? "Unlimited" : "\(Int(appState.config.appleSpeech.timeout))s"
                ) { value in
                    appState.config.appleSpeech.timeout = Double(value)
                    appState.ipcClient?.sendConfigUpdate(section: "apple_speech", key: "timeout", value: Double(value))
                }
            }

            WideRow {
                InlineNotice(
                    kind: .info,
                    text: "Audio stays on-device. Apple downloads, updates, and shares the language asset through macOS; Local Whisper does not manage the model files directly."
                )
            }
        }
    }
}

// MARK: - WhisperKit

struct WhisperKitSection: View {
    @Environment(AppState.self) private var appState

    private let modelPresets: [(id: String, label: String)] = [
        ("large-v3-v20240930_626MB", "Best accuracy"),
        ("large-v3-v20240930_turbo_632MB", "Fast accuracy"),
        ("large-v3-v20240930_turbo", "Fast"),
        ("large-v3-v20240930", "Large v3"),
        ("small", "Small"),
        ("base", "Base"),
    ]

    var body: some View {
        SettingsCard(
            icon: "server.rack",
            title: "WhisperKit settings",
            description: "Posts 30-second clips to a local server. Supports many languages."
        ) {
            SettingRow(title: "Server URL") {
                DeferredTextField(label: "URL", initialValue: appState.config.whisper.url) { value in
                    appState.config.whisper.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 280)
            }

            SettingRow(title: "Check URL") {
                DeferredTextField(label: "http://localhost:50060/", initialValue: appState.config.whisper.checkUrl) { value in
                    appState.config.whisper.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "check_url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 280)
            }

            WideRow {
                RestartNote()
            }

            SettingRow(
                title: "Preset",
                subtitle: "Argmax recommends Large v3 626 MB for maximum multilingual accuracy."
            ) {
                Picker("Preset", selection: modelPresetBinding) {
                    ForEach(modelPresets, id: \.id) { preset in
                        Text(preset.label).tag(preset.id)
                    }
                    Text("Custom").tag("custom")
                }
                .pickerStyle(.menu)
                .fixedSize()
            }

            SettingRow(title: "Model") {
                DeferredTextField(label: "Model", initialValue: appState.config.whisper.model) { value in
                    appState.config.whisper.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 280)
            }

            SettingRow(title: "Language") {
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
                .pickerStyle(.menu)
                .fixedSize()
            }

            WideRow {
                DisclosureGroup("Decoding") {
                    VStack(spacing: 0) {
                        SettingRow(title: "Temperature") {
                            CommitSlider(
                                value: appState.config.whisper.temperature,
                                in: 0...1,
                                step: 0.05,
                                onCommit: { v in
                                    appState.config.whisper.temperature = v
                                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "temperature", value: v)
                                }
                            ) { v in
                                Text(String(format: "%.2f", v)).monoStat(width: 40)
                            }
                        }

                        SettingRow(
                            title: "Compression-ratio threshold",
                            subtitle: "Filters segments above this ratio as likely repetitive or hallucinated. Default 2.4."
                        ) {
                            CommitSlider(
                                value: appState.config.whisper.compressionRatioThreshold,
                                in: 1...5,
                                step: 0.1,
                                onCommit: { v in
                                    appState.config.whisper.compressionRatioThreshold = v
                                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "compression_ratio_threshold", value: v)
                                }
                            ) { v in
                                Text(String(format: "%.1f", v)).monoStat(width: 40)
                            }
                        }

                        SettingRow(
                            title: "No-speech threshold",
                            subtitle: "Filters segments above this no-speech probability. Default 0.6."
                        ) {
                            CommitSlider(
                                value: appState.config.whisper.noSpeechThreshold,
                                in: 0...1,
                                step: 0.05,
                                onCommit: { v in
                                    appState.config.whisper.noSpeechThreshold = v
                                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "no_speech_threshold", value: v)
                                }
                            ) { v in
                                Text(String(format: "%.2f", v)).monoStat(width: 40)
                            }
                        }

                        SettingRow(
                            title: "Log-probability threshold",
                            subtitle: "Filters segments below this log-probability. Default -1.0."
                        ) {
                            CommitSlider(
                                value: appState.config.whisper.logprobThreshold,
                                in: -2...0,
                                step: 0.05,
                                onCommit: { v in
                                    appState.config.whisper.logprobThreshold = v
                                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "logprob_threshold", value: v)
                                }
                            ) { v in
                                Text(String(format: "%.2f", v)).monoStat(width: 40)
                            }
                        }

                        SettingRow(title: "Temperature fallback count") {
                            StepperRowControl(
                                value: appState.config.whisper.temperatureFallbackCount,
                                range: 1...10,
                                step: 1,
                                display: "\(appState.config.whisper.temperatureFallbackCount)",
                                displayWidth: 40
                            ) { v in
                                appState.config.whisper.temperatureFallbackCount = v
                                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "temperature_fallback_count", value: v)
                            }
                        }
                    }
                    .padding(.top, Theme.Spacing.xs)
                }
                .font(Theme.Typography.bodyEmphasized)
            }

            WideRow {
                DisclosureGroup("Vocabulary hints") {
                    VStack(spacing: 0) {
                        SettingRow(title: "Preset") {
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
                            .pickerStyle(.menu)
                            .fixedSize()
                        }

                        if appState.config.whisper.promptPreset == "custom" {
                            WideRow {
                                Text("Custom prompt")
                                    .font(Theme.Typography.bodyEmphasized)
                                DeferredTextEditor(initialValue: appState.config.whisper.prompt) { value in
                                    appState.config.whisper.prompt = value
                                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "prompt", value: value)
                                }
                                .font(.system(size: 12))
                                .frame(height: 60)
                                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Theme.Surface.stroke))
                            }
                        }
                    }
                    .padding(.top, Theme.Spacing.xs)
                }
                .font(Theme.Typography.bodyEmphasized)
            }

            SettingRow(title: "Timeout", subtitle: "Maximum wait per request. 0 means no limit.") {
                StepperRowControl(
                    value: Int(appState.config.whisper.timeout),
                    range: 0...300,
                    step: 5,
                    display: appState.config.whisper.timeout == 0 ? "Unlimited" : "\(Int(appState.config.whisper.timeout))s"
                ) { v in
                    appState.config.whisper.timeout = Double(v)
                    appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "timeout", value: Double(v))
                }
            }
        }
    }

    private var modelPresetBinding: Binding<String> {
        Binding(
            get: {
                modelPresets.contains { $0.id == appState.config.whisper.model }
                    ? appState.config.whisper.model
                    : "custom"
            },
            set: { value in
                guard value != "custom" else { return }
                appState.config.whisper.model = value
                appState.ipcClient?.sendConfigUpdate(section: "whisper", key: "model", value: value)
            }
        )
    }
}
