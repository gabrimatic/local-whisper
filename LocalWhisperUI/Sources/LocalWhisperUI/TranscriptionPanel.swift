import SwiftUI

// MARK: - Transcription panel
//
// Single entry point: one "Speech-to-text model" section with a card per
// engine. Clicking a card's action button switches / downloads the engine,
// with an inline progress bar inside the card while the download runs. The
// active engine's knobs render below in a dedicated settings section.

struct TranscriptionPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            Form {
                ModelsSection()
                switch appState.config.transcription.engine {
                case "parakeet_v3": ParakeetSection()
                case "qwen3_asr":   Qwen3Section()
                case "whisperkit":  WhisperKitSection()
                default:            EmptyView()
                }
            }
            .formStyle(.grouped)
        }
    }
}

// MARK: - Models section (merged engine picker + management)

struct ModelsSection: View {
    @Environment(AppState.self) private var appState
    @State private var removalTarget: EngineStatus? = nil

    private var sortedEngines: [EngineStatus] {
        appState.engines.sorted { a, b in
            if a.active != b.active { return a.active && !b.active }
            return a.id < b.id
        }
    }

    var body: some View {
        Section {
            if appState.engines.isEmpty {
                Text("Waiting for service…")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(sortedEngines) { engine in
                    EngineCard(
                        engine: engine,
                        download: appState.downloadStates[engine.id],
                        onRequestRemove: { removalTarget = $0 }
                    )
                    if engine.id != sortedEngines.last?.id {
                        Divider()
                            .padding(.vertical, 2)
                    }
                }
            }
        } header: {
            SettingsSectionHeader(
                symbol: "cpu",
                title: "Speech-to-text model",
                description: "Pick the engine for transcription. Each model downloads on first use and is kept on disk; switching frees the previous one from memory."
            )
        }
        .confirmationDialog(
            removalTarget.map { "Remove \($0.name) cache?" } ?? "",
            isPresented: Binding(
                get: { removalTarget != nil },
                set: { if !$0 { removalTarget = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(removalButtonLabel, role: .destructive) {
                if let target = removalTarget {
                    appState.ipcClient?.sendEngineRemoveCache(target.id)
                }
                removalTarget = nil
            }
            Button("Cancel", role: .cancel) { removalTarget = nil }
        } message: {
            Text("The weights will re-download on next use. This frees disk but not RAM.")
        }
    }

    private var removalButtonLabel: String {
        guard let mb = removalTarget?.sizeMb, mb > 0 else { return "Remove" }
        return "Remove \(mb) MB"
    }
}

// MARK: - Engine card

private struct EngineCard: View {
    let engine: EngineStatus
    let download: DownloadProgress?
    let onRequestRemove: (EngineStatus) -> Void

    @Environment(AppState.self) private var appState

    private var isDownloading: Bool {
        guard let download else { return false }
        return download.phase == "downloading" || download.phase == "preparing" || download.phase == "warming"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            HStack(alignment: .top, spacing: Theme.Spacing.m) {
                Image(systemName: iconName)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(iconColor)
                    .frame(width: 24)
                    .padding(.top, 2)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: Theme.Spacing.xs) {
                        Text(engine.name)
                            .font(.system(size: 13, weight: .semibold))
                        StatusPill(text: pillText, tone: pillTone)
                    }
                    Text(engine.description)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if !isDownloading {
                        Text(detailLine)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer(minLength: Theme.Spacing.s)

                if !isDownloading {
                    actionButton
                }
            }

            if let download, isDownloading || download.phase == "error" {
                DownloadProgressBar(progress: download)
                    .padding(.leading, 32)  // align under the text column
            }
        }
        .padding(.vertical, Theme.Spacing.xs)
        .background(cardBackground)
    }

    @ViewBuilder
    private var cardBackground: some View {
        if engine.active {
            RoundedRectangle(cornerRadius: Theme.Radius.medium)
                .fill(Color.accentColor.opacity(0.04))
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.Radius.medium)
                        .stroke(Color.accentColor.opacity(0.18), lineWidth: 1)
                )
                .padding(-2)
        } else {
            Color.clear
        }
    }

    private var iconName: String {
        switch engine.id {
        case "parakeet_v3": return "waveform.badge.mic"
        case "qwen3_asr":   return "sparkle"
        case "whisperkit":  return "server.rack"
        default:            return "cpu"
        }
    }

    private var iconColor: Color {
        engine.active ? .accentColor : .secondary
    }

    private var pillText: String {
        if let d = download, d.phase == "error" { return "Failed" }
        if isDownloading { return "Downloading" }
        if engine.active { return "Active" }
        if engine.downloaded { return "Downloaded" }
        return "Not downloaded"
    }

    private var pillTone: Theme.Tone {
        if let d = download, d.phase == "error" { return .danger }
        if isDownloading { return .info }
        if engine.active { return .success }
        if engine.downloaded { return .info }
        return .neutral
    }

    private var detailLine: String {
        var parts: [String] = []
        if engine.downloaded, let mb = engine.sizeMb, mb > 0 {
            parts.append(formatSize(mb: mb))
        } else if !engine.downloaded {
            parts.append("downloads on first use")
        }
        if engine.warmed { parts.append("warmed") }
        if let repo = engine.hfRepo, !repo.isEmpty {
            parts.append(repo)
        }
        return parts.joined(separator: " · ")
    }

    private func formatSize(mb: Int) -> String {
        if mb >= 1024 {
            let gb = Double(mb) / 1024.0
            return String(format: "%.1f GB", gb)
        }
        return "\(mb) MB"
    }

    @ViewBuilder
    private var actionButton: some View {
        if engine.active {
            Label("In use", systemImage: "checkmark.circle.fill")
                .labelStyle(.iconOnly)
                .foregroundStyle(.green)
                .help("This engine is currently loaded.")
        } else if let d = download, d.phase == "error" {
            Button("Retry") {
                switchTo(engine.id)
            }
            .buttonStyle(.bordered)
        } else if engine.downloaded {
            HStack(spacing: Theme.Spacing.xs) {
                Button("Use") { switchTo(engine.id) }
                .buttonStyle(.bordered)
                Button(role: .destructive) {
                    onRequestRemove(engine)
                } label: {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .help("Remove this engine's weights from disk.")
            }
        } else if engine.cacheDir != nil {
            Button("Use & download") { switchTo(engine.id) }
            .buttonStyle(.bordered)
            .help("Switches to this engine and downloads the model.")
        } else {
            // WhisperKit: lives outside the HF cache; no progress bar available.
            Button("Use") { switchTo(engine.id) }
            .buttonStyle(.bordered)
            .help("WhisperKit stores its own models. Install whisperkit-cli via Homebrew first.")
        }
    }

    private func switchTo(_ id: String) {
        appState.config.transcription.engine = id
        appState.ipcClient?.sendEngineSwitch(id)
    }
}
