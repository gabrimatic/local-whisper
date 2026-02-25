import SwiftUI

// MARK: - Shared UI components

struct RestartNote: View {
    @Environment(AppState.self) private var appState
    var message: String = "Requires service restart to take effect."

    var body: some View {
        HStack {
            Image(systemName: "info.circle")
                .foregroundStyle(.secondary)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button("Restart Service") {
                appState.ipcClient?.sendAction("restart")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
    }
}
