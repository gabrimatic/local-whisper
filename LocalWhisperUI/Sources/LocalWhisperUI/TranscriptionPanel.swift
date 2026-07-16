import SwiftUI

// MARK: - Transcription panel
//
// One "Speech-to-text model" section with a card per engine. A card's action
// button switches / downloads the engine, with an inline progress bar inside
// the card while the download runs. The active engine's knobs render below
// in a dedicated settings card.

struct TranscriptionPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        PanelScaffold(
            title: "Transcription",
            subtitle: "Choose and tune the on-device speech engine."
        ) {
            ModelsSection()
            switch appState.config.transcription.engine {
            case "parakeet_v3": ParakeetSection()
            case "qwen3_asr":   Qwen3Section()
            case "apple_speech": AppleSpeechSection()
            case "whisperkit":  WhisperKitSection()
            default:            EmptyView()
            }
        }
    }
}

// MARK: - Models section

struct ModelsSection: View {
    @Environment(AppState.self) private var appState
    @State private var removalTarget: EngineStatus? = nil
    // Engine id a switch was requested for. Drives the card spinner for
    // engines without download progress (Apple Speech, WhisperKit) and
    // disables the other cards while the service is busy switching.
    @State private var switchingTo: String? = nil
    @State private var switchTimeout: Task<Void, Never>? = nil

    private var sortedEngines: [EngineStatus] {
        appState.engines.sorted { a, b in
            if a.active != b.active { return a.active && !b.active }
            return a.id < b.id
        }
    }

    private var activeEngineID: String? {
        appState.engines.first(where: { $0.active })?.id
    }

    private var anyDownloadInFlight: Bool {
        appState.downloadStates.contains { key, value in
            key != "kokoro_tts" && (value.phase == "downloading" || value.phase == "preparing" || value.phase == "warming")
        }
    }

    /// Keys AND phases — a retry re-emits progress under the same key, so a
    /// key-only fingerprint missed the error -> downloading transition.
    private var downloadFingerprint: String {
        appState.downloadStates.map { "\($0.key):\($0.value.phase)" }.sorted().joined(separator: "|")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s + 2) {
            HStack(spacing: Theme.Spacing.s) {
                Image(systemName: "cpu")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.Brand.accent)
                    .frame(width: 16)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Speech-to-text model")
                        .font(Theme.Typography.sectionHeader)
                    Text("Model files stay on-device; Apple manages SpeechTranscriber language assets for its engine.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            .padding(.leading, 2)

            if appState.engines.isEmpty {
                VStack(spacing: 0) {
                    EmptyStateView(
                        icon: "antenna.radiowaves.left.and.right",
                        title: "Waiting for the service…",
                        message: "Engine details appear once the background service is connected."
                    )
                }
                .cardSurface()
            } else {
                VStack(spacing: Theme.Spacing.s) {
                    ForEach(sortedEngines) { engine in
                        EngineCard(
                            engine: engine,
                            download: appState.downloadStates[engine.id],
                            isSwitching: switchingTo == engine.id,
                            othersBusy: (switchingTo != nil && switchingTo != engine.id)
                                || (anyDownloadInFlight && appState.downloadStates[engine.id] == nil)
                                || appState.connectionState != .connected,
                            onSwitch: { requestSwitch(to: $0) },
                            onRequestRemove: { removalTarget = $0 }
                        )
                    }
                }
            }
        }
        .onChange(of: activeEngineID) { _, newActive in
            if let switching = switchingTo, newActive == switching {
                clearSwitching()
            }
        }
        .onChange(of: downloadFingerprint) { _, _ in
            // A progress stream started (or resumed after a failed attempt —
            // same key, new phase) for the requested engine: the inline bar
            // takes over from the card spinner.
            if let switching = switchingTo, let d = appState.downloadStates[switching],
               d.phase != "error" {
                clearSwitching()
            }
        }
        .onChange(of: appState.phase) { _, newPhase in
            // The service reported an error (e.g. "Busy — try again"): the
            // switch attempt is over.
            if newPhase == .error { clearSwitching() }
        }
        .confirmationDialog(
            removalTarget.map {
                $0.managedBy == "apple"
                    ? "Release \($0.name) language reservation?"
                    : "Remove \($0.name) cache?"
            } ?? "",
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
            Text(removalTarget?.managedBy == "apple"
                ? "Local Whisper will release its reservation. macOS decides when the shared language asset can be removed."
                : "The weights will re-download on next use. This frees disk but not RAM.")
        }
    }

    private var removalButtonLabel: String {
        if removalTarget?.managedBy == "apple" { return "Release" }
        guard let mb = removalTarget?.sizeMb, mb > 0 else { return "Remove" }
        return "Remove \(mb) MB"
    }

    private func requestSwitch(to id: String) {
        appState.ipcClient?.sendEngineSwitch(id)
        switchingTo = id
        switchTimeout?.cancel()
        switchTimeout = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 25_000_000_000)
            guard !Task.isCancelled else { return }
            switchingTo = nil
        }
    }

    private func clearSwitching() {
        switchTimeout?.cancel()
        switchTimeout = nil
        switchingTo = nil
    }
}

// MARK: - Engine card

private struct EngineCard: View {
    let engine: EngineStatus
    let download: DownloadProgress?
    /// A switch to THIS engine is in flight (no download stream yet).
    let isSwitching: Bool
    /// Another engine is switching/downloading: actions here would be
    /// silently rejected by the busy service, so gate them.
    let othersBusy: Bool
    let onSwitch: (String) -> Void
    let onRequestRemove: (EngineStatus) -> Void

    @Environment(AppState.self) private var appState
    @Environment(\.colorScheme) private var colorScheme

    private var isDownloading: Bool {
        guard let download else { return false }
        return download.phase == "downloading" || download.phase == "preparing" || download.phase == "warming"
    }

    /// Cancel is only honest while bytes are actually moving; "preparing"
    /// and "warming" ignore it server-side.
    private var canCancelDownload: Bool {
        download?.phase == "downloading"
    }

    /// Engines whose weights live outside the HF cache (WhisperKit) are
    /// externally managed — "not downloaded" would be a lie.
    private var isExternal: Bool {
        engine.cacheDir == nil && engine.managedBy != "apple"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            // Center alignment for the whole row: every card presents the
            // same anatomy — icon, text block, one action slot — with the
            // action vertically centered regardless of text height. (The
            // active checkmark used to float at the top corner while other
            // cards' buttons sat centered.)
            HStack(alignment: .center, spacing: Theme.Spacing.m) {
                SectionIcon(
                    symbol: iconName,
                    tint: engine.active ? Theme.Brand.accent : .secondary,
                    diameter: 34,
                    fontSize: 15
                )

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: Theme.Spacing.xs + 2) {
                        Text(engine.name)
                            .font(Theme.Typography.bodyEmphasized)
                        StatusPill(text: pillText, tone: pillTone)
                    }
                    Text(engine.description)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if !isDownloading && !detailLine.isEmpty {
                        Text(detailLine)
                            .font(Theme.Typography.monoSmall)
                            .foregroundStyle(.tertiary)
                            .padding(.top, 1)
                    }
                }

                Spacer(minLength: Theme.Spacing.s)

                actionButtons
            }
            .padding(Theme.Spacing.m)

            if let download, isDownloading || download.phase == "error" {
                DownloadProgressBar(progress: download)
                    .padding(.horizontal, Theme.Spacing.m)
                    .padding(.bottom, Theme.Spacing.m)
                    .padding(.top, -Theme.Spacing.xs)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                .fill(engine.active ? Theme.Brand.accent.opacity(0.07) : Theme.Surface.card)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                .strokeBorder(
                    engine.active ? Theme.Brand.accent.opacity(0.40) : Theme.Surface.stroke,
                    lineWidth: 1
                )
        )
    }

    private var iconName: String {
        switch engine.id {
        case "parakeet_v3": return "waveform.badge.mic"
        case "qwen3_asr":   return "sparkle"
        case "apple_speech": return "apple.logo"
        case "whisperkit":  return "server.rack"
        default:            return "cpu"
        }
    }

    private var pillText: String {
        if let d = download, d.phase == "error" { return "Failed" }
        if let d = download, d.phase == "warming" { return "Loading" }
        // A quick switch between already-downloaded engines briefly passes
        // through "preparing" with nothing to download — that's a load, not
        // a download.
        if let d = download, d.phase == "preparing", engine.downloaded { return "Loading" }
        if isSwitching { return "Switching" }
        if isDownloading { return "Downloading" }
        if engine.active { return "In use" }
        if engine.available == false { return "Unavailable" }
        if isExternal { return "External models" }
        if engine.downloaded { return "Downloaded" }
        if engine.managedBy == "apple" { return "Available" }
        if engine.downloadStatus == "partial" { return "Partial" }
        return "Not downloaded"
    }

    private var pillTone: Theme.Tone {
        if let d = download, d.phase == "error" { return .danger }
        if isSwitching || isDownloading { return .info }
        if engine.active { return (engine.downloaded || isExternal) ? .success : .warning }
        if engine.available == false { return .warning }
        if engine.downloaded { return .info }
        if engine.downloadStatus == "partial" { return .warning }
        return .neutral
    }

    private var detailLine: String {
        if engine.managedBy == "apple" {
            var parts = [engine.message ?? "Managed by macOS"]
            if let locale = engine.locale, !locale.isEmpty { parts.append(locale) }
            return parts.joined(separator: " · ")
        }
        if isExternal {
            return "Models managed by whisperkit-cli"
        }
        var parts: [String] = []
        if engine.downloaded, let mb = engine.sizeMb, mb > 0 {
            parts.append(formatSize(mb: mb))
        } else if engine.downloadStatus == "partial" {
            if let mb = engine.sizeMb, mb > 0 {
                parts.append("\(formatSize(mb: mb)) partial")
            } else {
                parts.append("partial download")
            }
        } else if !engine.downloaded {
            parts.append(engine.active ? "cache missing" : "not downloaded")
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
    private var actionButtons: some View {
        // Download progress outranks the switching spinner: once bytes are
        // moving the user needs the Cancel button, not "Switching…".
        if isDownloading {
            downloadButtons
        } else if isSwitching {
            HStack(spacing: Theme.Spacing.xs + 2) {
                ProgressView()
                    .controlSize(.small)
                Text("Switching…")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
        } else if engine.active {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(Theme.Brand.accent)
                .symbolRenderingMode(.hierarchical)
                .help("This engine is currently loaded.")
                .accessibilityLabel("Active engine")
        } else if let d = download, d.phase == "error" {
            Button("Retry") {
                switchTo(engine.id)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .disabled(othersBusy)
        } else if engine.downloaded {
            HStack(spacing: Theme.Spacing.xs) {
                Button("Use") { switchTo(engine.id) }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(othersBusy)
                if engine.removable != false {
                    Button(role: .destructive) {
                        onRequestRemove(engine)
                    } label: {
                        Image(systemName: "trash")
                    }
                    .buttonStyle(.borderless)
                    .disabled(othersBusy)
                    .help(engine.managedBy == "apple" ? "Release this app's Apple language reservation." : "Remove this engine's weights from disk.")
                }
            }
        } else if engine.managedBy == "apple" {
            // One rule across every card: the primary switch action is always
            // the prominent button, whatever its label.
            Button(engine.available == false ? "Unavailable" : "Download & use") { switchTo(engine.id) }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(engine.available == false || othersBusy)
                .help(engine.message ?? "macOS downloads and manages the selected language model.")
        } else if engine.cacheDir != nil {
            Button(engine.downloadStatus == "partial" ? "Resume download" : "Download & use") { switchTo(engine.id) }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(othersBusy)
                .help("Switches to this engine and downloads the model.")
        } else {
            // WhisperKit: lives outside the HF cache; no progress bar available.
            Button("Use") { switchTo(engine.id) }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(othersBusy)
                .help("WhisperKit stores its own models. Install whisperkit-cli via Homebrew first.")
        }
    }

    @ViewBuilder
    private var downloadButtons: some View {
        if canCancelDownload {
            Button("Cancel") {
                appState.ipcClient?.sendAction("cancel_download", id: engine.id)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Cancel this model download and keep the current engine.")
        } else {
            Label("Loading", systemImage: "hourglass")
                .labelStyle(.iconOnly)
                .foregroundStyle(.secondary)
                .help("Model weights are loading into memory.")
        }
    }

    private func switchTo(_ id: String) {
        onSwitch(id)
    }
}
