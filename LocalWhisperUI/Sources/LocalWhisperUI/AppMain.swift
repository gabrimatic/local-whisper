import SwiftUI
import AppKit
import UserNotifications

// MARK: - Shared app state (singleton for delegate bridge)

@MainActor
let sharedAppState = AppState()

// MARK: - App delegate

final class AppDelegate: NSObject, NSApplicationDelegate, @unchecked Sendable {
    private var overlayController: OverlayWindowController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let state = sharedAppState
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }

        Task { @MainActor in
            state.setupIPC()
            state.ipcClient?.start()

            let controller = OverlayWindowController(appState: state)
            self.overlayController = controller
            controller.setup()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
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
