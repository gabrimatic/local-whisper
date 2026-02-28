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

// MARK: - Config structs

struct HotkeyConfig: Codable, Sendable {
    var key: String
    var doubleTapThreshold: Double

    enum CodingKeys: String, CodingKey {
        case key
        case doubleTapThreshold = "double_tap_threshold"
    }
}

struct TranscriptionConfig: Codable, Sendable {
    var engine: String
}

struct Qwen3ASRConfig: Codable, Sendable {
    var model: String
    var language: String
    var timeout: Double
    var prefillStepSize: Int
    var temperature: Double
    var topP: Double
    var topK: Int
    var repetitionContextSize: Int
    var repetitionPenalty: Double
    var chunkDuration: Double

    enum CodingKeys: String, CodingKey {
        case model, language, timeout, temperature
        case prefillStepSize = "prefill_step_size"
        case topP = "top_p"
        case topK = "top_k"
        case repetitionContextSize = "repetition_context_size"
        case repetitionPenalty = "repetition_penalty"
        case chunkDuration = "chunk_duration"
    }
}

struct WhisperConfig: Codable, Sendable {
    var url: String
    var checkUrl: String
    var model: String
    var language: String
    var timeout: Double
    var prompt: String
    var temperature: Double
    var compressionRatioThreshold: Double
    var noSpeechThreshold: Double
    var logprobThreshold: Double
    var temperatureFallbackCount: Int
    var promptPreset: String

    enum CodingKeys: String, CodingKey {
        case url, model, language, timeout, prompt, temperature
        case checkUrl = "check_url"
        case compressionRatioThreshold = "compression_ratio_threshold"
        case noSpeechThreshold = "no_speech_threshold"
        case logprobThreshold = "logprob_threshold"
        case temperatureFallbackCount = "temperature_fallback_count"
        case promptPreset = "prompt_preset"
    }
}

struct GrammarConfig: Codable, Sendable {
    var backend: String
    var enabled: Bool
}

struct OllamaConfig: Codable, Sendable {
    var url: String
    var checkUrl: String
    var model: String
    var maxChars: Int
    var maxPredict: Int
    var numCtx: Int
    var keepAlive: String
    var timeout: Double
    var unloadOnExit: Bool

    enum CodingKeys: String, CodingKey {
        case url, model, timeout
        case checkUrl = "check_url"
        case maxChars = "max_chars"
        case maxPredict = "max_predict"
        case numCtx = "num_ctx"
        case keepAlive = "keep_alive"
        case unloadOnExit = "unload_on_exit"
    }
}

struct AppleIntelligenceConfig: Codable, Sendable {
    var maxChars: Int
    var timeout: Double

    enum CodingKeys: String, CodingKey {
        case maxChars = "max_chars"
        case timeout
    }
}

struct LMStudioConfig: Codable, Sendable {
    var url: String
    var checkUrl: String
    var model: String
    var maxChars: Int
    var maxTokens: Int
    var timeout: Double

    enum CodingKeys: String, CodingKey {
        case url, model, timeout
        case checkUrl = "check_url"
        case maxChars = "max_chars"
        case maxTokens = "max_tokens"
    }
}

struct AudioConfig: Codable, Sendable {
    var sampleRate: Int
    var minDuration: Double
    var maxDuration: Int
    var minRms: Double
    var vadEnabled: Bool
    var noiseReduction: Bool
    var normalizeAudio: Bool
    var preBuffer: Double

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
}

struct UIConfig: Codable, Sendable {
    var showOverlay: Bool
    var overlayOpacity: Double
    var soundsEnabled: Bool
    var notificationsEnabled: Bool
    var autoPaste: Bool

    enum CodingKeys: String, CodingKey {
        case showOverlay = "show_overlay"
        case overlayOpacity = "overlay_opacity"
        case soundsEnabled = "sounds_enabled"
        case notificationsEnabled = "notifications_enabled"
        case autoPaste = "auto_paste"
    }
}

struct BackupConfig: Codable, Sendable {
    var directory: String
    var historyLimit: Int

    enum CodingKeys: String, CodingKey {
        case directory
        case historyLimit = "history_limit"
    }
}

struct ShortcutsConfig: Codable, Sendable {
    var enabled: Bool
    var proofread: String
    var rewrite: String
    var promptEngineer: String

    enum CodingKeys: String, CodingKey {
        case enabled, proofread, rewrite
        case promptEngineer = "prompt_engineer"
    }
}

struct TTSConfig: Codable, Sendable {
    var enabled: Bool
    var provider: String
    var speakShortcut: String

    enum CodingKeys: String, CodingKey {
        case enabled, provider
        case speakShortcut = "speak_shortcut"
    }
}

struct KokoroTTSConfig: Codable, Sendable {
    var model: String
    var voice: String
}

struct AppConfig: Codable, Sendable {
    var hotkey: HotkeyConfig
    var transcription: TranscriptionConfig
    var qwen3Asr: Qwen3ASRConfig
    var whisper: WhisperConfig
    var grammar: GrammarConfig
    var ollama: OllamaConfig
    var appleIntelligence: AppleIntelligenceConfig
    var lmStudio: LMStudioConfig
    var audio: AudioConfig
    var ui: UIConfig
    var backup: BackupConfig
    var shortcuts: ShortcutsConfig
    var tts: TTSConfig
    var kokoroTts: KokoroTTSConfig

    enum CodingKeys: String, CodingKey {
        case hotkey, transcription, whisper, grammar, ollama, audio, ui, backup, shortcuts, tts
        case qwen3Asr = "qwen3_asr"
        case appleIntelligence = "apple_intelligence"
        case lmStudio = "lm_studio"
        case kokoroTts = "kokoro_tts"
    }

    static var defaultConfig: AppConfig {
        AppConfig(
            hotkey: HotkeyConfig(key: "alt_r", doubleTapThreshold: 0.4),
            transcription: TranscriptionConfig(engine: "qwen3_asr"),
            qwen3Asr: Qwen3ASRConfig(model: "mlx-community/Qwen3-ASR-1.7B-bf16", language: "auto", timeout: 0, prefillStepSize: 4096, temperature: 0.0, topP: 1.0, topK: 0, repetitionContextSize: 100, repetitionPenalty: 1.2, chunkDuration: 1200.0),
            whisper: WhisperConfig(
                url: "http://localhost:50060/v1/audio/transcriptions",
                checkUrl: "http://localhost:50060/",
                model: "whisper-large-v3-v20240930",
                language: "auto",
                timeout: 0,
                prompt: "",
                temperature: 0.0,
                compressionRatioThreshold: 2.4,
                noSpeechThreshold: 0.6,
                logprobThreshold: -1.0,
                temperatureFallbackCount: 5,
                promptPreset: "none"
            ),
            grammar: GrammarConfig(backend: "apple_intelligence", enabled: false),
            ollama: OllamaConfig(
                url: "http://localhost:11434/api/generate",
                checkUrl: "http://localhost:11434/",
                model: "gemma3:4b-it-qat",
                maxChars: 0,
                maxPredict: 0,
                numCtx: 0,
                keepAlive: "60m",
                timeout: 0,
                unloadOnExit: false
            ),
            appleIntelligence: AppleIntelligenceConfig(maxChars: 0, timeout: 0),
            lmStudio: LMStudioConfig(url: "http://localhost:1234/v1/chat/completions", checkUrl: "http://localhost:1234/", model: "google/gemma-3-4b", maxChars: 0, maxTokens: 0, timeout: 0),
            audio: AudioConfig(
                sampleRate: 16000,
                minDuration: 0,
                maxDuration: 0,
                minRms: 0.005,
                vadEnabled: true,
                noiseReduction: true,
                normalizeAudio: true,
                preBuffer: 0.0
            ),
            ui: UIConfig(showOverlay: true, overlayOpacity: 0.92, soundsEnabled: true, notificationsEnabled: false, autoPaste: false),
            backup: BackupConfig(directory: "~/.whisper", historyLimit: 100),
            shortcuts: ShortcutsConfig(
                enabled: true,
                proofread: "ctrl+shift+g",
                rewrite: "ctrl+shift+r",
                promptEngineer: "ctrl+shift+p"
            ),
            tts: TTSConfig(enabled: true, provider: "kokoro", speakShortcut: "alt+t"),
            kokoroTts: KokoroTTSConfig(model: "mlx-community/Kokoro-82M-bf16", voice: "af_sky")
        )
    }
}

// MARK: - History

struct HistoryEntry: Codable, Identifiable, Sendable {
    var id: String
    var text: String
    var timestamp: Double
    var audioPath: String?

    enum CodingKeys: String, CodingKey {
        case id, text, timestamp
        case audioPath = "audio_path"
    }

    var date: Date {
        Date(timeIntervalSince1970: timestamp)
    }
}

// MARK: - Incoming messages

enum IncomingMessage: Sendable {
    case configSnapshot(AppConfig)
    case stateUpdate(phase: AppPhase, durationSeconds: Double, rmsLevel: Double, text: String?, statusText: String?)
    case historyUpdate([HistoryEntry])
    case notification(title: String, body: String)
}

private struct RawIncoming: Decodable {
    var type: String
    var config: AppConfig?
    var phase: AppPhase?
    var duration_seconds: Double?
    var rms_level: Double?
    var text: String?
    var status_text: String?
    var entries: [HistoryEntry]?
}

func decodeIncomingMessage(_ data: Data) throws -> IncomingMessage {
    let raw = try JSONDecoder().decode(RawIncoming.self, from: data)
    switch raw.type {
    case "config_snapshot":
        guard let config = raw.config else {
            throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "Missing config in config_snapshot"))
        }
        return .configSnapshot(config)
    case "state_update":
        return .stateUpdate(
            phase: raw.phase ?? .idle,
            durationSeconds: raw.duration_seconds ?? 0,
            rmsLevel: raw.rms_level ?? 0,
            text: raw.text,
            statusText: raw.status_text
        )
    case "history_update":
        return .historyUpdate(raw.entries ?? [])
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

struct BackendSwitchMessage: Encodable, Sendable {
    var type = "backend_switch"
    var backend: String
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
