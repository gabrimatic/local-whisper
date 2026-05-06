import SwiftUI
import AppKit

// MARK: - Settings root with sidebar

struct SettingsView: View {
    @Environment(AppState.self) private var appState
    @State private var selection: SettingsSection = .recording
    @SceneStorage("settings.selection") private var storedSelection: String = SettingsSection.recording.rawValue

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider()
            detail
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minWidth: 780, minHeight: 540)
        .background(Color(nsColor: .windowBackgroundColor))
        .onAppear {
            if let restored = SettingsSection(rawValue: storedSelection) {
                selection = restored
            }
            Self.activateRegular()
            Self.configureSettingsWindowChrome()
            // Clear focus so DeferredTextFields don't swallow the Right Option
            // hotkey while the Settings window is key. Without this, double-tap
            // registers start + stop because the focused field consumes one edge.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                Self.configureSettingsWindowChrome()
                NSApp.keyWindow?.makeFirstResponder(nil)
            }
        }
        .onChange(of: selection) { _, newValue in
            storedSelection = newValue.rawValue
            // Drop focus when navigating between panels so a focused field
            // in one panel can't continue intercepting hotkeys.
            NSApp.keyWindow?.makeFirstResponder(nil)
        }
        .onDisappear(perform: Self.restoreAccessoryPolicy)
    }

    // MARK: - Sidebar

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l) {
            SettingsSidebarHeader()
                .padding(.horizontal, Theme.Spacing.xl)
                .padding(.top, Theme.Spacing.xl)

            VStack(spacing: Theme.Spacing.xs) {
                ForEach(SettingsSection.allCases) { section in
                    SettingsSidebarRow(
                        section: section,
                        isSelected: selection == section
                    ) {
                        selection = section
                    }
                }
            }
            .padding(.horizontal, Theme.Spacing.m)

            Spacer(minLength: 0)
        }
        .frame(width: 228)
        .background(.regularMaterial)
    }

    // MARK: - Detail panels

    @ViewBuilder
    private var detail: some View {
        VStack(alignment: .leading, spacing: 0) {
            SettingsDetailHeader(section: selection)
                .padding(.horizontal, Theme.Spacing.xxxl)
                .padding(.top, Theme.Spacing.xl)
                .padding(.bottom, Theme.Spacing.s)

            switch selection {
            case .recording:    RecordingPanel().environment(appState)
            case .transcription: TranscriptionPanel().environment(appState)
            case .grammar:      GrammarPanel().environment(appState)
            case .voice:        VoicePanel().environment(appState)
            case .vocabulary:   VocabularyPanel().environment(appState)
            case .output:       OutputPanel().environment(appState)
            case .shortcuts:    ShortcutsPanel().environment(appState)
            case .activity:     ActivityPanel().environment(appState)
            case .advanced:     AdvancedPanel().environment(appState)
            case .about:        AboutView().environment(appState)
            }
        }
    }

    @MainActor
    private static func activateRegular() {
        // Promote to a regular app while a Settings window is on screen so
        // it appears in Cmd+Tab and macOS treats it like an app, not a
        // floating utility window. Reverted in restoreAccessoryPolicy().
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    @MainActor
    private static func configureSettingsWindowChrome() {
        guard let window = NSApp.keyWindow else { return }
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
    }

    @MainActor
    private static func restoreAccessoryPolicy() {
        // Defer the policy switch — SwiftUI tears the window down before this
        // fires, so checking immediately misses the case where another panel
        // is being opened in the same tick.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            let stillOpen = NSApp.windows.contains { win in
                win.isVisible && win.identifier?.rawValue.contains("Settings") == true
            }
            if !stillOpen {
                NSApp.setActivationPolicy(.accessory)
            }
        }
    }
}

// MARK: - Sidebar chrome

private struct SettingsSidebarHeader: View {
    var body: some View {
        HStack(spacing: Theme.Spacing.m) {
            ZStack {
                RoundedRectangle(cornerRadius: Theme.Radius.medium)
                    .fill(Theme.Brand.accent.opacity(0.16))
                Image(systemName: "waveform")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Theme.Brand.accent)
                    .symbolRenderingMode(.hierarchical)
            }
            .frame(width: 40, height: 40)
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.medium)
                    .strokeBorder(Theme.Brand.accent.opacity(0.20), lineWidth: 1)
            )

            VStack(alignment: .leading, spacing: 2) {
                Text("Local Whisper")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                Text("Settings")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
            .lineLimit(1)
        }
        .padding(.top, Theme.Spacing.xl)
    }
}

private struct SettingsSidebarRow: View {
    let section: SettingsSection
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.m) {
                Image(systemName: section.symbol)
                    .font(.system(size: 15, weight: .semibold))
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(isSelected ? section.tint : .secondary)
                    .frame(width: 22)

                VStack(alignment: .leading, spacing: 1) {
                    Text(section.title)
                        .font(Theme.Typography.bodyEmphasized)
                        .foregroundStyle(isSelected ? .primary : .secondary)
                    Text(section.sidebarSubtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)
            }
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.medium))
            .padding(.horizontal, Theme.Spacing.m)
            .padding(.vertical, 9)
            .background {
                if isSelected {
                    RoundedRectangle(cornerRadius: Theme.Radius.medium)
                        .fill(section.tint.opacity(0.16))
                        .overlay(
                            RoundedRectangle(cornerRadius: Theme.Radius.medium)
                                .strokeBorder(section.tint.opacity(0.20), lineWidth: 1)
                        )
                }
            }
        }
        .buttonStyle(.plain)
    }
}

private struct SettingsDetailHeader: View {
    let section: SettingsSection

    var body: some View {
        HStack(alignment: .center, spacing: Theme.Spacing.m) {
            SectionIcon(symbol: section.symbol, tint: section.tint, diameter: 34, fontSize: 15)

            VStack(alignment: .leading, spacing: 2) {
                Text(section.title)
                    .font(Theme.Typography.title)
                Text(section.subtitle)
                    .font(Theme.Typography.captionEmphasized)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)
        }
    }
}

// MARK: - Sidebar sections

enum SettingsSection: String, CaseIterable, Identifiable, Hashable {
    case recording
    case transcription
    case grammar
    case voice
    case vocabulary
    case output
    case shortcuts
    case activity
    case advanced
    case about

    var id: String { rawValue }

    var title: String {
        switch self {
        case .recording:    return "Recording"
        case .transcription: return "Transcription"
        case .grammar:      return "Grammar"
        case .voice:        return "Voice"
        case .vocabulary:   return "Vocabulary"
        case .output:       return "Output"
        case .shortcuts:    return "Shortcuts"
        case .activity:     return "Activity"
        case .advanced:     return "Advanced"
        case .about:        return "About"
        }
    }

    var subtitle: String {
        switch self {
        case .recording:    return "Hotkey, mic, audio cleanup"
        case .transcription: return "Choose and tune the speech engine"
        case .grammar:      return "Optional cleanup pass"
        case .voice:        return "Read aloud and dictation commands"
        case .vocabulary:   return "Replacements that fix recurring words"
        case .output:       return "Overlay, sounds, paste, history"
        case .shortcuts:    return "Global text-transform keybindings"
        case .activity:     return "Usage statistics"
        case .advanced:     return "Storage and diagnostics"
        case .about:        return "Version and credits"
        }
    }

    var sidebarSubtitle: String {
        switch self {
        case .recording:    return "Hotkey and mic"
        case .transcription: return "Speech engine"
        case .grammar:      return "Cleanup pass"
        case .voice:        return "Read aloud"
        case .vocabulary:   return "Replacements"
        case .output:       return "Paste and history"
        case .shortcuts:    return "Keybindings"
        case .activity:     return "Stats"
        case .advanced:     return "Diagnostics"
        case .about:        return "Credits"
        }
    }

    var symbol: String {
        switch self {
        case .recording:    return "mic.fill"
        case .transcription: return "waveform"
        case .grammar:      return "text.badge.checkmark"
        case .voice:        return "speaker.wave.2.fill"
        case .vocabulary:   return "character.book.closed"
        case .output:       return "rectangle.on.rectangle"
        case .shortcuts:    return "command"
        case .activity:     return "chart.bar.fill"
        case .advanced:     return "slider.horizontal.3"
        case .about:        return "info.circle.fill"
        }
    }

    var accent: Theme.SectionAccent {
        switch self {
        case .recording:    return .recording
        case .transcription: return .transcription
        case .grammar:      return .grammar
        case .voice:        return .voice
        case .vocabulary:   return .vocabulary
        case .output:       return .output
        case .shortcuts:    return .shortcuts
        case .activity:     return .activity
        case .advanced:     return .advanced
        case .about:        return .about
        }
    }

    @MainActor
    var tint: Color { accent.color }
}
