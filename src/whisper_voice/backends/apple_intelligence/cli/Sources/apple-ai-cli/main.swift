import Foundation
import FoundationModels

/// Apple Intelligence CLI for grammar correction
/// Usage:
///   apple-ai-cli check     - Check if Apple Intelligence is available
///   apple-ai-cli fix       - Read text from stdin, output corrected text to stdout
///
/// Exit codes:
///   0 - Success
///   1 - Apple Intelligence unavailable
///   2 - Model error
///   3 - Invalid arguments

// MARK: - Grammar Fixer with Session Instructions

/// Grammar fixer using Apple Intelligence with session-level instructions
final class GrammarFixer {
    private let session: LanguageModelSession

    init() {
        // Set instructions at session creation (best practice from Apple docs)
        session = LanguageModelSession {
            """
            You are a transcript editor for noisy speech-to-text.

            Mission:
            - Turn a messy transcript into clear, natural, well-written text.
            - Fix grammar, spelling, punctuation, and formatting.
            - Break run-on sentences into proper sentences with correct punctuation.
            - Fix words when the transcript obviously misheard words (example: feature vs future).
            - Preserve what the speaker intended. Do not invent new information.

            What you are allowed to do:
            1) Correct grammar and writing issues - reorder words and restructure sentences.
            2) Remove noise - filler words (um, uh, like, you know), stutters, repeats, false starts.
            3) Meaning-based corrections - replace wrong words if context strongly indicates a transcription error.
            4) Formatting - split into paragraphs, use bullet points for lists.

            Hard safety rules:
            - Do NOT add new facts, names, numbers, dates, or details.
            - Do NOT guess missing content. Keep unclear wording as-is.
            - Do NOT complete cut-off text.
            - NEVER change technical tokens: file paths, URLs, commands, code, API keys, model names, hotkeys, numbers, units.

            Output rules:
            - Output ONLY the final edited transcript.
            - No quotes. No explanations. No notes.
            """
        }
    }

    func fix(_ text: String) async throws -> String {
        // Check if already processing (serialize requests)
        guard !session.isResponding else {
            throw GrammarError.sessionBusy
        }

        // Send just the text to fix - instructions are already set
        let response = try await session.respond(to: "Fix this transcript:\n\(text)")
        return response.content
    }
}

enum GrammarError: Error, LocalizedError {
    case sessionBusy
    case unavailable(String)

    var errorDescription: String? {
        switch self {
        case .sessionBusy:
            return "Session is busy processing another request"
        case .unavailable(let reason):
            return "Apple Intelligence unavailable: \(reason)"
        }
    }
}

// MARK: - CLI Entry Point

@main
struct AppleAICLI {
    static func main() async {
        let args = CommandLine.arguments

        guard args.count >= 2 else {
            printUsage()
            exit(3)
        }

        let command = args[1]

        switch command {
        case "check":
            checkAvailability()
        case "fix":
            await fixGrammar()
        default:
            printUsage()
            exit(3)
        }
    }

    /// Check if Apple Intelligence is available (using isAvailable shorthand)
    static func checkAvailability() {
        let model = SystemLanguageModel.default

        // Use isAvailable for quick check
        guard !model.isAvailable else {
            print("available")
            exit(0)
        }

        // Get detailed reason for unavailability
        switch model.availability {
        case .available:
            print("available")
            exit(0)
        case .unavailable(let reason):
            switch reason {
            case .appleIntelligenceNotEnabled:
                fputs("unavailable:apple_intelligence_not_enabled\n", stderr)
            case .deviceNotEligible:
                fputs("unavailable:device_not_eligible\n", stderr)
            case .modelNotReady:
                fputs("unavailable:model_not_ready\n", stderr)
            @unknown default:
                fputs("unavailable:unknown_reason\n", stderr)
            }
            exit(1)
        @unknown default:
            fputs("unavailable:unknown_state\n", stderr)
            exit(1)
        }
    }

    /// Fix grammar - read text from stdin, output corrected text to stdout
    static func fixGrammar() async {
        // Quick availability check
        guard SystemLanguageModel.default.isAvailable else {
            fputs("ERROR:Apple Intelligence not available\n", stderr)
            exit(1)
        }

        // Read all input from stdin
        var inputLines: [String] = []
        while let line = readLine(strippingNewline: false) {
            inputLines.append(line)
        }
        let input = inputLines.joined().trimmingCharacters(in: .whitespacesAndNewlines)

        guard !input.isEmpty else {
            fputs("ERROR:No input provided\n", stderr)
            exit(2)
        }

        // Create fixer and process
        let fixer = GrammarFixer()

        do {
            let corrected = try await fixer.fix(input)
            // Output the response content (no trailing newline, let the caller handle it)
            print(corrected, terminator: "")
        } catch {
            fputs("ERROR:\(error.localizedDescription)\n", stderr)
            exit(2)
        }
    }

    static func printUsage() {
        fputs("""
        Usage: apple-ai-cli <command>

        Commands:
          check   Check if Apple Intelligence is available
          fix     Read text from stdin, output corrected text to stdout

        The 'fix' command reads raw text from stdin and outputs
        grammar-corrected text to stdout. Instructions are built-in.

        Example:
          echo "um so like I want to test this" | apple-ai-cli fix

        """, stderr)
    }
}
