import SwiftUI
import AppKit

// MARK: - First launch onboarding

/// Lightweight onboarding that surfaces once per install. The service already
/// handles the heavy lifting (permission prompts, model download, engine
/// warm-up via setup.sh); this sheet orients the user to the core shortcut,
/// confirms permissions, and lets them set a grammar backend without hunting
/// through Settings.
struct OnboardingView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss

    @State private var step: Step = .welcome

    private enum Step: Int {
        case welcome
        case permissions
        case backend
        case ready
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            content
            Divider()
            footer
        }
        .frame(minWidth: 480, idealWidth: 520, minHeight: 380)
        .padding(0)
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "waveform.badge.mic")
                .font(.system(size: 28))
                .foregroundStyle(.primary)
                .symbolRenderingMode(.hierarchical)
            VStack(alignment: .leading, spacing: 2) {
                Text("Welcome to Local Whisper")
                    .font(.title3.weight(.semibold))
                Text(stepSubtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Text("\(step.rawValue + 1) / 4")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(16)
    }

    // MARK: Content

    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome:
            welcomeStep
        case .permissions:
            permissionsStep
        case .backend:
            backendStep
        case .ready:
            readyStep
        }
    }

    private var welcomeStep: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Local Whisper turns your voice into text. Everything runs on your Mac, nothing leaves the device.")
            Label("Double-tap Right Option (⌥) to record. Single-tap or Space to stop.", systemImage: "option")
            Label("Hold Right Option longer than the double-tap window for hold-to-record.", systemImage: "hand.tap")
            Label("Ctrl-Shift-G / R / P transforms selected text in any app.", systemImage: "text.cursor")
            Label("⌥T reads selected text aloud with Kokoro TTS.", systemImage: "speaker.wave.2")
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var permissionsStep: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Local Whisper needs two macOS permissions:")
            HStack(alignment: .top) {
                Image(systemName: "mic")
                VStack(alignment: .leading) {
                    Text("Microphone").font(.body.weight(.semibold))
                    Text("To capture your voice. Granted via System Settings → Privacy & Security → Microphone.")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                }
            }
            HStack(alignment: .top) {
                Image(systemName: "keyboard")
                VStack(alignment: .leading) {
                    Text("Accessibility").font(.body.weight(.semibold))
                    Text("To detect the global hotkey and read selected text. Grant to the `wh` process in System Settings → Privacy & Security → Accessibility.")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                }
            }
            HStack(spacing: 12) {
                Button("Open Accessibility Settings") {
                    openPrefPane("Privacy_Accessibility")
                }
                .buttonStyle(.bordered)
                Button("Open Microphone Settings") {
                    openPrefPane("Privacy_Microphone")
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var backendStep: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Pick a grammar backend (optional). You can always change this in Settings.")
            VStack(alignment: .leading, spacing: 8) {
                backendChoice(
                    id: "apple_intelligence",
                    title: "Apple Intelligence",
                    subtitle: "On-device Foundation Models. Best default on Apple Silicon, macOS 15+.",
                    icon: "sparkles"
                )
                backendChoice(
                    id: "ollama",
                    title: "Ollama",
                    subtitle: "Requires `ollama serve` running locally. Works on any Mac with a loaded model.",
                    icon: "cpu"
                )
                backendChoice(
                    id: "lm_studio",
                    title: "LM Studio",
                    subtitle: "OpenAI-compatible local server (Developer → Start Server in LM Studio).",
                    icon: "server.rack"
                )
                backendChoice(
                    id: "none",
                    title: "Skip for now",
                    subtitle: "Transcription only, no grammar. Toggle on in Settings whenever you're ready.",
                    icon: "xmark.circle"
                )
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var readyStep: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Setup complete. The service is running in the background.", systemImage: "checkmark.seal")
                .font(.body.weight(.semibold))
            Text("Tips for the first week:")
            Label("Speak naturally. The grammar pass handles most cleanup.", systemImage: "waveform")
            Label("Say \"new line\", \"period\", \"comma\", or \"scratch that\" as voice commands.", systemImage: "text.badge.minus")
            Label("Open Settings → Replacements to teach Local Whisper your vocabulary.", systemImage: "character.book.closed")
            Label("Run `wh doctor` in Terminal if anything misbehaves.", systemImage: "stethoscope")
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Footer

    private var footer: some View {
        HStack {
            Button("Skip") { finish() }
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)

            Spacer()

            if step != .welcome {
                Button("Back") { withAnimation { step = Step(rawValue: step.rawValue - 1) ?? .welcome } }
                    .buttonStyle(.bordered)
            }
            if step != .ready {
                Button("Next") { withAnimation { step = Step(rawValue: step.rawValue + 1) ?? .ready } }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.return)
            } else {
                Button("Get started") { finish() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.return)
            }
        }
        .padding(16)
    }

    // MARK: Helpers

    private var stepSubtitle: String {
        switch step {
        case .welcome:     return "What it does"
        case .permissions: return "macOS permissions"
        case .backend:     return "Grammar backend"
        case .ready:       return "You're set"
        }
    }

    private func backendChoice(id: String, title: String, subtitle: String, icon: String) -> some View {
        Button {
            if id == "none" {
                appState.config.grammar.enabled = false
                appState.ipcClient?.sendBackendSwitch("none")
            } else {
                appState.config.grammar.backend = id
                appState.config.grammar.enabled = true
                appState.ipcClient?.sendBackendSwitch(id)
            }
            withAnimation { step = .ready }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.title3)
                    .frame(width: 24)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.body.weight(.semibold))
                    Text(subtitle).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right").foregroundStyle(.tertiary)
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }

    private func openPrefPane(_ anchor: String) {
        let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(anchor)")!
        NSWorkspace.shared.open(url)
    }

    private func finish() {
        OnboardingFlag.markCompleted()
        dismiss()
    }
}


// MARK: - Completion flag

/// Tracks whether onboarding has been shown. Stored as a tiny file under
/// ``~/.whisper`` so uninstalling and reinstalling retriggers the flow.
enum OnboardingFlag {
    private static var path: URL {
        let dir = URL(fileURLWithPath: AppDirectories.whisper)
        return dir.appendingPathComponent(".onboarded")
    }

    static var hasCompleted: Bool {
        FileManager.default.fileExists(atPath: path.path)
    }

    static func markCompleted() {
        try? FileManager.default.createDirectory(
            at: path.deletingLastPathComponent(), withIntermediateDirectories: true
        )
        try? Data().write(to: path)
    }
}


// MARK: - Window presenter

/// Single source of truth for onboarding window lifetime. Used by both the
/// first-launch path and the About tab's "Replay Tutorial" button so we only
/// ever have one window, and it stays retained for its full lifetime rather
/// than leaking whenever someone presses the replay button.
@MainActor
final class OnboardingPresenter {
    static let shared = OnboardingPresenter()

    private var window: NSWindow?

    private init() {}

    func present(with state: AppState, title: String = "Welcome to Local Whisper") {
        if let existing = window {
            existing.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let hosting = NSHostingController(rootView: OnboardingView().environment(state))
        let window = NSWindow(contentViewController: hosting)
        window.styleMask = [.titled, .closable]
        window.title = title
        // Release the window naturally; keep a reference so ARC doesn't drop it
        // between presentation and the user's first interaction, and clear the
        // reference on close so a later "Replay Tutorial" click builds a fresh
        // one instead of resurrecting a closed window.
        window.isReleasedWhenClosed = false
        window.center()
        window.level = .normal
        window.delegate = OnboardingWindowDelegate.shared
        self.window = window
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    fileprivate func didClose() {
        self.window = nil
    }
}

@MainActor
private final class OnboardingWindowDelegate: NSObject, NSWindowDelegate {
    static let shared = OnboardingWindowDelegate()

    nonisolated func windowWillClose(_ notification: Notification) {
        Task { @MainActor in OnboardingPresenter.shared.didClose() }
    }
}
