import SwiftUI

// MARK: - Shared UI components

// Deferred text field: binds locally, sends config update only on Return or focus loss.
// When `initialValue` changes from the outside (e.g. a config_snapshot arrives) and the
// field isn't focused, the local buffer syncs so the field never shows stale data.
struct DeferredTextField: View {
    let label: String
    let placeholder: String
    let initialValue: String
    let onCommit: (String) -> Void

    @State private var localValue: String
    @FocusState private var isFocused: Bool

    init(label: String, placeholder: String = "", initialValue: String, onCommit: @escaping (String) -> Void) {
        self.label = label
        self.placeholder = placeholder
        self.initialValue = initialValue
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
            .onChange(of: initialValue) { _, newValue in
                if !isFocused { localValue = newValue }
            }
    }
}

// Numeric variant (Int). Mirrors DeferredTextField's external-change behavior.
struct DeferredIntTextField: View {
    let label: String
    let placeholder: String
    let initialValue: Int
    let onCommit: (Int) -> Void

    @State private var localValue: String
    @FocusState private var isFocused: Bool

    init(label: String, placeholder: String = "", initialValue: Int, onCommit: @escaping (Int) -> Void) {
        self.label = label
        self.placeholder = placeholder
        self.initialValue = initialValue
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
            .onChange(of: initialValue) { _, newValue in
                if !isFocused { localValue = newValue == 0 ? "" : "\(newValue)" }
            }
    }

    private func commit() {
        if let v = Int(localValue) {
            onCommit(v)
        } else if localValue.isEmpty {
            onCommit(0)
        } else {
            // Non-parseable input: snap back to the last valid external value so the
            // field stops showing a value that the service never received.
            localValue = initialValue == 0 ? "" : "\(initialValue)"
        }
    }
}

// TextEditor variant for multi-line deferred input (e.g. WhisperKit custom prompt).
struct DeferredTextEditor: View {
    let initialValue: String
    let onCommit: (String) -> Void

    @State private var localValue: String
    @FocusState private var isFocused: Bool

    init(initialValue: String, onCommit: @escaping (String) -> Void) {
        self.initialValue = initialValue
        self.onCommit = onCommit
        _localValue = State(initialValue: initialValue)
    }

    var body: some View {
        TextEditor(text: $localValue)
            .focused($isFocused)
            .onChange(of: isFocused) { _, focused in
                if !focused { onCommit(localValue) }
            }
            .onChange(of: initialValue) { _, newValue in
                if !isFocused { localValue = newValue }
            }
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
