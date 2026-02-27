import SwiftUI

// MARK: - Overlay pill view

struct OverlayView: View {
    var appState: AppState

    private let barWidth: Double = 140

    var body: some View {
        Group {
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
        .padding(.horizontal, 22)
        .padding(.vertical, 14)
        .frame(minWidth: 200)
        .glassEffect(.regular.interactive(false), in: .capsule)
        .overlay(Capsule().strokeBorder(.white.opacity(0.18), lineWidth: 1))
        .accessibilityLabel(pillAccessibilityLabel)
    }

    // MARK: - Recording

    private var recordingView: some View {
        VStack(spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "waveform")
                    .font(.system(size: 15))
                    .foregroundStyle(.primary)
                    .symbolEffect(.variableColor.iterative.reversing)

                Text(formattedDuration)
                    .font(.system(size: 17, weight: .bold, design: .monospaced))
                    .foregroundStyle(.primary)
                    .contentTransition(.numericText())
            }
            .frame(maxWidth: .infinity, alignment: .center)

            audioLevelBar
        }
    }

    // MARK: - Processing

    private var processingView: some View {
        HStack(spacing: 8) {
            ProgressView()
                .controlSize(.small)

            Text(appState.statusText.isEmpty ? "Transcribing..." : appState.statusText)
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    // MARK: - Done

    private var doneView: some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 16))
                .foregroundStyle(.green)
                .symbolEffect(.bounce, value: appState.phase)

            Text("Copied")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(.primary)
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    // MARK: - Error

    private var errorView: some View {
        HStack(spacing: 8) {
            Image(systemName: "xmark.circle.fill")
                .font(.system(size: 16))
                .foregroundStyle(.red)
                .symbolEffect(.bounce, value: appState.phase)

            Text(appState.statusText.isEmpty ? "Failed" : appState.statusText)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(.primary)
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    // MARK: - Speaking

    private var speakingView: some View {
        HStack(spacing: 10) {
            Image(systemName: "speaker.wave.2.fill")
                .font(.system(size: 15))
                .foregroundStyle(.primary)
                .symbolEffect(.variableColor.iterative.reversing)

            Text(appState.statusText.isEmpty ? "Speaking..." : appState.statusText)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(.primary)
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    // MARK: - RMS bar

    private var audioLevelBar: some View {
        ZStack(alignment: .leading) {
            Capsule()
                .fill(.secondary.opacity(0.25))
                .frame(width: barWidth, height: 3)

            Capsule()
                .fill(levelColor)
                .frame(width: levelBarWidth, height: 3)
        }
        .frame(maxWidth: .infinity, alignment: .center)
        .accessibilityLabel("Audio level")
        .accessibilityValue("\(Int(levelPercent))%")
    }

    private var levelPercent: Double {
        let rms = appState.rmsLevel
        guard rms > 0.001 else { return 0 }
        return max(0.0, min(1.0, log10(rms / 0.001) / 2.5)) * 100
    }

    private var levelBarWidth: Double {
        let rms = appState.rmsLevel
        guard rms > 0.001 else { return 0 }
        let scaled = max(0.0, min(1.0, log10(rms / 0.001) / 2.5))
        return scaled * barWidth
    }

    private var levelColor: Color {
        let rms = appState.rmsLevel
        if rms < 0.005 { return .secondary }
        if rms < 0.05 { return .green }
        return .orange
    }

    private var formattedDuration: String {
        let m = Int(appState.durationSeconds) / 60
        let s = Int(appState.durationSeconds) % 60
        return String(format: "%d:%02d", m, s)
    }

    // MARK: - Accessibility

    private var pillAccessibilityLabel: String {
        switch appState.phase {
        case .idle:
            return "Local Whisper idle"
        case .recording:
            return "Recording, \(String(format: "%.0f", appState.durationSeconds)) seconds"
        case .processing:
            return appState.statusText.isEmpty ? "Processing transcription" : appState.statusText
        case .done:
            return "Transcription complete, copied to clipboard"
        case .error:
            return appState.statusText.isEmpty ? "Transcription failed" : appState.statusText
        case .speaking:
            return appState.statusText.isEmpty ? "Speaking" : appState.statusText
        }
    }
}
