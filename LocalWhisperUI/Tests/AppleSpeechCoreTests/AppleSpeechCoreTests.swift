import Foundation
import Testing
@testable import AppleSpeechCore

@Test func canonicalLocaleUsesBCP47Hyphens() throws {
    #expect(try AppleSpeechService.canonicalLocaleIdentifier("en_US") == "en-US")
    #expect(try AppleSpeechService.canonicalLocaleIdentifier("de-DE") == "de-DE")
}

@Test func emptyLocaleHasStableErrorCode() {
    #expect(throws: AppleSpeechError.self) {
        try AppleSpeechService.canonicalLocaleIdentifier("  ")
    }

    do {
        _ = try AppleSpeechService.canonicalLocaleIdentifier("")
        Issue.record("Expected an empty-locale error")
    } catch let error as AppleSpeechError {
        #expect(error.code == "invalid_locale")
        #expect(error.errorDescription == "Choose a transcription language before using Apple SpeechTranscriber.")
    } catch {
        Issue.record("Unexpected error type: \(error)")
    }
}

@Test func statusJSONUsesStablePublicKeys() throws {
    let status = AppleSpeechStatus(
        availability: .installed,
        localeIdentifier: "en-US",
        message: "Apple SpeechTranscriber is ready."
    )
    let data = try JSONEncoder().encode(status)
    let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])

    #expect(object["availability"] as? String == "installed")
    #expect(object["installed"] as? Bool == true)
    #expect(object["locale"] as? String == "en-US")
    #expect(object["message"] as? String == "Apple SpeechTranscriber is ready.")
}
