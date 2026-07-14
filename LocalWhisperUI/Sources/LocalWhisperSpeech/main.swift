import AppleSpeechCore
import Darwin
import Foundation

private struct HelperResponse: Encodable {
    let ok: Bool
    let availability: AppleSpeechAvailability?
    let installed: Bool?
    let locale: String?
    let message: String
    let transcript: String?
    let code: String?

    static func status(_ status: AppleSpeechStatus) -> HelperResponse {
        HelperResponse(
            ok: status.availability != .unavailable,
            availability: status.availability,
            installed: status.installed,
            locale: status.localeIdentifier,
            message: status.message,
            transcript: nil,
            code: status.availability == .unavailable ? "unavailable" : nil
        )
    }

    static func transcript(_ text: String, locale: String) -> HelperResponse {
        HelperResponse(
            ok: true,
            availability: .installed,
            installed: true,
            locale: locale,
            message: "Transcription complete.",
            transcript: text,
            code: nil
        )
    }

    static func failure(_ error: Error) -> HelperResponse {
        if let error = error as? AppleSpeechError {
            return HelperResponse(
                ok: false,
                availability: .unavailable,
                installed: nil,
                locale: nil,
                message: error.message,
                transcript: nil,
                code: error.code
            )
        }
        return HelperResponse(
            ok: false,
            availability: .unavailable,
            installed: nil,
            locale: nil,
            message: error.localizedDescription,
            transcript: nil,
            code: "unexpected_error"
        )
    }
}

private func argumentValue(_ name: String, in arguments: [String]) throws -> String {
    guard let index = arguments.firstIndex(of: name), arguments.indices.contains(index + 1) else {
        throw AppleSpeechError(
            code: "invalid_arguments",
            message: "Missing required argument \(name)."
        )
    }
    return arguments[index + 1]
}

@available(macOS 26.0, *)
private func run(arguments: [String]) async throws -> HelperResponse {
    guard let command = arguments.first else {
        throw AppleSpeechError(
            code: "invalid_arguments",
            message: "Use status, install, release, or transcribe."
        )
    }
    let locale = try argumentValue("--locale", in: arguments)
    switch command {
    case "status":
        return .status(await AppleSpeechService.status(localeIdentifier: locale))
    case "install":
        return .status(try await AppleSpeechService.install(localeIdentifier: locale))
    case "release":
        return .status(try await AppleSpeechService.release(localeIdentifier: locale))
    case "transcribe":
        guard let audioPath = arguments.last, audioPath != locale, audioPath != "--locale" else {
            throw AppleSpeechError(
                code: "invalid_arguments",
                message: "Provide an audio file path for transcription."
            )
        }
        let canonical = try AppleSpeechService.canonicalLocaleIdentifier(locale)
        let transcript = try await AppleSpeechService.transcribe(
            audioURL: URL(fileURLWithPath: audioPath),
            localeIdentifier: canonical
        )
        return .transcript(transcript, locale: canonical)
    default:
        throw AppleSpeechError(
            code: "invalid_arguments",
            message: "Unknown command \(command). Use status, install, release, or transcribe."
        )
    }
}

private func emit(_ response: HelperResponse) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard let data = try? encoder.encode(response), let json = String(data: data, encoding: .utf8) else {
        print("{\"code\":\"encoding_failed\",\"message\":\"Could not encode helper response.\",\"ok\":false}")
        return
    }
    print(json)
}

let arguments = Array(CommandLine.arguments.dropFirst())
do {
    guard #available(macOS 26.0, *) else {
        throw AppleSpeechError(
            code: "os_unsupported",
            message: "Apple SpeechTranscriber requires macOS 26 or later."
        )
    }
    emit(try await run(arguments: arguments))
    exit(EXIT_SUCCESS)
} catch {
    emit(.failure(error))
    exit(EXIT_FAILURE)
}
