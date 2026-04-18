import SwiftUI
import AppKit

// MARK: - Settings root

struct SettingsView: View {
    @Environment(AppState.self) private var appState
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            GeneralSettingsView()
                .environment(appState)
                .tabItem { Label("General", systemImage: "gearshape") }
                .tag(0)

            AdvancedSettingsView()
                .environment(appState)
                .tabItem { Label("Advanced", systemImage: "slider.horizontal.3") }
                .tag(1)

            AboutView()
                .environment(appState)
                .tabItem { Label("About", systemImage: "info.circle") }
                .tag(2)
        }
        .frame(minWidth: 500, minHeight: 520)
        .padding(.top, 8)
        .onAppear(perform: Self.forceForeground)
        .onDisappear(perform: Self.restoreAccessoryPolicy)
    }

    // LSUIElement apps can't bring a window to the foreground without
    // first flipping activation policy to .regular. Policy is restored
    // in onDisappear.
    @MainActor
    private static func forceForeground() {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        NSApp.keyWindow?.makeKeyAndOrderFront(nil)
        NSApp.keyWindow?.orderFrontRegardless()
    }

    @MainActor
    private static func restoreAccessoryPolicy() {
        let anotherWindowOpen = NSApp.windows.contains { win in
            win.isVisible && win.title.localizedCaseInsensitiveContains("settings")
        }
        if !anotherWindowOpen {
            NSApp.setActivationPolicy(.accessory)
        }
    }
}
