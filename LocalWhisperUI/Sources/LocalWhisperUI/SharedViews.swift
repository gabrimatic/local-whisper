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
        TextField(label, text: $localValue, prompt: Text(label).foregroundStyle(.tertiary))
            .labelsHidden()
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
        TextField(label, text: $localValue, prompt: Text(label).foregroundStyle(.tertiary))
            .labelsHidden()
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
            return
        }
        // Empty or unparseable: snap back. Never overwrite a real value
        // with 0 just because the user deleted text mid-edit.
        localValue = initialValue == 0 ? "" : "\(initialValue)"
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

// MARK: - Restart hint row

struct RestartNote: View {
    @Environment(AppState.self) private var appState
    var message: String = "Requires service restart to take effect."

    var body: some View {
        HStack(spacing: Theme.Spacing.s) {
            Image(systemName: "info.circle")
                .foregroundStyle(.secondary)
            Text(message)
                .font(Theme.Typography.caption)
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

// MARK: - Settings section header (icon + title + description)

struct SettingsSectionHeader: View {
    let symbol: String
    let title: String
    var description: String? = nil

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.secondary)
                .frame(width: 14)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Theme.Typography.sectionHeader)
                if let description {
                    Text(description)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer()
        }
        .padding(.bottom, 2)
        .textCase(nil)
    }
}

// MARK: - Inline notice rows (used by panels for warnings / info)

struct InlineNotice: View {
    enum Kind { case info, warning, error, success }
    let kind: Kind
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Spacing.s) {
            Image(systemName: icon)
                .foregroundStyle(tint)
                .symbolRenderingMode(.hierarchical)
            Text(text)
                .font(Theme.Typography.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
    }

    private var icon: String {
        switch kind {
        case .info:    return "info.circle"
        case .warning: return "exclamationmark.triangle.fill"
        case .error:   return "xmark.octagon.fill"
        case .success: return "checkmark.seal.fill"
        }
    }

    private var tint: Color {
        switch kind {
        case .info:    return .secondary
        case .warning: return Theme.Tone.warning.color
        case .error:   return Theme.Tone.danger.color
        case .success: return Theme.Tone.success.color
        }
    }
}

// MARK: - Status pill (used in panel headers / activity / connection state)

struct StatusPill: View {
    let text: String
    let tone: Theme.Tone

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(tone.color)
                .frame(width: 6, height: 6)
            Text(text)
                .font(Theme.Typography.captionEmphasized)
                .lineLimit(1)
        }
        .padding(.horizontal, Theme.Spacing.s)
        .padding(.vertical, 3)
        .background(background, in: Capsule())
        .foregroundStyle(foreground)
        .accessibilityElement(children: .combine)
    }

    private var background: AnyShapeStyle {
        let opacity: Double = colorScheme == .dark ? 0.22 : 0.14
        return AnyShapeStyle(tone.color.opacity(opacity))
    }

    private var foreground: Color {
        switch tone {
        case .neutral: return .secondary
        case .success: return colorScheme == .dark ? .green : Color(nsColor: .systemGreen).mix(with: .black, by: 0.25)
        case .warning: return colorScheme == .dark ? .orange : Color(nsColor: .systemOrange).mix(with: .black, by: 0.25)
        case .danger:  return colorScheme == .dark ? .red : Color(nsColor: .systemRed).mix(with: .black, by: 0.20)
        case .info:    return .accentColor
        }
    }
}

// MARK: - Trailing monospaced stat formatting

extension Text {
    /// Right-aligned monospaced numeric value, fixed width so sliders / steppers don't reflow.
    func monoStat(width: CGFloat) -> some View {
        self
            .font(Theme.Typography.mono)
            .foregroundStyle(.secondary)
            .frame(width: width, alignment: .trailing)
            .monospacedDigit()
    }
}

// MARK: - Hover highlight (subtle background change on cursor hover)

struct HoverHighlight: ViewModifier {
    @State private var hovering = false
    var cornerRadius: CGFloat = Theme.Radius.medium
    var baseOpacity: Double = 0.07
    var hoverOpacity: Double = 0.14

    func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .fill(Color.secondary.opacity(hovering ? hoverOpacity : baseOpacity))
            )
            .onHover { hovering = $0 }
            .animation(.easeOut(duration: 0.12), value: hovering)
    }
}

extension View {
    func hoverHighlight(
        cornerRadius: CGFloat = Theme.Radius.medium,
        base: Double = 0.07,
        hover: Double = 0.14
    ) -> some View {
        modifier(HoverHighlight(cornerRadius: cornerRadius, baseOpacity: base, hoverOpacity: hover))
    }
}
