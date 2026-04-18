import SwiftUI
import AppKit
import UserNotifications

// MARK: - Shared app state (singleton for delegate bridge)

@MainActor
let sharedAppState = AppState()

// MARK: - App delegate

final class AppDelegate: NSObject, NSApplicationDelegate, @unchecked Sendable {
    private var overlayController: OverlayWindowController?
    private var wakeObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let state = sharedAppState
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }

        Task { @MainActor in
            state.setupIPC()
            state.ipcClient?.start()

            self.overlayController = OverlayWindowController(appState: state)

            self.installSleepWakeObservers(for: state)

            if !OnboardingFlag.hasCompleted {
                OnboardingPresenter.shared.present(with: state)
            }
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
    private var appState: AppState { sharedAppState }

    var body: some Scene {
        MenuBarExtra {
            MenuBarView()
                .environment(appState)
        } label: {
            Image(systemName: appState.menuBarIconName)
                .symbolEffect(.bounce, value: appState.phase)
        }
        .menuBarExtraStyle(.menu)

        Settings {
            SettingsView()
                .environment(appState)
        }
        .defaultSize(width: 580, height: 620)
        .windowResizability(.contentMinSize)
    }
}
