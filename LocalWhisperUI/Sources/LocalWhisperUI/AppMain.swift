import SwiftUI
import AppKit
import UserNotifications

// MARK: - Shared app state (singleton for delegate bridge)

@MainActor
let sharedAppState = AppState()

// MARK: - Window identifiers

enum AppWindowID {
    static let settings = "settings"
    static let onboarding = "onboarding"
}

// MARK: - Debug launch flags
//
// Development / screenshot-tooling switches; harmless in normal launches.
//   --settings [panel]   open the settings window at launch (panel = rawValue)
//   --onboarding         present onboarding even when already completed
//   --panel-preview      open the menu bar panel content in a plain window
//   --appearance light|dark   force the app's appearance

enum LaunchFlags {
    static let openSettings = CommandLine.arguments.contains("--settings")
    static let showOnboarding = CommandLine.arguments.contains("--onboarding")
    static let panelPreview = CommandLine.arguments.contains("--panel-preview")

    static var initialPanel: SettingsSection? {
        guard let index = CommandLine.arguments.firstIndex(of: "--settings"),
              index + 1 < CommandLine.arguments.count else { return nil }
        return SettingsSection(rawValue: CommandLine.arguments[index + 1])
    }

    static var forcedAppearance: NSAppearance? {
        guard let index = CommandLine.arguments.firstIndex(of: "--appearance"),
              index + 1 < CommandLine.arguments.count else { return nil }
        switch CommandLine.arguments[index + 1] {
        case "light": return NSAppearance(named: .aqua)
        case "dark":  return NSAppearance(named: .darkAqua)
        default:      return nil
        }
    }
}

// MARK: - App delegate

final class AppDelegate: NSObject, NSApplicationDelegate, @unchecked Sendable {
    private var overlayController: OverlayWindowController?
    private var wakeObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let state = sharedAppState
        // Debug/screenshot launches skip the notification prompt — it would
        // sit modally over every capture.
        if !LaunchFlags.openSettings && !LaunchFlags.panelPreview && !LaunchFlags.showOnboarding {
            UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
        }

        Task { @MainActor in
            if let appearance = LaunchFlags.forcedAppearance {
                NSApp.appearance = appearance
            }

            state.setupIPC()
            state.ipcClient?.start()

            self.overlayController = OverlayWindowController(appState: state)

            self.installSleepWakeObservers(for: state)
            // First-run onboarding is opened by MenuBarLabel.onAppear — the
            // only launch-time hook with openWindow access.
        }
    }

    @MainActor
    private func installSleepWakeObservers(for state: AppState) {
        let center = NSWorkspace.shared.notificationCenter
        wakeObserver = center.addObserver(
            forName: NSWorkspace.didWakeNotification,
            object: nil,
            queue: .main
        ) { _ in
            Task { @MainActor in
                state.ipcClient?.sendAction("resync_audio")
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let observer = wakeObserver {
            NSWorkspace.shared.notificationCenter.removeObserver(observer)
            wakeObserver = nil
        }
        sharedAppState.ipcClient?.stopSync()
    }
}

// MARK: - App entry point

@main
struct LocalWhisperUIApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var appState: AppState { sharedAppState }

    var body: some Scene {
        MenuBarExtra {
            MenuBarPanel()
                .environment(appState)
                .tint(Theme.Brand.accent)
        } label: {
            MenuBarLabel(iconName: appState.menuBarIconName, phase: appState.phase, reduceMotion: reduceMotion)
        }
        .menuBarExtraStyle(.window)

        Window("Local Whisper Settings", id: AppWindowID.settings) {
            SettingsView()
                .environment(appState)
                .tint(Theme.Brand.accent)
        }
        .defaultSize(width: 960, height: 680)
        .windowResizability(.automatic)
        .windowStyle(.hiddenTitleBar)
        .defaultLaunchBehavior(LaunchFlags.openSettings ? .presented : .suppressed)
        .restorationBehavior(.disabled)

        Window("Welcome to Local Whisper", id: AppWindowID.onboarding) {
            OnboardingView()
                .environment(appState)
                .tint(Theme.Brand.accent)
        }
        .defaultSize(width: 620, height: 600)
        .windowResizability(.contentSize)
        .windowStyle(.hiddenTitleBar)
        .defaultLaunchBehavior(.suppressed)
        .restorationBehavior(.disabled)

        // Debug-only: renders the menu bar panel content in a plain window so
        // screenshot tooling can capture it without clicking the status item.
        Window("Panel Preview", id: "panel-preview") {
            MenuBarPanel()
                .environment(appState)
                .tint(Theme.Brand.accent)
                .frame(width: 336)
                .background(WindowAccessor { $0.makeKeyAndOrderFront(nil) })
        }
        .windowResizability(.contentSize)
        .defaultLaunchBehavior(LaunchFlags.panelPreview ? .presented : .suppressed)
        .restorationBehavior(.disabled)
    }
}

private struct MenuBarBounce<V: Equatable>: ViewModifier {
    let value: V
    let reduceMotion: Bool
    func body(content: Content) -> some View {
        if reduceMotion {
            content
        } else {
            content.symbolEffect(.bounce, value: value)
        }
    }
}

/// The status item label doubles as the launch hook for the debug
/// panel-preview window: it is the one view guaranteed to appear at launch,
/// and `defaultLaunchBehavior(.presented)` is only honored for the first
/// Window scene.
private struct MenuBarLabel: View {
    let iconName: String
    let phase: AppPhase
    let reduceMotion: Bool
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Image(systemName: iconName)
            .modifier(MenuBarBounce(value: phase, reduceMotion: reduceMotion))
            .onAppear {
                if LaunchFlags.panelPreview {
                    openWindow(id: "panel-preview")
                }
                if !OnboardingFlag.hasCompleted || LaunchFlags.showOnboarding {
                    openWindow(id: AppWindowID.onboarding)
                }
            }
    }
}
