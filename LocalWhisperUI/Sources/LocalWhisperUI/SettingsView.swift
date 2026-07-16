import SwiftUI
import AppKit

// MARK: - Settings window shell
//
// Custom Window scene (not the SwiftUI Settings scene) so the app fully owns
// chrome, sizing, and activation. Layout: a permanently graphite sidebar on
// the left (brand identity, independent of system appearance) and an adaptive
// content area on the right. The hosting NSWindow is resolved through
// WindowAccessor — never NSApp.keyWindow guessing.

struct SettingsView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var selection: SettingsSection = .recording
    @SceneStorage("settings.selection") private var storedSelection: String = SettingsSection.recording.rawValue
    @State private var hostWindow: NSWindow?

    var body: some View {
        HStack(spacing: 0) {
            SettingsSidebar(selection: $selection)

            detail
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Theme.Surface.window)
        }
        .ignoresSafeArea()
        .frame(
            minWidth: 880, idealWidth: 960, maxWidth: .infinity,
            minHeight: 620, idealHeight: 680, maxHeight: .infinity
        )
        .background(
            WindowAccessor { window in
                guard hostWindow !== window else { return }
                hostWindow = window
                SettingsWindowChrome.configure(window)
                SettingsWindowChrome.bringForward(window)
            }
        )
        .onAppear {
            if let restored = SettingsSection(rawValue: storedSelection) {
                selection = restored
            }
            if let forced = LaunchFlags.initialPanel {
                selection = forced
            }
            ActivationPolicy.shared.acquire()
            // Clear focus so DeferredTextFields don't swallow the Right Option
            // hotkey while the Settings window is key. Without this, double-tap
            // registers start + stop because the focused field consumes one edge.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                hostWindow?.makeFirstResponder(nil)
            }
        }
        .onDisappear {
            ActivationPolicy.shared.release()
        }
        .onChange(of: selection) { _, newValue in
            storedSelection = newValue.rawValue
            // Drop focus when navigating between panels so a focused field
            // in one panel can't continue intercepting hotkeys.
            hostWindow?.makeFirstResponder(nil)
        }
    }

    // MARK: - Detail panels

    private var detail: some View {
        ZStack {
            panelContent
                .id(selection)
                .transition(
                    reduceMotion
                        ? .opacity
                        : .asymmetric(
                            insertion: .opacity.combined(with: .offset(y: 6)),
                            removal: .opacity
                        )
                )
        }
        .animation(reduceMotion ? nil : Theme.Motion.panelSwitch, value: selection)
    }

    @ViewBuilder
    private var panelContent: some View {
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

// MARK: - Sidebar

private struct SettingsSidebar: View {
    @Binding var selection: SettingsSection
    @Environment(AppState.self) private var appState

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(.top, 54)   // clears the traffic lights
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.bottom, Theme.Spacing.xl)

            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                    ForEach(SettingsSection.groups, id: \.title) { group in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(group.title)
                                .font(.system(size: 10.5, weight: .semibold))
                                .kerning(0.8)
                                .foregroundStyle(Theme.Surface.sidebarTextTertiary)
                                .padding(.horizontal, Theme.Spacing.m)
                                .padding(.bottom, 3)
                            ForEach(group.sections) { section in
                                SidebarRow(
                                    section: section,
                                    isSelected: selection == section
                                ) {
                                    selection = section
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, Theme.Spacing.m)
            }
            .scrollIndicators(.never)

            Spacer(minLength: Theme.Spacing.s)

            footer
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.bottom, Theme.Spacing.l)
        }
        .frame(width: 224)
        .background(
            LinearGradient(
                colors: [Theme.Surface.sidebarTop, Theme.Surface.sidebarBottom],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .overlay(alignment: .trailing) {
            Rectangle()
                .fill(Theme.Surface.sidebarStroke)
                .frame(width: 1)
        }
        .environment(\.colorScheme, .dark)
    }

    private var header: some View {
        HStack(spacing: Theme.Spacing.m - 2) {
            ZStack {
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(Theme.Brand.mintDark.opacity(0.14))
                Image(systemName: "waveform")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(Theme.Brand.mintDark)
                    .symbolRenderingMode(.hierarchical)
            }
            .frame(width: 34, height: 34)
            .overlay(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .strokeBorder(Theme.Brand.mintDark.opacity(0.25), lineWidth: 1)
            )

            VStack(alignment: .leading, spacing: 1) {
                Text("Local Whisper")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundStyle(Theme.Surface.sidebarTextPrimary)
                Text("Settings")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Surface.sidebarTextSecondary)
            }
            .lineLimit(1)
        }
    }

    private var footer: some View {
        HStack(spacing: Theme.Spacing.s) {
            Circle()
                .fill(connectionColor)
                .frame(width: 7, height: 7)
            Text(connectionText)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Surface.sidebarTextSecondary)
                .lineLimit(1)
            Spacer(minLength: 0)
        }
        .padding(Theme.Spacing.s + 2)
        .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: Theme.Radius.small + 2))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.small + 2)
                .strokeBorder(Color.white.opacity(0.06), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Service \(connectionText)")
    }

    private var connectionColor: Color {
        switch appState.connectionState {
        case .connected:    return Theme.Brand.mintDark
        case .connecting:   return .secondary
        case .disconnected: return Color(hex: 0xFFB454)
        }
    }

    private var connectionText: String {
        switch appState.connectionState {
        case .connected:    return "Service connected"
        case .connecting:   return "Connecting…"
        case .disconnected: return "Service not running"
        }
    }
}

private struct SidebarRow: View {
    let section: SettingsSection
    let isSelected: Bool
    let action: () -> Void

    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.s + 1) {
                Image(systemName: section.symbol)
                    .font(.system(size: 12.5, weight: .semibold))
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(isSelected ? Theme.Brand.mintDark : Theme.Surface.sidebarTextSecondary)
                    .frame(width: 19)

                Text(section.title)
                    .font(Theme.Typography.bodyEmphasized)
                    .foregroundStyle(isSelected ? Theme.Surface.sidebarTextPrimary : Theme.Surface.sidebarTextSecondary)

                Spacer(minLength: 0)
            }
            .padding(.horizontal, Theme.Spacing.m - 2)
            .padding(.vertical, 7)
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.small + 2))
            .background {
                RoundedRectangle(cornerRadius: Theme.Radius.small + 2, style: .continuous)
                    .fill(
                        isSelected
                            ? Theme.Brand.mintDark.opacity(0.14)
                            : (hovering ? Color.white.opacity(0.05) : Color.clear)
                    )
            }
            .overlay {
                if isSelected {
                    RoundedRectangle(cornerRadius: Theme.Radius.small + 2, style: .continuous)
                        .strokeBorder(Theme.Brand.mintDark.opacity(0.22), lineWidth: 1)
                }
            }
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .animation(Theme.Motion.hover, value: hovering)
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}

// MARK: - Sections

enum SettingsSection: String, CaseIterable, Identifiable, Hashable {
    case recording
    case transcription
    case grammar
    case vocabulary
    case voice
    case shortcuts
    case output
    case activity
    case advanced
    case about

    var id: String { rawValue }

    struct Group {
        let title: String
        let sections: [SettingsSection]
    }

    static let groups: [Group] = [
        Group(title: "DICTATION", sections: [.recording, .transcription, .grammar, .vocabulary]),
        Group(title: "TOOLS", sections: [.voice, .shortcuts, .output]),
        Group(title: "APP", sections: [.activity, .advanced, .about]),
    ]

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
        case .recording:    return "Trigger key, microphone handling, and audio cleanup."
        case .transcription: return "Choose and tune the on-device speech engine."
        case .grammar:      return "An optional cleanup pass over every transcript."
        case .voice:        return "Read text aloud and speak punctuation while dictating."
        case .vocabulary:   return "Teach Local Whisper your names, jargon, and slang."
        case .output:       return "Overlay, sounds, paste behavior, and history."
        case .shortcuts:    return "Global keybindings that transform selected text."
        case .activity:     return "Your dictation usage at a glance."
        case .advanced:     return "Service status, permissions, storage, and diagnostics."
        case .about:        return "Version, credits, and the tutorial."
        }
    }

    var symbol: String {
        switch self {
        case .recording:    return "mic.fill"
        case .transcription: return "waveform"
        case .grammar:      return "text.badge.checkmark"
        case .voice:        return "speaker.wave.2.fill"
        case .vocabulary:   return "character.book.closed.fill"
        case .output:       return "rectangle.on.rectangle"
        case .shortcuts:    return "command"
        case .activity:     return "chart.bar.fill"
        case .advanced:     return "slider.horizontal.3"
        case .about:        return "info.circle.fill"
        }
    }
}
