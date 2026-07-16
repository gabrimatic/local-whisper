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
            .onSubmit { commit() }
            .onChange(of: isFocused) { _, focused in
                if !focused { commit() }
            }
            .onChange(of: initialValue) { _, newValue in
                if !isFocused { localValue = newValue }
            }
    }

    // Only real changes commit. Click-in/click-out used to fire a no-op
    // config write — which, for engine model fields, made the service unload
    // and reload the whole engine. (No lastSent-style de-dup here: the
    // service skips unchanged writes itself, and a de-dup that never reset
    // silently swallowed legitimate re-commits after a server-side revert.)
    private func commit() {
        guard localValue != initialValue else { return }
        onCommit(localValue)
    }
}

struct DeferredIntTextField: View {
    let label: String
    let placeholder: String
    let initialValue: Int
    /// When set, typed values clamp into this range and the FIELD shows the
    /// clamped value — otherwise the display could keep a number that was
    /// never saved.
    let clamp: ClosedRange<Int>?
    let onCommit: (Int) -> Void

    @State private var localValue: String
    @FocusState private var isFocused: Bool

    init(label: String, placeholder: String = "", initialValue: Int, clamp: ClosedRange<Int>? = nil, onCommit: @escaping (Int) -> Void) {
        self.label = label
        self.placeholder = placeholder
        self.initialValue = initialValue
        self.clamp = clamp
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
            let applied = clamp.map { min(max(v, $0.lowerBound), $0.upperBound) } ?? v
            if applied != v {
                localValue = "\(applied)"
            }
            if applied != initialValue {
                onCommit(applied)
            }
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
                if !focused, localValue != initialValue { onCommit(localValue) }
            }
            .onChange(of: initialValue) { _, newValue in
                if !isFocused { localValue = newValue }
            }
    }
}

// MARK: - Commit-on-release slider
//
// A plain Slider bound straight to a config Binding fires an IPC write and
// a full config.toml rewrite on EVERY drag tick (dozens per second). This
// wrapper keeps drags local and commits once, on release.
struct CommitSlider<Label: View>: View {
    let range: ClosedRange<Double>
    let step: Double
    let value: Double
    let onCommit: (Double) -> Void
    @ViewBuilder let label: (Double) -> Label

    @State private var localValue: Double
    @State private var dragging = false

    init(
        value: Double,
        in range: ClosedRange<Double>,
        step: Double,
        onCommit: @escaping (Double) -> Void,
        @ViewBuilder label: @escaping (Double) -> Label
    ) {
        self.range = range
        self.step = step
        self.value = value
        self.onCommit = onCommit
        self.label = label
        _localValue = State(initialValue: value)
    }

    var body: some View {
        HStack(spacing: Theme.Spacing.s) {
            Slider(value: $localValue, in: range, step: step) { editing in
                dragging = editing
                if !editing {
                    onCommit(localValue)
                }
            }
            .controlSize(.small)
            // Fixed track width: sliders next to short labels otherwise
            // stretch across the whole card and every row looks different.
            .frame(width: 210)
            label(localValue)
        }
        .onChange(of: value) { _, newValue in
            if !dragging { localValue = newValue }
        }
    }
}

// MARK: - Stepper with a monospaced value readout

struct StepperRowControl: View {
    let value: Int
    let range: ClosedRange<Int>
    let step: Int
    let display: String
    var displayWidth: CGFloat = 70
    let onChange: (Int) -> Void

    var body: some View {
        HStack(spacing: Theme.Spacing.s) {
            Text(display)
                .monoStat(width: displayWidth)
            Stepper("", value: Binding(get: { value }, set: onChange), in: range, step: step)
                .labelsHidden()
        }
    }
}

// MARK: - Restart hint row

struct RestartNote: View {
    @Environment(AppState.self) private var appState
    var message: String = "Requires a service restart to take effect."

    var body: some View {
        HStack(spacing: Theme.Spacing.s) {
            Image(systemName: "arrow.triangle.2.circlepath")
                .font(.system(size: 11, weight: .semibold))
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

// MARK: - Inline notice rows (used by panels for warnings / info)

struct InlineNotice: View {
    enum Kind { case info, warning, error, success }
    let kind: Kind
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Spacing.s) {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(tint)
                .symbolRenderingMode(.hierarchical)
                .padding(.top, 1)
            Text(text)
                .font(Theme.Typography.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(Theme.Spacing.s + 2)
        .background(tint.opacity(0.07), in: RoundedRectangle(cornerRadius: Theme.Radius.small + 2))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.small + 2)
                .strokeBorder(tint.opacity(0.16), lineWidth: 1)
        )
    }

    private var icon: String {
        switch kind {
        case .info:    return "info.circle.fill"
        case .warning: return "exclamationmark.triangle.fill"
        case .error:   return "xmark.octagon.fill"
        case .success: return "checkmark.seal.fill"
        }
    }

    private var tint: Color {
        switch kind {
        case .info:    return Theme.Brand.sky
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
        .overlay(Capsule().strokeBorder(tone.color.opacity(0.18), lineWidth: 1))
        .foregroundStyle(foreground)
        .accessibilityElement(children: .combine)
    }

    private var background: AnyShapeStyle {
        let opacity: Double = colorScheme == .dark ? 0.16 : 0.10
        return AnyShapeStyle(tone.color.opacity(opacity))
    }

    private var foreground: Color {
        switch tone {
        case .neutral: return .secondary
        default:       return tone.color
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

// MARK: - Download progress bar (inline, shown under sections that download)

struct DownloadProgressBar: View {
    let progress: DownloadProgress
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: Theme.Spacing.s) {
                Text(phaseLabel)
                    .font(Theme.Typography.captionEmphasized)
                    .foregroundStyle(toneColor)
                Spacer(minLength: Theme.Spacing.s)
                Text(byteLabel)
                    .font(Theme.Typography.mono)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }

            if isIndeterminate {
                ProgressView()
                    .progressViewStyle(.linear)
                    .tint(toneColor)
            } else {
                ProgressView(value: clampedValue, total: 1.0)
                    .progressViewStyle(.linear)
                    .tint(toneColor)
            }

            if let error = progress.error, !error.isEmpty {
                Text(error)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Tone.danger.color(for: colorScheme))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.top, 2)
    }

    private var clampedValue: Double {
        min(max(progress.percent, 0.0), 1.0)
    }

    private var isIndeterminate: Bool {
        progress.phase == "preparing" || progress.phase == "warming" || progress.total <= 0
    }

    private var tone: Theme.Tone {
        switch progress.phase {
        case "error":    return .danger
        case "ready":    return .success
        case "canceled": return .warning
        case "warming":  return .info
        default:         return .info
        }
    }

    private var toneColor: Color {
        tone.color(for: colorScheme)
    }

    private var phaseLabel: String {
        switch progress.phase {
        case "preparing":   return "Preparing download…"
        case "downloading": return "Downloading…"
        case "warming":     return "Warming up…"
        case "ready":       return "Ready"
        case "canceled":    return "Canceled"
        case "error":       return "Download failed"
        default:            return progress.phase.capitalized
        }
    }

    private var byteLabel: String {
        let percentText: String
        if progress.total > 0 && progress.phase == "downloading" {
            percentText = " · \(Int(clampedValue * 100)) %"
        } else {
            percentText = ""
        }
        if progress.total > 0 {
            return "\(formatMB(progress.bytes)) / \(formatMB(progress.total))\(percentText)"
        }
        if progress.bytes > 0 {
            return formatMB(progress.bytes)
        }
        return ""
    }

    private func formatMB(_ bytes: Int64) -> String {
        let mb = Double(bytes) / (1024.0 * 1024.0)
        if mb >= 1024 {
            let gb = mb / 1024.0
            return String(format: "%.2f GB", gb)
        }
        if mb >= 100 {
            return String(format: "%.0f MB", mb)
        }
        return String(format: "%.1f MB", mb)
    }
}

// MARK: - Hover highlight (subtle background change on cursor hover)

struct HoverHighlight: ViewModifier {
    @State private var hovering = false
    var cornerRadius: CGFloat = Theme.Radius.medium

    func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .fill(hovering ? Theme.Surface.hover : Color.clear)
            )
            .onHover { hovering = $0 }
            .animation(Theme.Motion.hover, value: hovering)
    }
}

extension View {
    func hoverHighlight(cornerRadius: CGFloat = Theme.Radius.medium) -> some View {
        modifier(HoverHighlight(cornerRadius: cornerRadius))
    }
}
