import SwiftUI
import AppKit

// MARK: - Onboarding view

struct OnboardingView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var step: Step = .welcome

    fileprivate enum Step: Int, CaseIterable {
        case welcome
        case permissions
        case backend
        case ready

        var title: String {
            switch self {
            case .welcome:     return "Welcome to Local Whisper"
            case .permissions: return "Two macOS permissions"
            case .backend:     return "Choose your grammar pass"
            case .ready:       return "You're set"
            }
        }

        var subtitle: String {
            switch self {
            case .welcome:     return "What it does, and how it talks to your Mac."
            case .permissions: return "Both are required for global dictation."
            case .backend:     return "Optional. You can change this any time."
            case .ready:       return "Try a recording when you're ready."
            }
        }

        var icon: String {
            switch self {
            case .welcome:     return "waveform.badge.mic"
            case .permissions: return "lock.shield"
            case .backend:     return "wand.and.stars"
            case .ready:       return "checkmark.seal"
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.6)
            content
                .frame(minHeight: 360, alignment: .topLeading)
            Divider().opacity(0.6)
            footer
        }
        .frame(minWidth: 560, minHeight: 540)
        .background(.background)
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .center, spacing: Theme.Spacing.l - 2) {
            SectionIcon(symbol: step.icon, tint: .accentColor, diameter: 44, fontSize: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(step.title)
                    .font(Theme.Typography.headline)
                Text(step.subtitle)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            stepIndicator
        }
        .padding(Theme.Spacing.xl)
    }

    private var stepIndicator: some View {
        HStack(spacing: 6) {
            ForEach(Step.allCases, id: \.self) { s in
                Capsule()
                    .fill(s == step ? Color.accentColor : Color.secondary.opacity(0.25))
                    .frame(width: s == step ? 18 : 6, height: 6)
                    .animation(reduceMotion ? .none : .smooth(duration: 0.18), value: step)
            }
        }
        .accessibilityLabel("Step \(step.rawValue + 1) of \(Step.allCases.count)")
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome:     welcomeStep
        case .permissions: permissionsStep
        case .backend:     backendStep
        case .ready:       readyStep
        }
    }

    private var welcomeStep: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l + 2) {
            Text("Local Whisper turns your voice into text. Everything runs on your Mac. No cloud, no telemetry.")
                .font(Theme.Typography.body)
                .foregroundStyle(.primary)

            VStack(alignment: .leading, spacing: Theme.Spacing.m - 2) {
                bulletRow(icon: "option", title: "Double-tap Right Option (⌥)", subtitle: "Starts recording. Tap once or press Space to stop.")
                bulletRow(icon: "hand.tap.fill", title: "Hold-to-record", subtitle: "Hold the trigger past the double-tap window. Release to stop.")
                bulletRow(icon: "text.cursor", title: "Transform any selection", subtitle: "Ctrl-Shift-G to proofread, Ctrl-Shift-R to rewrite, Ctrl-Shift-P to make a prompt.")
                bulletRow(icon: "speaker.wave.2.fill", title: "Speak text aloud", subtitle: "⌥T reads the current selection with Kokoro TTS.")
            }
        }
        .padding(.horizontal, Theme.Spacing.xxl)
        .padding(.vertical, Theme.Spacing.l + 2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var permissionsStep: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l - 2) {
            permissionCard(
                icon: "mic.fill",
                tint: .red,
                title: "Microphone",
                description: "To capture your voice. Granted in System Settings → Privacy & Security → Microphone.",
                buttonTitle: "Open Microphone Settings",
                anchor: "Privacy_Microphone"
            )

            permissionCard(
                icon: "keyboard.fill",
                tint: .blue,
                title: "Accessibility",
                description: "To detect the global hotkey and read selected text. Granted to the wh helper in System Settings → Privacy & Security → Accessibility.",
                buttonTitle: "Open Accessibility Settings",
                anchor: "Privacy_Accessibility"
            )

            InlineNotice(
                kind: .info,
                text: "Both prompts also appear automatically the first time the service runs. You can grant later from Settings → Advanced."
            )
        }
        .padding(.horizontal, Theme.Spacing.xxl)
        .padding(.vertical, Theme.Spacing.l + 2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var backendStep: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            Text("Pick a grammar pass for your transcripts. You can always change this later.")
                .font(Theme.Typography.caption)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: Theme.Spacing.m - 2) {
                backendChoice(id: "apple_intelligence", title: "Apple Intelligence", subtitle: "On-device Foundation Models. Best default on Apple Silicon, macOS 15+.", icon: "sparkles", tint: .purple)
                backendChoice(id: "ollama",             title: "Ollama",             subtitle: "Local LLM via the Ollama app. Works on any Mac with a loaded model.", icon: "shippingbox.fill", tint: .blue)
                backendChoice(id: "lm_studio",          title: "LM Studio",          subtitle: "OpenAI-compatible local server. Start it via LM Studio's Developer tab.", icon: "server.rack", tint: .indigo)
                backendChoice(id: "none",               title: "Skip for now",       subtitle: "Transcription only, no grammar pass. Toggle on later in Settings.", icon: "xmark.circle.fill", tint: .secondary)
            }
        }
        .padding(.horizontal, Theme.Spacing.xxl)
        .padding(.vertical, Theme.Spacing.l + 2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var readyStep: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l - 2) {
            HStack(alignment: .center, spacing: Theme.Spacing.l - 2) {
                SectionIcon(symbol: "checkmark.seal.fill", tint: .green, diameter: 56, fontSize: 28)
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Setup complete")
                        .font(Theme.Typography.headline)
                    Text("The service is running quietly in the background. The menu bar icon is your status light.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
            }

            Divider()

            Text("Try this first")
                .font(Theme.Typography.captionEmphasized)
                .foregroundStyle(.secondary)
                .textCase(.uppercase)

            VStack(alignment: .leading, spacing: Theme.Spacing.m - 2) {
                bulletRow(icon: "1.circle.fill", title: "Place your cursor where you want text to appear", subtitle: "Any text field, in any app.")
                bulletRow(icon: "2.circle.fill", title: "Double-tap the trigger key, speak, then tap once to stop", subtitle: "Right Option (⌥) by default. Change it in Settings → Recording.")
                bulletRow(icon: "3.circle.fill", title: "The transcript lands on your clipboard", subtitle: "Or pastes at the cursor if you turn on \"Paste at cursor\" in Settings → Output.")
            }

            HStack(spacing: Theme.Spacing.s) {
                Image(systemName: "lightbulb.fill")
                    .foregroundStyle(.yellow)
                    .symbolRenderingMode(.hierarchical)
                Text("Say \"new line\", \"period\", \"comma\", or \"scratch that\" while dictating.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, Theme.Spacing.xxl)
        .padding(.vertical, Theme.Spacing.l + 2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Footer

    private var footer: some View {
        HStack {
            if step != .ready {
                Button("Skip setup") { finish() }
                    .buttonStyle(.borderless)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if step != .welcome {
                Button("Back") {
                    withAnimation(reduceMotion ? .none : .smooth(duration: 0.22)) {
                        step = Step(rawValue: step.rawValue - 1) ?? .welcome
                    }
                }
                .buttonStyle(.bordered)
            }

            if step != .ready {
                Button("Next") {
                    withAnimation(reduceMotion ? .none : .smooth(duration: 0.22)) {
                        step = Step(rawValue: step.rawValue + 1) ?? .ready
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.return)
            } else {
                Button("Get started") { finish() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.return)
            }
        }
        .padding(Theme.Spacing.xl)
    }

    // MARK: - Helpers

    private func bulletRow(icon: String, title: String, subtitle: String) -> some View {
        HStack(alignment: .top, spacing: Theme.Spacing.m) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
                .symbolRenderingMode(.hierarchical)
                .frame(width: 22, alignment: .center)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Theme.Typography.bodyEmphasized)
                Text(subtitle)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func permissionCard(icon: String, tint: Color, title: String, description: String, buttonTitle: String, anchor: String) -> some View {
        HStack(alignment: .top, spacing: Theme.Spacing.m) {
            SectionIcon(symbol: icon, tint: tint, diameter: 36, fontSize: 16)
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text(title)
                    .font(Theme.Typography.bodyEmphasized)
                Text(description)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button(buttonTitle) {
                    openPrefPane(anchor)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .padding(.top, Theme.Spacing.xs)
            }
            Spacer()
        }
        .padding(Theme.Spacing.l - 2)
        .cardSurface(radius: Theme.Radius.medium)
    }

    private func backendChoice(id: String, title: String, subtitle: String, icon: String, tint: Color) -> some View {
        let isCurrent = (id == "none" && !appState.config.grammar.enabled)
            || (id != "none" && appState.config.grammar.enabled && appState.config.grammar.backend == id)
        return Button {
            if id == "none" {
                appState.config.grammar.enabled = false
                appState.ipcClient?.sendBackendSwitch("none")
            } else {
                appState.config.grammar.backend = id
                appState.config.grammar.enabled = true
                appState.ipcClient?.sendBackendSwitch(id)
            }
            withAnimation(reduceMotion ? .none : .smooth(duration: 0.22)) { step = .ready }
        } label: {
            HStack(spacing: Theme.Spacing.m) {
                SectionIcon(symbol: icon, tint: tint)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: Theme.Spacing.xs + 2) {
                        Text(title).font(Theme.Typography.bodyEmphasized)
                        if isCurrent {
                            StatusPill(text: "Current", tone: .info)
                        }
                    }
                    Text(subtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .foregroundStyle(.tertiary)
            }
            .padding(Theme.Spacing.m)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.secondary.opacity(isCurrent ? 0.12 : 0.07),
                        in: RoundedRectangle(cornerRadius: Theme.Radius.medium))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.medium)
                    .strokeBorder(
                        isCurrent ? Color.accentColor.opacity(0.4) : Color.secondary.opacity(0.10),
                        lineWidth: isCurrent ? 1.5 : 1
                    )
            )
        }
        .buttonStyle(.plain)
        .accessibilityHint(isCurrent ? "Currently selected" : "Tap to select \(title)")
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

@MainActor
final class OnboardingPresenter {
    static let shared = OnboardingPresenter()

    private var window: NSWindow?

    private init() {}

    func present(with state: AppState) {
        if let existing = window {
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
            existing.makeKeyAndOrderFront(nil)
            existing.orderFrontRegardless()
            return
        }
        let hosting = NSHostingController(rootView: OnboardingView().environment(state))
        hosting.preferredContentSize = NSSize(width: 600, height: 580)
        let window = NSWindow(contentViewController: hosting)
        window.styleMask = [.titled, .closable, .fullSizeContentView]
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.title = ""
        window.isReleasedWhenClosed = false
        window.setContentSize(NSSize(width: 600, height: 580))
        window.setFrameAutosaveName("LocalWhisperOnboarding")
        if !window.setFrameUsingName("LocalWhisperOnboarding") {
            window.center()
        }
        window.level = .normal
        window.delegate = OnboardingWindowDelegate.shared
        self.window = window
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
    }

    fileprivate func didClose() {
        self.window = nil
        let anotherWindowOpen = NSApp.windows.contains { win in
            win.isVisible && win.title.localizedCaseInsensitiveContains("settings")
        }
        if !anotherWindowOpen {
            NSApp.setActivationPolicy(.accessory)
        }
    }
}

@MainActor
private final class OnboardingWindowDelegate: NSObject, NSWindowDelegate {
    static let shared = OnboardingWindowDelegate()

    nonisolated func windowWillClose(_ notification: Notification) {
        Task { @MainActor in
            OnboardingFlag.markCompleted()
            OnboardingPresenter.shared.didClose()
        }
    }
}
