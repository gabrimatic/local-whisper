import SwiftUI
import AppKit

// MARK: - Settings root with sidebar

struct SettingsView: View {
    @Environment(AppState.self) private var appState
    @State private var selection: SettingsSection = .recording
    @SceneStorage("settings.selection") private var storedSelection: String = SettingsSection.recording.rawValue

    var body: some View {
        NavigationSplitView {
            sidebar
        } detail: {
            detail
                .frame(minWidth: 520, idealWidth: 600)
                .navigationTitle(selection.title)
                .navigationSubtitle(selection.subtitle)
        }
        .frame(minWidth: 780, minHeight: 540)
        .onAppear {
            if let restored = SettingsSection(rawValue: storedSelection) {
                selection = restored
            }
            Self.activateRegular()
            // Clear focus so DeferredTextFields don't swallow the Right Option
            // hotkey while the Settings window is key. Without this, double-tap
            // registers start + stop because the focused field consumes one edge.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
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
        List(SettingsSection.allCases, selection: $selection) { section in
            NavigationLink(value: section) {
                Label {
                    Text(section.title)
                } icon: {
                    Image(systemName: section.symbol)
                        .foregroundStyle(section.tint)
                }
            }
            .tag(section)
        }
        .listStyle(.sidebar)
        .navigationSplitViewColumnWidth(min: 190, ideal: 210, max: 260)
    }

    // MARK: - Detail panels

    @ViewBuilder
    private var detail: some View {
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

    @MainActor
    private static func activateRegular() {
        // Promote to a regular app while a Settings window is on screen so
        // it appears in Cmd+Tab and macOS treats it like an app, not a
        // floating utility window. Reverted in restoreAccessoryPolicy().
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
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
