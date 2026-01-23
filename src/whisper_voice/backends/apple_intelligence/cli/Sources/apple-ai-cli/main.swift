import Foundation
import FoundationModels

/// Apple Intelligence CLI for grammar correction
/// Usage:
///   apple-ai-cli check   - Check if Apple Intelligence is available
///   apple-ai-cli serve   - Start long-lived server mode for grammar correction
///
/// Server mode protocol (JSONL over stdin/stdout):
///   Request:  {"system": "...", "user_prompt": "...", "text": "..."}
///   Response: {"success": true, "result": "..."} or {"success": false, "error": "..."}
///
/// Exit codes:
///   0 - Success
///   1 - Apple Intelligence unavailable
///   2 - Invalid arguments

// MARK: - Grammar Fixer

/// Grammar fixer using Apple Intelligence with session-level instructions
final class GrammarFixer {
    private let session: LanguageModelSession

    init(instructions: String) {
        session = LanguageModelSession {
            instructions
        }
    }

    /// Prewarm the session to load resources and cache instructions
    func prewarm() {
        session.prewarm()
    }

    func fix(prompt: String) async throws -> String {
        guard !session.isResponding else {
            throw GrammarError.sessionBusy
        }
        let response = try await session.respond(to: prompt)
        return response.content
    }
}

enum GrammarError: Error, LocalizedError {
    case sessionBusy

    var errorDescription: String? {
        switch self {
        case .sessionBusy:
            return "Session is busy processing another request"
        }
    }
}

// MARK: - JSON Protocol Types

struct FixRequest: Codable {
    let system: String
    let userPrompt: String
    let text: String

    enum CodingKeys: String, CodingKey {
        case system
        case userPrompt = "user_prompt"
        case text
    }

    /// Build the full prompt by substituting {text} placeholder
    var fullPrompt: String {
        userPrompt.replacingOccurrences(of: "{text}", with: text)
    }
}

struct FixResponse: Codable {
    let success: Bool
    let result: String?
    let error: String?

    static func ok(_ result: String) -> FixResponse {
        FixResponse(success: true, result: result, error: nil)
    }

    static func fail(_ error: String) -> FixResponse {
        FixResponse(success: false, result: nil, error: error)
    }
}

// MARK: - CLI Entry Point

@main
struct AppleAICLI {
    static func main() async {
        let args = CommandLine.arguments

        guard args.count >= 2 else {
            printUsage()
            exit(2)
        }

        switch args[1] {
        case "check":
            await checkAvailability()
        case "serve":
            await startServer()
        default:
            printUsage()
            exit(2)
        }
    }

    // MARK: - Commands

    /// Check if Apple Intelligence is available
    static func checkAvailability() async {
        let model = SystemLanguageModel.default

        guard model.isAvailable else {
            let reason: String
            switch model.availability {
            case .unavailable(let r):
                switch r {
                case .appleIntelligenceNotEnabled:
                    reason = "apple_intelligence_not_enabled"
                case .deviceNotEligible:
                    reason = "device_not_eligible"
                case .modelNotReady:
                    reason = "model_not_ready"
                @unknown default:
                    reason = "unknown_reason"
                }
            default:
                reason = "unknown_state"
            }
            fputs("unavailable:\(reason)\n", stderr)
            exit(1)
        }

        print("available")
        exit(0)
    }

    /// Start long-lived server mode for efficient repeated calls
    static func startServer() async {
        guard SystemLanguageModel.default.isAvailable else {
            printJSON(FixResponse.fail("Apple Intelligence not available"))
            exit(1)
        }

        // Signal ready to parent process
        fputs("READY\n", stderr)
        fflush(stderr)

        var currentFixer: GrammarFixer?
        var currentSystemPrompt = ""
        let decoder = JSONDecoder()

        // Process requests until stdin closes
        while let line = readLine(strippingNewline: true) {
            guard !line.isEmpty else { continue }

            // Parse request
            guard let data = line.data(using: .utf8) else {
                printJSON(FixResponse.fail("Invalid UTF-8 input"))
                continue
            }

            let request: FixRequest
            do {
                request = try decoder.decode(FixRequest.self, from: data)
            } catch {
                printJSON(FixResponse.fail("Invalid JSON: \(error.localizedDescription)"))
                continue
            }

            // Validate required fields
            guard !request.system.isEmpty else {
                printJSON(FixResponse.fail("System prompt cannot be empty"))
                continue
            }
            guard !request.text.isEmpty else {
                printJSON(FixResponse.fail("Text cannot be empty"))
                continue
            }

            // Create or reuse fixer based on system prompt
            if currentFixer == nil || currentSystemPrompt != request.system {
                currentSystemPrompt = request.system
                currentFixer = GrammarFixer(instructions: request.system)
                currentFixer?.prewarm()
            }

            // Process the request
            guard let fixer = currentFixer else {
                printJSON(FixResponse.fail("Failed to initialize fixer"))
                continue
            }

            do {
                let result = try await fixer.fix(prompt: request.fullPrompt)
                printJSON(FixResponse.ok(result))
            } catch {
                printJSON(FixResponse.fail(error.localizedDescription))
            }
        }
    }

    // MARK: - Helpers

    static func printJSON(_ value: FixResponse) {
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(value),
              let json = String(data: data, encoding: .utf8) else {
            fputs("{\"success\":false,\"error\":\"JSON encoding failed\"}\n", stdout)
            fflush(stdout)
            return
        }
        print(json)
        fflush(stdout)
    }

    static func printUsage() {
        fputs("""
        Usage: apple-ai-cli <command>

        Commands:
          check   Check if Apple Intelligence is available
          serve   Start server mode (recommended)

        Server mode uses JSONL protocol over stdin/stdout:
          Request:  {"system": "...", "user_prompt": "...", "text": "..."}
          Response: {"success": true, "result": "..."} or {"success": false, "error": "..."}

        The server keeps the LanguageModelSession warm for efficient repeated calls.

        """, stderr)
    }
}
