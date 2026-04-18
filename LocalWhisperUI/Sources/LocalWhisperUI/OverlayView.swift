import SwiftUI

// MARK: - Overlay pill view

struct OverlayView: View {
    var appState: AppState

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorScheme) private var colorScheme

    @State private var rmsHistory: [Double] = Array(repeating: 0, count: WaveformConfig.barCount)

    // Stable pill dimensions: the capsule never changes size between phases,
    // only the content inside cross-fades. Prevents the "freeze / shrink" the
    // user sees when recording → processing → done resizes the pill on each step.
    private static let pillWidth: CGFloat = 290
    private static let pillHeight: CGFloat = 46

    var body: some View {
        ZStack {
            content
                .id(appState.phase)
                .transition(.opacity)
        }
        .frame(width: Self.pillWidth, height: Self.pillHeight)
        .modifier(OverlayBackground(reduceTransparency: reduceTransparency))
        .overlay(
            Capsule().strokeBorder(strokeColor, lineWidth: 0.8)
        )
        .compositingGroup()
        .shadow(color: .black.opacity(reduceTransparency ? 0 : 0.18), radius: 18, x: 0, y: 8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(pillAccessibilityLabel)
        .accessibilityValue(pillAccessibilityValue)
        .animation(reduceMotion ? .none : .easeInOut(duration: 0.16), value: appState.phase)
        .onChange(of: appState.rmsLevel) { _, newValue in
            handleRMSSample(newValue)
        }
        .onChange(of: appState.phase) { _, newPhase in
            if newPhase == .recording {
                rmsHistory = Array(repeating: 0, count: WaveformConfig.barCount)
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch appState.phase {
        case .idle:
            EmptyView()
        case .recording:
            recordingView
        case .processing:
            processingView
        case .done:
            doneView
        case .error:
            errorView
        case .speaking:
            speakingView
        }
    }

    private var strokeColor: Color {
        if reduceTransparency { return Color.primary.opacity(0.18) }
        return colorScheme == .dark
            ? Color.white.opacity(0.18)
            : Color.black.opacity(0.10)
    }

    // MARK: - Recording

    private var recordingView: some View {
        HStack(alignment: .center, spacing: Theme.Spacing.m) {
            Image(systemName: "record.circle.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Color.red)
                .symbolRenderingMode(.hierarchical)
                .modifier(VariableColorIfMotionAllowed(reduceMotion: reduceMotion))
                .accessibilityHidden(true)

            Text(formattedDuration)
                .font(Theme.Typography.monoLarge)
                .foregroundStyle(.primary)
                .monospacedDigit()
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .contentTransition(.numericText())
                .accessibilityLabel("Recording duration")

            WaveformView(samples: rmsHistory, isReducedMotion: reduceMotion)
                .frame(width: WaveformConfig.totalWidth, height: 22)
                .accessibilityHidden(true)
        }
    }

    // MARK: - Processing

    private var processingView: some View {
        HStack(spacing: Theme.Spacing.s) {
            ProgressView()
                .controlSize(.small)
            Text(processingLabel)
                .font(Theme.Typography.bodyEmphasized)
                .foregroundStyle(.primary)
                .lineLimit(1)
                .truncationMode(.tail)
        }
    }

    private var processingLabel: String {
        let s = appState.statusText.trimmingCharacters(in: .whitespacesAndNewlines)
        return s.isEmpty ? "Transcribing…" : s
    }

    // MARK: - Done

    private var doneView: some View {
        HStack(alignment: .center, spacing: Theme.Spacing.s) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.green)
                .symbolRenderingMode(.hierarchical)
                .modifier(BounceIfMotionAllowed(value: appState.phase, reduceMotion: reduceMotion))
                .accessibilityHidden(true)

            Text(doneLabel)
                .font(Theme.Typography.bodyEmphasized)
                .foregroundStyle(.primary)
                .lineLimit(1)
        }
    }

    private var doneLabel: String {
        let s = appState.doneStatusText.trimmingCharacters(in: .whitespacesAndNewlines)
        return s.isEmpty ? "Copied!" : s
    }

    // MARK: - Error

    private var errorView: some View {
        HStack(alignment: .center, spacing: Theme.Spacing.s) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.orange)
                .symbolRenderingMode(.hierarchical)
                .modifier(BounceIfMotionAllowed(value: appState.phase, reduceMotion: reduceMotion))
                .accessibilityHidden(true)

            Text(errorLabel)
                .font(Theme.Typography.bodyEmphasized)
                .foregroundStyle(.primary)
                .lineLimit(1)
                .truncationMode(.tail)
        }
    }

    private var errorLabel: String {
        let s = appState.statusText.trimmingCharacters(in: .whitespacesAndNewlines)
        return s.isEmpty ? "Failed" : s
    }

    // MARK: - Speaking

    private var speakingView: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: "speaker.wave.2.fill")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.primary)
                .symbolRenderingMode(.hierarchical)
                .modifier(VariableColorIfMotionAllowed(reduceMotion: reduceMotion))
                .accessibilityHidden(true)
            Text(speakingLabel)
                .font(Theme.Typography.bodyEmphasized)
                .foregroundStyle(.primary)
                .lineLimit(1)
                .truncationMode(.tail)
        }
    }

    private var speakingLabel: String {
        let s = appState.statusText.trimmingCharacters(in: .whitespacesAndNewlines)
        return s.isEmpty ? "Speaking…" : s
    }

    // MARK: - RMS history handling

    private func handleRMSSample(_ rms: Double) {
        guard appState.phase == .recording else { return }
        let normalized = normalize(rms)
        rmsHistory.append(normalized)
        if rmsHistory.count > WaveformConfig.barCount {
            rmsHistory.removeFirst(rmsHistory.count - WaveformConfig.barCount)
        }
    }

    private func normalize(_ rms: Double) -> Double {
        guard rms > 0.001 else { return 0 }
        return max(0, min(1, log10(rms / 0.001) / 2.5))
    }

    // MARK: - Helpers

    private var formattedDuration: String {
        let total = Int(appState.durationSeconds)
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        if h > 0 {
            return String(format: "%d:%02d:%02d", h, m, s)
        }
        return String(format: "%d:%02d", m, s)
    }

    // MARK: - Accessibility

    private var pillAccessibilityLabel: String {
        switch appState.phase {
        case .idle:       return "Local Whisper idle"
        case .recording:  return "Recording"
        case .processing: return processingLabel
        case .done:       return "Transcription complete, copied to clipboard"
        case .error:      return errorLabel
        case .speaking:   return speakingLabel
        }
    }

    private var pillAccessibilityValue: String {
        switch appState.phase {
        case .recording:
            return "\(Int(appState.durationSeconds)) seconds, level \(Int(normalize(appState.rmsLevel) * 100)) percent"
        default:
            return ""
        }
    }
}

// MARK: - Waveform view

private enum WaveformConfig {
    static let barCount: Int = 28
    static let barWidth: CGFloat = 3
    static let barSpacing: CGFloat = 2
    static var totalWidth: CGFloat {
        CGFloat(barCount) * barWidth + CGFloat(barCount - 1) * barSpacing
    }
}

private struct WaveformView: View {
    let samples: [Double]
    let isReducedMotion: Bool

    var body: some View {
        GeometryReader { geo in
            HStack(alignment: .center, spacing: WaveformConfig.barSpacing) {
                ForEach(Array(samples.enumerated()), id: \.offset) { index, value in
                    Capsule()
                        .fill(barColor(for: value, position: index))
                        .frame(
                            width: WaveformConfig.barWidth,
                            height: max(2, geo.size.height * CGFloat(value))
                        )
                        .animation(isReducedMotion ? .none : .smooth(duration: 0.18), value: value)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height, alignment: .center)
        }
        .accessibilityHidden(true)
    }

    private func barColor(for value: Double, position: Int) -> Color {
        let recencyBoost = Double(position) / Double(max(1, samples.count - 1))
        let baseOpacity = 0.45 + recencyBoost * 0.55
        if value < 0.2 { return .secondary.opacity(baseOpacity * 0.7) }
        if value < 0.65 { return .green.opacity(baseOpacity) }
        return .orange.opacity(baseOpacity)
    }
}

// MARK: - Accessibility-aware effect modifiers

private struct VariableColorIfMotionAllowed: ViewModifier {
    let reduceMotion: Bool
    func body(content: Content) -> some View {
        if reduceMotion {
            content
        } else {
            content.symbolEffect(.variableColor.iterative.reversing)
        }
    }
}

private struct BounceIfMotionAllowed<V: Equatable>: ViewModifier {
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

private struct OverlayBackground: ViewModifier {
    let reduceTransparency: Bool
    func body(content: Content) -> some View {
        if reduceTransparency {
            content.background(.ultraThickMaterial, in: .capsule)
        } else {
            content.glassEffect(.regular.interactive(false), in: .capsule)
        }
    }
}
