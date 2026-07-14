import AVFoundation
import Foundation
import Speech

public enum AppleSpeechAvailability: String, Codable, Sendable {
    case unavailable
    case supported
    case downloading
    case installed
}

public struct AppleSpeechStatus: Codable, Sendable, Equatable {
    public let availability: AppleSpeechAvailability
    public let installed: Bool
    public let localeIdentifier: String
    public let message: String

    public init(
        availability: AppleSpeechAvailability,
        localeIdentifier: String,
        message: String
    ) {
        self.availability = availability
        self.installed = availability == .installed
        self.localeIdentifier = localeIdentifier
        self.message = message
    }

    enum CodingKeys: String, CodingKey {
        case availability
        case installed
        case localeIdentifier = "locale"
        case message
    }
}

public struct AppleSpeechError: LocalizedError, Codable, Sendable, Equatable {
    public let code: String
    public let message: String

    public init(code: String, message: String) {
        self.code = code
        self.message = message
    }

    public var errorDescription: String? { message }
}

public enum AppleSpeechService {
    public static func canonicalLocaleIdentifier(_ identifier: String) throws -> String {
        let trimmed = identifier.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw AppleSpeechError(
                code: "invalid_locale",
                message: "Choose a transcription language before using Apple SpeechTranscriber."
            )
        }
        return Locale(identifier: trimmed.replacingOccurrences(of: "_", with: "-"))
            .identifier
            .replacingOccurrences(of: "_", with: "-")
    }

    @available(macOS 26.0, iOS 26.0, *)
    public static func status(localeIdentifier: String) async -> AppleSpeechStatus {
        do {
            let (canonical, _, transcriber) = try await configuredTranscriber(
                localeIdentifier: localeIdentifier
            )
            let nativeStatus = await AssetInventory.status(forModules: [transcriber])
            switch nativeStatus {
            case .installed:
                return AppleSpeechStatus(
                    availability: .installed,
                    localeIdentifier: canonical,
                    message: "Apple SpeechTranscriber is ready."
                )
            case .downloading:
                return AppleSpeechStatus(
                    availability: .downloading,
                    localeIdentifier: canonical,
                    message: "Apple is downloading the \(canonical) speech model."
                )
            case .supported:
                return AppleSpeechStatus(
                    availability: .supported,
                    localeIdentifier: canonical,
                    message: "Download the Apple-managed \(canonical) speech model before transcription."
                )
            case .unsupported:
                return AppleSpeechStatus(
                    availability: .unavailable,
                    localeIdentifier: canonical,
                    message: "Apple SpeechTranscriber is unavailable for \(canonical) on this device."
                )
            @unknown default:
                return AppleSpeechStatus(
                    availability: .unavailable,
                    localeIdentifier: canonical,
                    message: "Apple SpeechTranscriber returned an unknown model state."
                )
            }
        } catch let error as AppleSpeechError {
            let canonical = (try? canonicalLocaleIdentifier(localeIdentifier)) ?? localeIdentifier
            return AppleSpeechStatus(
                availability: .unavailable,
                localeIdentifier: canonical,
                message: error.message
            )
        } catch {
            return AppleSpeechStatus(
                availability: .unavailable,
                localeIdentifier: localeIdentifier,
                message: error.localizedDescription
            )
        }
    }

    @available(macOS 26.0, iOS 26.0, *)
    @discardableResult
    public static func install(localeIdentifier: String) async throws -> AppleSpeechStatus {
        let (canonical, _, transcriber) = try await configuredTranscriber(
            localeIdentifier: localeIdentifier
        )
        let initialStatus = await AssetInventory.status(forModules: [transcriber])
        if initialStatus == .installed {
            return AppleSpeechStatus(
                availability: .installed,
                localeIdentifier: canonical,
                message: "Apple SpeechTranscriber is ready."
            )
        }
        guard initialStatus != .unsupported else {
            throw AppleSpeechError(
                code: "asset_unsupported",
                message: "Apple does not provide a SpeechTranscriber model for \(canonical) on this device."
            )
        }

        if let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
            try await request.downloadAndInstall()
        }

        guard await AssetInventory.status(forModules: [transcriber]) == .installed else {
            throw AppleSpeechError(
                code: "asset_install_failed",
                message: "Apple did not finish installing the \(canonical) speech model."
            )
        }
        return AppleSpeechStatus(
            availability: .installed,
            localeIdentifier: canonical,
            message: "Apple SpeechTranscriber is ready."
        )
    }

    @available(macOS 26.0, iOS 26.0, *)
    @discardableResult
    public static func release(localeIdentifier: String) async throws -> AppleSpeechStatus {
        let (canonical, supportedLocale, _) = try await configuredTranscriber(
            localeIdentifier: localeIdentifier
        )
        let reservedLocales = await AssetInventory.reservedLocales
        if let reserved = reservedLocales.first(where: {
            $0.language.isEquivalent(to: supportedLocale.language)
                && ($0.region == supportedLocale.region || $0.region == nil || supportedLocale.region == nil)
        }) {
            _ = await AssetInventory.release(reservedLocale: reserved)
        }
        return await status(localeIdentifier: canonical)
    }

    @available(macOS 26.0, iOS 26.0, *)
    public static func transcribe(
        audioURL: URL,
        localeIdentifier: String
    ) async throws -> String {
        guard FileManager.default.fileExists(atPath: audioURL.path) else {
            throw AppleSpeechError(
                code: "audio_missing",
                message: "The recording file is missing: \(audioURL.path)"
            )
        }

        _ = try await install(localeIdentifier: localeIdentifier)
        let (_, _, transcriber) = try await configuredTranscriber(localeIdentifier: localeIdentifier)
        let file: AVAudioFile
        do {
            file = try AVAudioFile(forReading: audioURL)
        } catch {
            throw AppleSpeechError(
                code: "audio_unreadable",
                message: "Apple SpeechTranscriber could not read the recording: \(error.localizedDescription)"
            )
        }

        let analyzer = SpeechAnalyzer(modules: [transcriber])
        async let transcriptResult: String = collectResults(from: transcriber)

        do {
            if let lastSample = try await analyzer.analyzeSequence(from: file) {
                try await analyzer.finalizeAndFinish(through: lastSample)
            } else {
                await analyzer.cancelAndFinishNow()
            }
            let transcript = try await transcriptResult
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !transcript.isEmpty else {
                throw AppleSpeechError(
                    code: "empty_transcript",
                    message: "Apple SpeechTranscriber did not detect speech in the recording."
                )
            }
            return transcript
        } catch let error as AppleSpeechError {
            throw error
        } catch {
            await analyzer.cancelAndFinishNow()
            throw AppleSpeechError(
                code: "analysis_failed",
                message: "Apple SpeechTranscriber failed: \(error.localizedDescription)"
            )
        }
    }

    @available(macOS 26.0, iOS 26.0, *)
    private static func configuredTranscriber(
        localeIdentifier: String
    ) async throws -> (String, Locale, SpeechTranscriber) {
        guard SpeechTranscriber.isAvailable else {
            throw AppleSpeechError(
                code: "device_unsupported",
                message: "Apple SpeechTranscriber is unavailable on this device. Use macOS or iOS 26 on supported Apple hardware."
            )
        }
        let canonical = try canonicalLocaleIdentifier(localeIdentifier)
        let requestedLocale = Locale(identifier: canonical)
        guard let supportedLocale = await SpeechTranscriber.supportedLocale(
            equivalentTo: requestedLocale
        ) else {
            throw AppleSpeechError(
                code: "locale_unsupported",
                message: "Apple SpeechTranscriber does not support \(canonical) on this device."
            )
        }
        return (
            try canonicalLocaleIdentifier(supportedLocale.identifier),
            supportedLocale,
            SpeechTranscriber(locale: supportedLocale, preset: .transcription)
        )
    }

    @available(macOS 26.0, iOS 26.0, *)
    private static func collectResults(from transcriber: SpeechTranscriber) async throws -> String {
        var transcript = ""
        for try await result in transcriber.results {
            transcript += String(result.text.characters)
        }
        return transcript
    }
}
