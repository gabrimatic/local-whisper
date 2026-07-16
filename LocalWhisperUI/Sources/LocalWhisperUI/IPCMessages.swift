import Foundation

// MARK: - App Phase

enum AppPhase: String, Codable, Sendable {
    case idle
    case recording
    case processing
    case done
    case error
    case speaking
}

// MARK: - Tolerant decoding
//
// Every config struct decodes field-by-field with a default fallback. A
// missing or mistyped key must never drop the entire config_snapshot: that
// failure mode silently left the UI editing phantom defaults while looking
// "Connected", and made every Python schema addition a lockstep hazard.

extension KeyedDecodingContainer {
    func decodeOr<T: Decodable>(_ type: T.Type, _ key: Key, _ fallback: T) -> T {
        // `try?` flattens the `T??` from decodeIfPresent to `T?` (SE-0230).
        if let value = try? decodeIfPresent(T.self, forKey: key) {
            return value
        }
        return fallback
    }
}

// MARK: - Config structs

struct HotkeyConfig: Codable, Sendable {
    var key: String = "alt_r"
    var doubleTapThreshold: Double = 0.4
    var holdThreshold: Double = 0.0

    enum CodingKeys: String, CodingKey {
        case key
        case doubleTapThreshold = "double_tap_threshold"
        case holdThreshold = "hold_threshold"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        key = c.decodeOr(String.self, .key, d.key)
        doubleTapThreshold = c.decodeOr(Double.self, .doubleTapThreshold, d.doubleTapThreshold)
        holdThreshold = c.decodeOr(Double.self, .holdThreshold, d.holdThreshold)
    }
}

struct TranscriptionConfig: Codable, Sendable {
    var engine: String = "parakeet_v3"

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        engine = c.decodeOr(String.self, .engine, d.engine)
    }

    enum CodingKeys: String, CodingKey { case engine }
}

struct ParakeetConfig: Codable, Sendable {
    var model: String = "mlx-community/parakeet-tdt-0.6b-v3"
    var timeout: Double = 0
    var chunkDuration: Double = 120.0
    var overlapDuration: Double = 15.0
    var decoding: String = "greedy"
    var beamSize: Int = 5
    var lengthPenalty: Double = 0.013
    var patience: Double = 3.5
    var durationReward: Double = 0.67
    var localAttention: Bool = false
    var localAttentionContextSize: Int = 256

    enum CodingKeys: String, CodingKey {
        case model, timeout, decoding, patience
        case chunkDuration = "chunk_duration"
        case overlapDuration = "overlap_duration"
        case beamSize = "beam_size"
        case lengthPenalty = "length_penalty"
        case durationReward = "duration_reward"
        case localAttention = "local_attention"
        case localAttentionContextSize = "local_attention_context_size"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        model = c.decodeOr(String.self, .model, d.model)
        timeout = c.decodeOr(Double.self, .timeout, d.timeout)
        chunkDuration = c.decodeOr(Double.self, .chunkDuration, d.chunkDuration)
        overlapDuration = c.decodeOr(Double.self, .overlapDuration, d.overlapDuration)
        decoding = c.decodeOr(String.self, .decoding, d.decoding)
        beamSize = c.decodeOr(Int.self, .beamSize, d.beamSize)
        lengthPenalty = c.decodeOr(Double.self, .lengthPenalty, d.lengthPenalty)
        patience = c.decodeOr(Double.self, .patience, d.patience)
        durationReward = c.decodeOr(Double.self, .durationReward, d.durationReward)
        localAttention = c.decodeOr(Bool.self, .localAttention, d.localAttention)
        localAttentionContextSize = c.decodeOr(Int.self, .localAttentionContextSize, d.localAttentionContextSize)
    }
}

struct Qwen3ASRConfig: Codable, Sendable {
    var model: String = "mlx-community/Qwen3-ASR-1.7B-bf16"
    var timeout: Double = 0
    var temperature: Double = 0.0
    var topP: Double = 1.0
    var topK: Int = 0
    var repetitionContextSize: Int = 100
    var repetitionPenalty: Double = 1.2
    var chunkDuration: Double = 1200.0
    var maxTokens: Int = 0

    enum CodingKeys: String, CodingKey {
        case model, timeout, temperature
        case topP = "top_p"
        case topK = "top_k"
        case repetitionContextSize = "repetition_context_size"
        case repetitionPenalty = "repetition_penalty"
        case chunkDuration = "chunk_duration"
        case maxTokens = "max_tokens"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        model = c.decodeOr(String.self, .model, d.model)
        timeout = c.decodeOr(Double.self, .timeout, d.timeout)
        temperature = c.decodeOr(Double.self, .temperature, d.temperature)
        topP = c.decodeOr(Double.self, .topP, d.topP)
        topK = c.decodeOr(Int.self, .topK, d.topK)
        repetitionContextSize = c.decodeOr(Int.self, .repetitionContextSize, d.repetitionContextSize)
        repetitionPenalty = c.decodeOr(Double.self, .repetitionPenalty, d.repetitionPenalty)
        chunkDuration = c.decodeOr(Double.self, .chunkDuration, d.chunkDuration)
        maxTokens = c.decodeOr(Int.self, .maxTokens, d.maxTokens)
    }
}

struct AppleSpeechConfig: Codable, Sendable {
    var locale: String = "en-US"
    var timeout: Double = 0

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        locale = c.decodeOr(String.self, .locale, d.locale)
        timeout = c.decodeOr(Double.self, .timeout, d.timeout)
    }

    enum CodingKeys: String, CodingKey { case locale, timeout }
}

struct WhisperConfig: Codable, Sendable {
    var url: String = "http://localhost:50060/v1/audio/transcriptions"
    var checkUrl: String = "http://localhost:50060/"
    var model: String = "large-v3-v20240930_626MB"
    var language: String = "auto"
    var timeout: Double = 0
    var prompt: String = ""
    var temperature: Double = 0.0
    var compressionRatioThreshold: Double = 2.4
    var noSpeechThreshold: Double = 0.6
    var logprobThreshold: Double = -1.0
    var temperatureFallbackCount: Int = 5
    var promptPreset: String = "none"

    enum CodingKeys: String, CodingKey {
        case url, model, language, timeout, prompt, temperature
        case checkUrl = "check_url"
        case compressionRatioThreshold = "compression_ratio_threshold"
        case noSpeechThreshold = "no_speech_threshold"
        case logprobThreshold = "logprob_threshold"
        case temperatureFallbackCount = "temperature_fallback_count"
        case promptPreset = "prompt_preset"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        url = c.decodeOr(String.self, .url, d.url)
        checkUrl = c.decodeOr(String.self, .checkUrl, d.checkUrl)
        model = c.decodeOr(String.self, .model, d.model)
        language = c.decodeOr(String.self, .language, d.language)
        timeout = c.decodeOr(Double.self, .timeout, d.timeout)
        prompt = c.decodeOr(String.self, .prompt, d.prompt)
        temperature = c.decodeOr(Double.self, .temperature, d.temperature)
        compressionRatioThreshold = c.decodeOr(Double.self, .compressionRatioThreshold, d.compressionRatioThreshold)
        noSpeechThreshold = c.decodeOr(Double.self, .noSpeechThreshold, d.noSpeechThreshold)
        logprobThreshold = c.decodeOr(Double.self, .logprobThreshold, d.logprobThreshold)
        temperatureFallbackCount = c.decodeOr(Int.self, .temperatureFallbackCount, d.temperatureFallbackCount)
        promptPreset = c.decodeOr(String.self, .promptPreset, d.promptPreset)
    }
}

struct GrammarConfig: Codable, Sendable {
    var backend: String = "apple_intelligence"
    var enabled: Bool = false

    enum CodingKeys: String, CodingKey { case backend, enabled }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        backend = c.decodeOr(String.self, .backend, d.backend)
        enabled = c.decodeOr(Bool.self, .enabled, d.enabled)
    }
}

struct OllamaConfig: Codable, Sendable {
    var url: String = "http://localhost:11434/api/generate"
    var checkUrl: String = "http://localhost:11434/"
    var model: String = "gemma3:4b-it-qat"
    var maxChars: Int = 0
    var maxPredict: Int = 0
    var numCtx: Int = 0
    var keepAlive: String = "60m"
    var timeout: Double = 0
    var unloadOnExit: Bool = false

    enum CodingKeys: String, CodingKey {
        case url, model, timeout
        case checkUrl = "check_url"
        case maxChars = "max_chars"
        case maxPredict = "max_predict"
        case numCtx = "num_ctx"
        case keepAlive = "keep_alive"
        case unloadOnExit = "unload_on_exit"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        url = c.decodeOr(String.self, .url, d.url)
        checkUrl = c.decodeOr(String.self, .checkUrl, d.checkUrl)
        model = c.decodeOr(String.self, .model, d.model)
        maxChars = c.decodeOr(Int.self, .maxChars, d.maxChars)
        maxPredict = c.decodeOr(Int.self, .maxPredict, d.maxPredict)
        numCtx = c.decodeOr(Int.self, .numCtx, d.numCtx)
        keepAlive = c.decodeOr(String.self, .keepAlive, d.keepAlive)
        timeout = c.decodeOr(Double.self, .timeout, d.timeout)
        unloadOnExit = c.decodeOr(Bool.self, .unloadOnExit, d.unloadOnExit)
    }
}

struct AppleIntelligenceConfig: Codable, Sendable {
    var maxChars: Int = 0
    var timeout: Double = 0

    enum CodingKeys: String, CodingKey {
        case maxChars = "max_chars"
        case timeout
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        maxChars = c.decodeOr(Int.self, .maxChars, d.maxChars)
        timeout = c.decodeOr(Double.self, .timeout, d.timeout)
    }
}

struct LMStudioConfig: Codable, Sendable {
    var url: String = "http://localhost:1234/v1/chat/completions"
    var checkUrl: String = "http://localhost:1234/"
    var model: String = "google/gemma-3-4b"
    var maxChars: Int = 0
    var maxTokens: Int = 0
    var timeout: Double = 0

    enum CodingKeys: String, CodingKey {
        case url, model, timeout
        case checkUrl = "check_url"
        case maxChars = "max_chars"
        case maxTokens = "max_tokens"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        url = c.decodeOr(String.self, .url, d.url)
        checkUrl = c.decodeOr(String.self, .checkUrl, d.checkUrl)
        model = c.decodeOr(String.self, .model, d.model)
        maxChars = c.decodeOr(Int.self, .maxChars, d.maxChars)
        maxTokens = c.decodeOr(Int.self, .maxTokens, d.maxTokens)
        timeout = c.decodeOr(Double.self, .timeout, d.timeout)
    }
}

struct AudioConfig: Codable, Sendable {
    var sampleRate: Int = 16000
    var minDuration: Double = 0
    var maxDuration: Int = 0
    var minRms: Double = 0.005
    var vadEnabled: Bool = true
    var noiseReduction: Bool = true
    var normalizeAudio: Bool = true
    var preBuffer: Double = 0.0

    enum CodingKeys: String, CodingKey {
        case sampleRate = "sample_rate"
        case minDuration = "min_duration"
        case maxDuration = "max_duration"
        case minRms = "min_rms"
        case vadEnabled = "vad_enabled"
        case noiseReduction = "noise_reduction"
        case normalizeAudio = "normalize_audio"
        case preBuffer = "pre_buffer"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        sampleRate = c.decodeOr(Int.self, .sampleRate, d.sampleRate)
        minDuration = c.decodeOr(Double.self, .minDuration, d.minDuration)
        maxDuration = c.decodeOr(Int.self, .maxDuration, d.maxDuration)
        minRms = c.decodeOr(Double.self, .minRms, d.minRms)
        vadEnabled = c.decodeOr(Bool.self, .vadEnabled, d.vadEnabled)
        noiseReduction = c.decodeOr(Bool.self, .noiseReduction, d.noiseReduction)
        normalizeAudio = c.decodeOr(Bool.self, .normalizeAudio, d.normalizeAudio)
        preBuffer = c.decodeOr(Double.self, .preBuffer, d.preBuffer)
    }
}

struct UIConfig: Codable, Sendable {
    var showOverlay: Bool = true
    var overlayOpacity: Double = 0.92
    var soundsEnabled: Bool = true
    var notificationsEnabled: Bool = false
    var autoPaste: Bool = false

    enum CodingKeys: String, CodingKey {
        case showOverlay = "show_overlay"
        case overlayOpacity = "overlay_opacity"
        case soundsEnabled = "sounds_enabled"
        case notificationsEnabled = "notifications_enabled"
        case autoPaste = "auto_paste"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        showOverlay = c.decodeOr(Bool.self, .showOverlay, d.showOverlay)
        overlayOpacity = c.decodeOr(Double.self, .overlayOpacity, d.overlayOpacity)
        soundsEnabled = c.decodeOr(Bool.self, .soundsEnabled, d.soundsEnabled)
        notificationsEnabled = c.decodeOr(Bool.self, .notificationsEnabled, d.notificationsEnabled)
        autoPaste = c.decodeOr(Bool.self, .autoPaste, d.autoPaste)
    }
}

struct BackupConfig: Codable, Sendable {
    var directory: String = "~/.whisper"
    var historyLimit: Int = 100

    enum CodingKeys: String, CodingKey {
        case directory
        case historyLimit = "history_limit"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        directory = c.decodeOr(String.self, .directory, d.directory)
        historyLimit = c.decodeOr(Int.self, .historyLimit, d.historyLimit)
    }
}

struct ServiceConfig: Codable, Sendable {
    var idleUnloadMinutes: Int = 20

    enum CodingKeys: String, CodingKey {
        case idleUnloadMinutes = "idle_unload_minutes"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        idleUnloadMinutes = c.decodeOr(Int.self, .idleUnloadMinutes, d.idleUnloadMinutes)
    }
}

struct ShortcutsConfig: Codable, Sendable {
    var enabled: Bool = true
    var proofread: String = "ctrl+shift+g"
    var rewrite: String = "ctrl+shift+r"
    var promptEngineer: String = "ctrl+shift+p"
    var pasteResult: Bool = true

    enum CodingKeys: String, CodingKey {
        case enabled, proofread, rewrite
        case promptEngineer = "prompt_engineer"
        case pasteResult = "paste_result"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        enabled = c.decodeOr(Bool.self, .enabled, d.enabled)
        proofread = c.decodeOr(String.self, .proofread, d.proofread)
        rewrite = c.decodeOr(String.self, .rewrite, d.rewrite)
        promptEngineer = c.decodeOr(String.self, .promptEngineer, d.promptEngineer)
        pasteResult = c.decodeOr(Bool.self, .pasteResult, d.pasteResult)
    }
}

struct TTSConfig: Codable, Sendable {
    var enabled: Bool = false
    var provider: String = "kokoro"
    var speakShortcut: String = "alt+t"

    enum CodingKeys: String, CodingKey {
        case enabled, provider
        case speakShortcut = "speak_shortcut"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        enabled = c.decodeOr(Bool.self, .enabled, d.enabled)
        provider = c.decodeOr(String.self, .provider, d.provider)
        speakShortcut = c.decodeOr(String.self, .speakShortcut, d.speakShortcut)
    }
}

struct KokoroTTSConfig: Codable, Sendable {
    var model: String = "mlx-community/Kokoro-82M-bf16"
    var voice: String = "af_sky"

    enum CodingKeys: String, CodingKey { case model, voice }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        model = c.decodeOr(String.self, .model, d.model)
        voice = c.decodeOr(String.self, .voice, d.voice)
    }
}

struct ReplacementsConfig: Codable, Sendable {
    var enabled: Bool = false
    var rules: [String: String] = [:]

    enum CodingKeys: String, CodingKey { case enabled, rules }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        enabled = c.decodeOr(Bool.self, .enabled, d.enabled)
        rules = c.decodeOr([String: String].self, .rules, d.rules)
    }
}

struct DictationConfig: Codable, Sendable {
    var enabled: Bool = true
    var stripFillers: Bool = true
    var commands: [String: String] = [:]
    /// Built-in command set sent by the service so the UI renders the real
    /// effective list instead of a hardcoded, drifting copy.
    var defaults: [String: String] = [:]

    enum CodingKeys: String, CodingKey {
        case enabled, commands, defaults
        case stripFillers = "strip_fillers"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        enabled = c.decodeOr(Bool.self, .enabled, d.enabled)
        stripFillers = c.decodeOr(Bool.self, .stripFillers, d.stripFillers)
        commands = c.decodeOr([String: String].self, .commands, d.commands)
        defaults = c.decodeOr([String: String].self, .defaults, d.defaults)
    }

    /// Defaults merged with user overrides, the way the engine applies them.
    var effectiveCommands: [(phrase: String, replacement: String, isCustom: Bool)] {
        var merged: [String: (String, Bool)] = [:]
        for (k, v) in defaults { merged[k.lowercased()] = (v, false) }
        for (k, v) in commands { merged[k.lowercased()] = (v, true) }
        return merged
            .sorted { $0.key < $1.key }
            .map { (phrase: $0.key, replacement: $0.value.0, isCustom: $0.value.1) }
    }
}

struct AppConfig: Codable, Sendable {
    var hotkey = HotkeyConfig()
    var transcription = TranscriptionConfig()
    var parakeet = ParakeetConfig()
    var qwen3Asr = Qwen3ASRConfig()
    var appleSpeech = AppleSpeechConfig()
    var whisper = WhisperConfig()
    var grammar = GrammarConfig()
    var ollama = OllamaConfig()
    var appleIntelligence = AppleIntelligenceConfig()
    var lmStudio = LMStudioConfig()
    var audio = AudioConfig()
    var ui = UIConfig()
    var backup = BackupConfig()
    var service = ServiceConfig()
    var shortcuts = ShortcutsConfig()
    var tts = TTSConfig()
    var kokoroTts = KokoroTTSConfig()
    var replacements = ReplacementsConfig()
    var dictation = DictationConfig()

    enum CodingKeys: String, CodingKey {
        case hotkey, transcription, whisper, grammar, ollama, audio, ui, backup, service, shortcuts, tts, replacements, dictation
        case parakeet = "parakeet_v3"
        case qwen3Asr = "qwen3_asr"
        case appleSpeech = "apple_speech"
        case appleIntelligence = "apple_intelligence"
        case lmStudio = "lm_studio"
        case kokoroTts = "kokoro_tts"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = Self()
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else { return }
        hotkey = c.decodeOr(HotkeyConfig.self, .hotkey, d.hotkey)
        transcription = c.decodeOr(TranscriptionConfig.self, .transcription, d.transcription)
        parakeet = c.decodeOr(ParakeetConfig.self, .parakeet, d.parakeet)
        qwen3Asr = c.decodeOr(Qwen3ASRConfig.self, .qwen3Asr, d.qwen3Asr)
        appleSpeech = c.decodeOr(AppleSpeechConfig.self, .appleSpeech, d.appleSpeech)
        whisper = c.decodeOr(WhisperConfig.self, .whisper, d.whisper)
        grammar = c.decodeOr(GrammarConfig.self, .grammar, d.grammar)
        ollama = c.decodeOr(OllamaConfig.self, .ollama, d.ollama)
        appleIntelligence = c.decodeOr(AppleIntelligenceConfig.self, .appleIntelligence, d.appleIntelligence)
        lmStudio = c.decodeOr(LMStudioConfig.self, .lmStudio, d.lmStudio)
        audio = c.decodeOr(AudioConfig.self, .audio, d.audio)
        ui = c.decodeOr(UIConfig.self, .ui, d.ui)
        backup = c.decodeOr(BackupConfig.self, .backup, d.backup)
        service = c.decodeOr(ServiceConfig.self, .service, d.service)
        shortcuts = c.decodeOr(ShortcutsConfig.self, .shortcuts, d.shortcuts)
        tts = c.decodeOr(TTSConfig.self, .tts, d.tts)
        kokoroTts = c.decodeOr(KokoroTTSConfig.self, .kokoroTts, d.kokoroTts)
        replacements = c.decodeOr(ReplacementsConfig.self, .replacements, d.replacements)
        dictation = c.decodeOr(DictationConfig.self, .dictation, d.dictation)
    }

    static var defaultConfig: AppConfig { AppConfig() }
}

// MARK: - Engine status

struct EngineStatus: Codable, Sendable, Identifiable {
    var id: String
    var name: String
    var description: String
    var active: Bool
    var downloaded: Bool
    var downloadStatus: String?
    var sizeMb: Int?
    var warmed: Bool
    var cacheDir: String?
    var hfRepo: String?
    var managedBy: String?
    var available: Bool?
    var removable: Bool?
    var locale: String?
    var message: String?

    enum CodingKeys: String, CodingKey {
        case id, name, description, active, downloaded, warmed
        case downloadStatus = "download_status"
        case sizeMb = "size_mb"
        case cacheDir = "cache_dir"
        case hfRepo = "hf_repo"
        case managedBy = "managed_by"
        case available, removable, locale, message
    }
}

// MARK: - History

struct HistoryEntry: Codable, Identifiable, Sendable {
    var id: String
    var text: String
    /// Raw engine transcription when it differs from the final text.
    var raw: String?
    var timestamp: Double
    var audioPath: String?

    enum CodingKeys: String, CodingKey {
        case id, text, raw, timestamp
        case audioPath = "audio_path"
    }

    var date: Date {
        Date(timeIntervalSince1970: timestamp)
    }
}

// MARK: - Download progress

struct DownloadProgress: Codable, Sendable {
    var target: String
    var bytes: Int64
    var total: Int64
    var percent: Double
    var phase: String
    var error: String?
}

// MARK: - Pipeline test results (vocabulary / dictation testers)

struct PipelineTestResult: Sendable {
    var input: String
    var output: String
    var enabled: Bool
}

// MARK: - Incoming messages

enum IncomingMessage: Sendable {
    case configSnapshot(AppConfig)
    case stateUpdate(phase: AppPhase, durationSeconds: Double, rmsLevel: Double, text: String?, statusText: String?)
    case historyUpdate([HistoryEntry])
    case enginesStatus([EngineStatus])
    case downloadProgress(DownloadProgress)
    case notification(title: String, body: String)
    case replacementTestResult(PipelineTestResult)
    case dictationTestResult(PipelineTestResult)
    /// Internal (not from the wire): connection transitions, delivered through
    /// the same ordered stream as wire messages so they can never race them.
    case connectionChanged(ConnectionState)
}

/// Array that skips undecodable elements instead of failing the whole
/// message — one malformed history entry must not drop the entire update
/// during service/app version skew.
struct LossyArray<Element: Decodable>: Decodable {
    var elements: [Element]

    init(from decoder: Decoder) throws {
        var container = try decoder.unkeyedContainer()
        var result: [Element] = []
        while !container.isAtEnd {
            if let element = try? container.decode(Element.self) {
                result.append(element)
            } else {
                // Skip the broken element, keeping position.
                _ = try? container.decode(AnyDecodable.self)
            }
        }
        elements = result
    }

    private struct AnyDecodable: Decodable {}
}

/// Value wrapper that decodes to nil instead of failing — one undecodable
/// engine entry must not drop the whole engines list during version skew.
struct Lossy<T: Decodable>: Decodable {
    let value: T?

    init(from decoder: Decoder) throws {
        value = try? T(from: decoder)
    }
}

private struct RawIncoming: Decodable {
    var type: String
    var config: AppConfig?
    var phase: String?
    var duration_seconds: Double?
    var rms_level: Double?
    var text: String?
    var status_text: String?
    var entries: LossyArray<HistoryEntry>?
    var engines: [String: Lossy<EngineStatus>]?
}

// Separate struct so the `phase` field on download_progress — which uses its
// own vocabulary ("preparing"/"downloading"/"warming"/"ready"/"error") —
// doesn't collide with AppPhase decoding on state_update.
private struct RawDownloadProgress: Decodable {
    var target: String?
    var bytes: Int64?
    var total: Int64?
    var percent: Double?
    var phase: String?
    var error: String?
}

private struct RawTestResult: Decodable {
    var input: String?
    var output: String?
    var enabled: Bool?
}

func decodeIncomingMessage(_ data: Data) throws -> IncomingMessage {
    // Peek at `type` before full decode. download_progress uses its own phase
    // vocabulary that would collide with AppPhase decoding on RawIncoming.
    struct TypePeek: Decodable { var type: String }
    let typeOnly = try JSONDecoder().decode(TypePeek.self, from: data)
    switch typeOnly.type {
    case "download_progress":
        let dp = try JSONDecoder().decode(RawDownloadProgress.self, from: data)
        return .downloadProgress(DownloadProgress(
            target: dp.target ?? "",
            bytes: dp.bytes ?? 0,
            total: dp.total ?? 0,
            percent: dp.percent ?? 0,
            phase: dp.phase ?? "",
            error: dp.error
        ))
    case "replacement_test_result", "dictation_test_result":
        let raw = try JSONDecoder().decode(RawTestResult.self, from: data)
        let result = PipelineTestResult(
            input: raw.input ?? "",
            output: raw.output ?? "",
            enabled: raw.enabled ?? true
        )
        return typeOnly.type == "replacement_test_result"
            ? .replacementTestResult(result)
            : .dictationTestResult(result)
    default:
        break
    }
    let raw = try JSONDecoder().decode(RawIncoming.self, from: data)
    switch raw.type {
    case "config_snapshot":
        guard let config = raw.config else {
            throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "Missing config in config_snapshot"))
        }
        return .configSnapshot(config)
    case "state_update":
        // Unknown phase strings from a newer service map to .idle instead of
        // throwing away the whole update.
        return .stateUpdate(
            phase: raw.phase.flatMap(AppPhase.init(rawValue:)) ?? .idle,
            durationSeconds: raw.duration_seconds ?? 0,
            rmsLevel: raw.rms_level ?? 0,
            text: raw.text,
            statusText: raw.status_text
        )
    case "history_update":
        return .historyUpdate(raw.entries?.elements ?? [])
    case "engines_status":
        return .enginesStatus((raw.engines ?? [:]).values.compactMap(\.value))
    case "notification":
        if let msg = try? JSONDecoder().decode(NotificationMessage.self, from: data) {
            return .notification(title: msg.title, body: msg.body)
        }
        throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "Malformed notification message"))
    default:
        throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "Unknown message type: \(raw.type)"))
    }
}

// MARK: - Notification message (Python → Swift)

struct NotificationMessage: Codable {
    let type: String
    let title: String
    let body: String
}

// MARK: - Outgoing messages

struct ActionMessage: Encodable, Sendable {
    var type = "action"
    var action: String
    var id: String?
}

struct EngineSwitchMessage: Encodable, Sendable {
    var type = "engine_switch"
    var engine: String
}

/// Suspends the service's shortcut interception while a recorder captures a
/// combo, so pressing a currently-bound combo reaches the recorder instead of
/// firing its action.
struct CaptureModeMessage: Encodable, Sendable {
    var type = "capture_mode"
    var active: Bool
}

struct EngineRemoveCacheMessage: Encodable, Sendable {
    var type = "engine_remove_cache"
    var engine: String
}

struct BackendSwitchMessage: Encodable, Sendable {
    var type = "backend_switch"
    var backend: String
}

struct ReplacementAddMessage: Encodable, Sendable {
    var type = "replacement_add"
    var spoken: String
    var replacement: String
}

struct ReplacementRemoveMessage: Encodable, Sendable {
    var type = "replacement_remove"
    var spoken: String
}

struct ReplacementImportMessage: Encodable, Sendable {
    var type = "replacement_import"
    var rules: [String: String]
}

struct ReplacementTestMessage: Encodable, Sendable {
    var type = "replacement_test"
    var text: String
}

struct DictationCommandAddMessage: Encodable, Sendable {
    var type = "dictation_command_add"
    var spoken: String
    var replacement: String
}

struct DictationCommandRemoveMessage: Encodable, Sendable {
    var type = "dictation_command_remove"
    var spoken: String
}

struct DictationTestMessage: Encodable, Sendable {
    var type = "dictation_test"
    var text: String
}

struct ConfigUpdateMessage: Encodable, Sendable {
    var type = "config_update"
    var section: String
    var key: String
    var value: AnyEncodable
}

struct AnyEncodable: Encodable, @unchecked Sendable {
    private let _encode: (Encoder) throws -> Void

    init<T: Encodable>(_ value: T) {
        self._encode = value.encode
    }

    func encode(to encoder: Encoder) throws {
        try _encode(encoder)
    }
}
