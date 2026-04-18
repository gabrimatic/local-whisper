import SwiftUI
import AppKit

// MARK: - About panel

struct AboutView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var version: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
    }

    private var build: String {
        Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? ""
    }

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.xl) {
                hero
                actionRow
                creditsCard
                authorCard
                tutorialCard
            }
            .padding(Theme.Spacing.xxl)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
    }

    // MARK: - Hero

    private var hero: some View {
        VStack(spacing: Theme.Spacing.m) {
            ZStack {
                Circle()
                    .fill(LinearGradient(
                        colors: [Color.accentColor.opacity(0.30), Color.accentColor.opacity(0.05)],
                        startPoint: .top,
                        endPoint: .bottom
                    ))
                    .frame(width: 120, height: 120)
                Image(systemName: "waveform.badge.mic")
                    .font(.system(size: 56, weight: .regular))
                    .foregroundStyle(.primary)
                    .symbolRenderingMode(.hierarchical)
                    .modifier(BreatheIfMotionAllowed(reduceMotion: reduceMotion))
            }
            .accessibilityHidden(true)

            VStack(spacing: Theme.Spacing.xs) {
                Text("Local Whisper")
                    .font(Theme.Typography.title)
                Text(versionLine)
                    .font(Theme.Typography.mono)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            Text("100% local voice transcription for macOS.\nNo cloud, no tracking, no internet required.")
                .font(Theme.Typography.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
                .padding(.horizontal, Theme.Spacing.l)
        }
    }

    private var versionLine: String {
        if build.isEmpty || build == version {
            return "Version \(version)"
        }
        return "Version \(version) (\(build))"
    }

    // MARK: - Action row

    private var actionRow: some View {
        HStack(spacing: Theme.Spacing.m) {
            Button {
                openExternal("https://github.com/gabrimatic/local-whisper")
            } label: {
                Label("GitHub", systemImage: "chevron.left.forwardslash.chevron.right")
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)

            Button {
                openExternal("https://github.com/gabrimatic/local-whisper/releases")
            } label: {
                Label("Releases", systemImage: "tag")
            }
            .buttonStyle(.bordered)
            .controlSize(.large)

            Button {
                openExternal("https://gabrimatic.info")
            } label: {
                Label("Website", systemImage: "globe")
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
        }
    }

    // MARK: - Credits

    private var creditsCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            sectionLabel("Built on", icon: "shippingbox.fill")
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                creditCategory(title: "Speech", entries: [
                    ("Qwen3-ASR",   "Alibaba Qwen", "https://github.com/QwenLM/Qwen3-ASR"),
                    ("WhisperKit",  "argmaxinc",    "https://github.com/argmaxinc/WhisperKit"),
                    ("Kokoro-82M",  "hexgrad",       "https://huggingface.co/hexgrad/Kokoro-82M"),
                ])
                Divider().padding(.vertical, 2)
                creditCategory(title: "Grammar", entries: [
                    ("Apple Foundation Models", "developer.apple.com", "https://developer.apple.com/documentation/foundationmodels"),
                    ("Ollama",    "ollama.com",   "https://ollama.com"),
                    ("LM Studio", "lmstudio.ai",  "https://lmstudio.ai"),
                ])
            }
        }
        .padding(Theme.Spacing.l + 2)
        .cardSurface()
    }

    private func sectionLabel(_ text: String, icon: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
                .symbolRenderingMode(.hierarchical)
            Text(text)
                .font(Theme.Typography.captionEmphasized)
                .foregroundStyle(.secondary)
                .textCase(.uppercase)
        }
        .padding(.bottom, Theme.Spacing.m)
    }

    private func creditCategory(title: String, entries: [(String, String, String)]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(Theme.Typography.captionEmphasized)
                .foregroundStyle(.primary)
            ForEach(entries, id: \.0) { (name, attribution, url) in
                HStack(spacing: Theme.Spacing.s) {
                    Text(name)
                        .font(Theme.Typography.body)
                    Text("·").foregroundStyle(.tertiary)
                    Text(attribution)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button {
                        openExternal(url)
                    } label: {
                        Image(systemName: "arrow.up.forward.app")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help(url)
                    .accessibilityLabel("Open \(name) website")
                }
            }
        }
    }

    // MARK: - Author

    private var authorCard: some View {
        HStack(spacing: Theme.Spacing.l - 2) {
            Image(systemName: "person.crop.circle")
                .font(.system(size: 36))
                .foregroundStyle(.secondary)
                .symbolRenderingMode(.hierarchical)
            VStack(alignment: .leading, spacing: 2) {
                Text("Made by Soroush Yousefpour")
                    .font(Theme.Typography.bodyEmphasized)
                Text("MIT-licensed. Sole author. No telemetry.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("gabrimatic.info") {
                openExternal("https://gabrimatic.info")
            }
            .buttonStyle(.link)
        }
        .padding(Theme.Spacing.l)
        .cardSurface()
    }

    // MARK: - Tutorial

    private var tutorialCard: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: "play.circle.fill")
                .font(.title2)
                .foregroundStyle(Color.accentColor)
                .symbolRenderingMode(.hierarchical)
            VStack(alignment: .leading, spacing: 2) {
                Text("Replay tutorial")
                    .font(Theme.Typography.bodyEmphasized)
                Text("Walk through onboarding again at any time.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Replay") {
                OnboardingPresenter.shared.present(with: appState)
            }
            .buttonStyle(.bordered)
        }
        .padding(Theme.Spacing.l - 2)
        .tintedCard(.accentColor)
    }

    private func openExternal(_ string: String) {
        guard let url = URL(string: string) else { return }
        NSWorkspace.shared.open(url)
    }
}

private struct BreatheIfMotionAllowed: ViewModifier {
    let reduceMotion: Bool
    func body(content: Content) -> some View {
        if reduceMotion {
            content
        } else {
            content.symbolEffect(.breathe)
        }
    }
}
