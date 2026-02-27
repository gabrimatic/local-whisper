import SwiftUI

// MARK: - Shared UI components

// Deferred text field: binds locally, sends config update only on Return or focus loss.
struct DeferredTextField: View {
    let label: String
    let placeholder: String
    let onCommit: (String) -> Void

    @State private var localValue: String
    @FocusState private var isFocused: Bool

    init(label: String, placeholder: String = "", initialValue: String, onCommit: @escaping (String) -> Void) {
        self.label = label
        self.placeholder = placeholder
        self.onCommit = onCommit
        _localValue = State(initialValue: initialValue)
    }

    var body: some View {
        TextField(label, text: $localValue)
            .focused($isFocused)
            .onSubmit { onCommit(localValue) }
            .onChange(of: isFocused) { _, focused in
                if !focused { onCommit(localValue) }
            }
    }
}

// Numeric variant (Int).
struct DeferredIntTextField: View {
    let label: String
    let placeholder: String
    let onCommit: (Int) -> Void

    @State private var localValue: String
    @FocusState private var isFocused: Bool

    init(label: String, placeholder: String = "", initialValue: Int, onCommit: @escaping (Int) -> Void) {
        self.label = label
        self.placeholder = placeholder
        self.onCommit = onCommit
        _localValue = State(initialValue: initialValue == 0 ? "" : "\(initialValue)")
    }

    var body: some View {
        TextField(label, text: $localValue)
            .focused($isFocused)
            .onSubmit { commit() }
            .onChange(of: isFocused) { _, focused in
                if !focused { commit() }
            }
    }

    private func commit() {
        if let v = Int(localValue) { onCommit(v) }
        else if localValue.isEmpty { onCommit(0) }
    }
}

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
