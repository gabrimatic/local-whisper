import SwiftUI

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
    }
}
