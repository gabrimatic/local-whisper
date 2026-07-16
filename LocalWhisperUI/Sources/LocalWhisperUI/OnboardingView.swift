import SwiftUI
import AppKit

// MARK: - Onboarding view

struct OnboardingView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dismiss) private var dismiss

    @State private var step: Step = .welcome
    @State private var hostWindow: NSWindow?

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
            case .permissions: return "lock.shield.fill"
            case .backend:     return "wand.and.stars"
            case .ready:       return "checkmark.seal.fill"
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            hero
            ScrollView {
                content
                    .padding(.horizontal, Theme.Spacing.xxl)
                    .padding(.vertical, Theme.Spacing.xl)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: .infinity)
            Divider().opacity(0.6)
            footer
        }
        .frame(minWidth: 600, idealWidth: 620, minHeight: 580, idealHeight: 600)
        .background(Theme.Surface.window)
        .ignoresSafeArea()
        .background(
            WindowAccessor { window in
                guard hostWindow !== window else { return }
                hostWindow = window
                SettingsWindowChrome.configure(window)
                SettingsWindowChrome.bringForward(window)
            }
        )
        .onAppear {
            ActivationPolicy.shared.acquire()
        }
        .onDisappear {
            // Closing the window at any point counts as "seen it" — the
            // window-delegate behavior of the old hand-made NSWindow.
            OnboardingFlag.markCompleted()
            ActivationPolicy.shared.release()
        }
    }

    // MARK: - Hero band

    private var hero: some View {
        HStack(alignment: .center, spacing: Theme.Spacing.l - 2) {
            ZStack {
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .fill(Theme.Brand.mintDark.opacity(0.14))
                Image(systemName: step.icon)
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(Theme.Brand.mintDark)
                    .symbolRenderingMode(.hierarchical)
                    .contentTransition(.symbolEffect(.replace))
            }
            .frame(width: 46, height: 46)
            .overlay(
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .strokeBorder(Theme.Brand.mintDark.opacity(0.25), lineWidth: 1)
            )
            .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 2) {
                Text(step.title)
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Surface.sidebarTextPrimary)
                Text(step.subtitle)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Surface.sidebarTextSecondary)
            }
            Spacer()
            stepIndicator
        }
        .padding(.horizontal, Theme.Spacing.xxl)
        .padding(.vertical, Theme.Spacing.xl)
        .frame(maxWidth: .infinity)
        .background(
            LinearGradient(
                colors: [Theme.Surface.sidebarTop, Theme.Surface.sidebarBottom],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .environment(\.colorScheme, .dark)
    }

    private var stepIndicator: some View {
        HStack(spacing: 6) {
            ForEach(Step.allCases, id: \.self) { s in
                Capsule()
                    .fill(s == step ? Theme.Brand.mintDark : Color.white.opacity(0.22))
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

    private var transformSubtitle: String {
        // Render the live bindings, not hardcoded defaults — the user may
        // have rebound these in Settings.
        let s = appState.config.shortcuts
        var parts: [String] = []
        if !s.proofread.isEmpty { parts.append("\(KeyboardGlyph.display(s.proofread)) to proofread") }
        if !s.rewrite.isEmpty { parts.append("\(KeyboardGlyph.display(s.rewrite)) to rewrite") }
        if !s.promptEngineer.isEmpty { parts.append("\(KeyboardGlyph.display(s.promptEngineer)) to make a prompt") }
        return parts.isEmpty ? "Configure shortcuts in Settings → Shortcuts." : parts.joined(separator: ", ") + "."
    }

    private var welcomeStep: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l + 2) {
            Text("Local Whisper turns your voice into text. Built-in speech processing stays on this Mac after setup. No hosted speech API, no telemetry.")
                .font(Theme.Typography.body)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: Theme.Spacing.m - 2) {
                bulletRow(icon: "option", title: "Double-tap Right Option (⌥)", subtitle: "Starts recording. Tap once or press Space to stop.")
                bulletRow(icon: "hand.tap.fill", title: "Hold-to-record", subtitle: "Hold the trigger past the double-tap window. Release to stop.")
                bulletRow(icon: "text.cursor", title: "Transform any selection", subtitle: transformSubtitle)
                bulletRow(icon: "speaker.wave.2.fill", title: "Speak text aloud", subtitle: "\(KeyboardGlyph.display(appState.config.tts.speakShortcut)) reads the current selection with Kokoro TTS.")
            }
        }
    }

    private var permissionsStep: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l - 2) {
            if appState.connectionState != .connected {
                InlineNotice(
                    kind: .warning,
                    text: "Waiting for the background service — permission requests go through it and would be lost right now. This clears the moment it connects."
                )
            }

            permissionCard(
                icon: "mic.fill",
                tint: Theme.Tone.danger.color,
                title: "Microphone",
                description: "To capture your voice. If macOS has not asked yet, this sends the permission request now.",
                buttonTitle: "Request Microphone Access",
                action: {
                    appState.ipcClient?.sendAction("request_microphone_permission")
                }
            )

            permissionCard(
                icon: "keyboard.fill",
                tint: Theme.Brand.sky,
                title: "Accessibility",
                description: "To detect the global hotkey and read selected text. This sends the Accessibility request for the wh helper.",
                buttonTitle: "Request Accessibility Access",
                action: {
                    appState.ipcClient?.sendAction("request_accessibility_permission")
                }
            )

            InlineNotice(
                kind: .info,
                text: "If a permission was previously denied, macOS opens the matching System Settings page instead of showing the prompt again."
            )
        }
    }

    private var backendStep: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            Text("Pick a grammar pass for your transcripts. You can always change this later.")
                .font(Theme.Typography.caption)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                onboardingChoice(id: "apple_intelligence", title: "Apple Intelligence", subtitle: "On-device Foundation Models. Best default on Apple Silicon, macOS 26+.", icon: "sparkles", tint: Theme.Brand.sky)
                onboardingChoice(id: "ollama",             title: "Ollama",             subtitle: "Local LLM via the Ollama app. Works on any Mac with a loaded model.", icon: "shippingbox.fill", tint: Theme.Brand.accent)
                onboardingChoice(id: "lm_studio",          title: "LM Studio",          subtitle: "OpenAI-compatible local server. Start it via LM Studio's Developer tab.", icon: "server.rack", tint: Theme.Brand.accent)
                onboardingChoice(id: "none",               title: "Skip for now",       subtitle: "Transcription only, no grammar pass. Toggle on later in Settings.", icon: "xmark.circle.fill", tint: .secondary)
            }
        }
    }

    private var readyStep: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l - 2) {
            HStack(alignment: .center, spacing: Theme.Spacing.l - 2) {
                SectionIcon(symbol: "checkmark.seal.fill", tint: Theme.Tone.success.color, diameter: 56, fontSize: 28)
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
                    .foregroundStyle(Theme.Tone.warning.color)
                    .symbolRenderingMode(.hierarchical)
                Text("Say \"new line\", \"period\", \"comma\", or \"scratch that\" while dictating.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(Theme.Spacing.s + 2)
            .frame(maxWidth: .infinity, alignment: .leading)
            .tintedCard(Theme.Tone.warning.color, radius: Theme.Radius.medium)
        }
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
                .foregroundStyle(Theme.Brand.accent)
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

    private func permissionCard(icon: String, tint: Color, title: String, description: String, buttonTitle: String, action: @escaping () -> Void) -> some View {
        HStack(alignment: .top, spacing: Theme.Spacing.m) {
            SectionIcon(symbol: icon, tint: tint, diameter: 36, fontSize: 16)
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text(title)
                    .font(Theme.Typography.bodyEmphasized)
                Text(description)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button(buttonTitle, action: action)
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(appState.connectionState != .connected)
                .padding(.top, Theme.Spacing.xs)
            }
            Spacer()
        }
        .padding(Theme.Spacing.l - 2)
        .cardSurface(radius: Theme.Radius.medium)
    }

    private func onboardingChoice(id: String, title: String, subtitle: String, icon: String, tint: Color) -> some View {
        let isCurrent = (id == "none" && !appState.config.grammar.enabled)
            || (id != "none" && appState.config.grammar.enabled && appState.config.grammar.backend == id)
        return ChoiceCard(
            icon: icon,
            tint: tint,
            title: title,
            subtitle: subtitle,
            isSelected: isCurrent
        ) {
            if id == "none" {
                appState.config.grammar.enabled = false
                appState.ipcClient?.sendBackendSwitch("none")
            } else {
                appState.config.grammar.backend = id
                appState.config.grammar.enabled = true
                appState.ipcClient?.sendBackendSwitch(id)
            }
            withAnimation(reduceMotion ? .none : .smooth(duration: 0.22)) { step = .ready }
        }
    }

    private func finish() {
        OnboardingFlag.markCompleted()
        // Real dismissal: onboarding lives in a proper Window scene now. (In
        // the old hand-made NSWindow, dismiss() was a silent no-op — the
        // "Get started does nothing" bug.)
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

