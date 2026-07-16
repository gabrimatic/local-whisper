import SwiftUI
import AppKit

// MARK: - Menu bar panel
//
// A rich window-style panel (menuBarExtraStyle(.window)) instead of a plain
// text menu: live status hero, quick toggles, engine/grammar pickers, recent
// transcriptions with inline copy, and a footer with the app-level actions.

struct MenuBarPanel: View {
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var panelWindow: NSWindow?
    @State private var copiedEntryID: String?
    @State private var startingService = false

    private static let panelWidth: CGFloat = 336
    private static let recentCount = 5

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.top, Theme.Spacing.m + 2)
                .padding(.bottom, Theme.Spacing.m)

            StatusHero(startingService: $startingService, onStartService: startService)
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.bottom, Theme.Spacing.m)

            quickToggles
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.bottom, Theme.Spacing.m)

            pickers
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.bottom, Theme.Spacing.s)

            PanelDivider()

            recentSection
                .padding(.vertical, Theme.Spacing.s)

            PanelDivider()

            footer
                .padding(.horizontal, Theme.Spacing.m)
                .padding(.vertical, Theme.Spacing.s + 2)
        }
        .frame(width: Self.panelWidth)
        .background(
            WindowAccessor { window in
                if panelWindow !== window { panelWindow = window }
            }
        )
        .onExitCommand { closePanel() }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: Theme.Spacing.s + 1) {
            ZStack {
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(Theme.Brand.accent.opacity(0.14))
                Image(systemName: "waveform")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.Brand.accent)
            }
            .frame(width: 26, height: 26)
            .accessibilityHidden(true)

            Text("Local Whisper")
                .font(.system(size: 13.5, weight: .semibold, design: .rounded))

            Spacer(minLength: 0)

            StatusPill(text: connectionPillText, tone: connectionPillTone)
        }
    }

    private var connectionPillText: String {
        switch appState.connectionState {
        case .connected:    return phasePillText
        case .connecting:   return "Connecting"
        case .disconnected: return "Offline"
        }
    }

    private var phasePillText: String {
        switch appState.phase {
        case .idle:       return "Ready"
        case .recording:  return "Recording"
        case .processing: return "Working"
        case .done:       return "Done"
        case .error:      return "Error"
        case .speaking:   return "Speaking"
        }
    }

    private var connectionPillTone: Theme.Tone {
        switch appState.connectionState {
        case .connecting:   return .neutral
        case .disconnected: return .warning
        case .connected:
            switch appState.phase {
            case .idle:       return .success
            case .recording:  return .danger
            case .processing: return .info
            case .done:       return .success
            case .error:      return .warning
            case .speaking:   return .accent
            }
        }
    }

    // MARK: - Quick toggles

    private var quickToggles: some View {
        Grid(horizontalSpacing: Theme.Spacing.s, verticalSpacing: Theme.Spacing.s) {
            GridRow {
                QuickToggleChip(
                    icon: "doc.on.clipboard",
                    title: "Paste at cursor",
                    isOn: appState.config.ui.autoPaste
                ) {
                    let newValue = !appState.config.ui.autoPaste
                    appState.config.ui.autoPaste = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "ui", key: "auto_paste", value: newValue)
                }
                QuickToggleChip(
                    icon: "character.book.closed.fill",
                    title: "Replacements",
                    isOn: appState.config.replacements.enabled
                ) {
                    let newValue = !appState.config.replacements.enabled
                    appState.config.replacements.enabled = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "replacements", key: "enabled", value: newValue)
                }
                .help(replacementsHelp)
            }
            GridRow {
                QuickToggleChip(
                    icon: "speaker.wave.2.fill",
                    title: "Read aloud",
                    isOn: appState.config.tts.enabled
                ) {
                    let newValue = !appState.config.tts.enabled
                    appState.config.tts.enabled = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "tts", key: "enabled", value: newValue)
                }
                .help(readAloudHelp)
                QuickToggleChip(
                    icon: "bell.badge.fill",
                    title: "Sounds",
                    isOn: appState.config.ui.soundsEnabled
                ) {
                    let newValue = !appState.config.ui.soundsEnabled
                    appState.config.ui.soundsEnabled = newValue
                    appState.ipcClient?.sendConfigUpdate(section: "ui", key: "sounds_enabled", value: newValue)
                }
            }
        }
    }

    // MARK: - Engine / grammar pickers

    private var pickers: some View {
        VStack(spacing: 2) {
            PanelPickerRow(icon: "waveform", title: "Engine") {
                Picker("Engine", selection: engineBinding) {
                    ForEach(engineChoices, id: \.id) { choice in
                        Text(choice.name).tag(choice.id)
                    }
                }
                .pickerStyle(.menu)
                .labelsHidden()
                .controlSize(.small)
                .fixedSize()
                .disabled(appState.connectionState != .connected)
            }
            .help("The model that converts your speech into text.")

            PanelPickerRow(icon: "text.badge.checkmark", title: "Grammar") {
                Picker("Grammar", selection: grammarBinding) {
                    Text("Apple Intelligence").tag("apple_intelligence")
                    Text("Ollama").tag("ollama")
                    Text("LM Studio").tag("lm_studio")
                    Divider()
                    Text("Off").tag("none")
                }
                .pickerStyle(.menu)
                .labelsHidden()
                .controlSize(.small)
                .fixedSize()
                .disabled(appState.connectionState != .connected)
            }
            .help("Cleans up punctuation, capitalization, and obvious mistakes after transcription.")
        }
    }

    private var replacementsHelp: String {
        let count = appState.config.replacements.rules.count
        if count == 0 { return "Rewrites specific words after transcription. No rules yet — add them in Settings → Vocabulary." }
        return "Rewrites specific words after transcription (\(count) rule\(count == 1 ? "" : "s"))."
    }

    private var readAloudHelp: String {
        let combo = appState.config.tts.speakShortcut
        if combo.isEmpty { return "Reads the selected text aloud. Set a shortcut in Settings → Voice." }
        return "Select text in any app and press \(KeyboardGlyph.display(combo)) to hear it spoken."
    }

    private struct EngineChoice {
        let id: String
        let name: String
    }

    private var engineChoices: [EngineChoice] {
        // Live registry from the service when available (includes every
        // installed engine); static fallback otherwise.
        if !appState.engines.isEmpty {
            var choices = appState.engines.map { EngineChoice(id: $0.id, name: $0.name) }
            let current = appState.config.transcription.engine
            if !choices.contains(where: { $0.id == current }) {
                choices.append(EngineChoice(id: current, name: current))
            }
            return choices
        }
        var choices = [
            EngineChoice(id: "parakeet_v3", name: "Parakeet-TDT v3"),
            EngineChoice(id: "qwen3_asr", name: "Qwen3-ASR"),
            EngineChoice(id: "apple_speech", name: "Apple Speech"),
            EngineChoice(id: "whisperkit", name: "WhisperKit"),
        ]
        let current = appState.config.transcription.engine
        if !choices.contains(where: { $0.id == current }) {
            choices.append(EngineChoice(id: current, name: current))
        }
        return choices
    }

    private var engineBinding: Binding<String> {
        Binding(
            get: { appState.config.transcription.engine },
            set: { newValue in
                appState.config.transcription.engine = newValue
                appState.ipcClient?.sendEngineSwitch(newValue)
            }
        )
    }

    private var grammarBinding: Binding<String> {
        Binding(
            get: { appState.config.grammar.enabled ? appState.config.grammar.backend : "none" },
            set: { newValue in
                if newValue == "none" {
                    appState.config.grammar.enabled = false
                } else {
                    appState.config.grammar.backend = newValue
                    appState.config.grammar.enabled = true
                }
                appState.ipcClient?.sendBackendSwitch(newValue)
            }
        )
    }

    // MARK: - Recent transcriptions

    private var recentSection: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text("RECENT")
                    .font(.system(size: 10, weight: .semibold))
                    .kerning(0.8)
                    .foregroundStyle(.tertiary)
                Spacer()
                if !appState.history.isEmpty {
                    Text("\(appState.history.count) saved")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.tertiary)
                        .monospacedDigit()
                }
            }
            .padding(.horizontal, Theme.Spacing.l)
            .padding(.bottom, 2)

            if appState.history.isEmpty {
                HStack(spacing: Theme.Spacing.s) {
                    Image(systemName: "tray")
                        .foregroundStyle(.tertiary)
                    Text("Transcriptions will appear here.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.vertical, Theme.Spacing.s)
            } else {
                ForEach(Array(appState.history.prefix(Self.recentCount))) { entry in
                    RecentRow(
                        entry: entry,
                        copied: copiedEntryID == entry.id,
                        onCopy: { copyEntry(entry) },
                        onReveal: entry.audioPath != nil
                            ? { appState.ipcClient?.sendAction("reveal", id: entry.id) }
                            : nil
                    )
                }
            }
        }
    }

    // MARK: - Footer

    private var footer: some View {
        HStack(spacing: Theme.Spacing.s) {
            Button {
                openSettings()
            } label: {
                Label("Settings…", systemImage: "gearshape.fill")
                    .font(Theme.Typography.bodyEmphasized)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .keyboardShortcut(",", modifiers: .command)

            Spacer(minLength: 0)

            FooterIconButton(icon: "arrow.clockwise", help: "Retry last transcription") {
                appState.ipcClient?.sendAction("retry")
                closePanel()
            }
            .disabled(!appState.hasHistory || appState.connectionState != .connected)
            .keyboardShortcut("r", modifiers: .command)

            Menu {
                Button("Copy last transcription") {
                    appState.ipcClient?.sendAction("copy")
                }
                .disabled(!appState.hasHistory || appState.connectionState != .connected)
                .keyboardShortcut("c", modifiers: [.command, .shift])
                Divider()
                Button("Open transcripts folder") {
                    NSWorkspace.shared.open(URL(fileURLWithPath: AppDirectories.historyDir(appState.config)))
                    closePanel()
                }
                Button("Open audio folder") {
                    NSWorkspace.shared.open(URL(fileURLWithPath: AppDirectories.audioDir(appState.config)))
                    closePanel()
                }
                Button("Open service log") {
                    let path = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/service.log")
                    NSWorkspace.shared.open(URL(fileURLWithPath: path))
                    closePanel()
                }
                Divider()
                Button("Check for updates…") {
                    appState.ipcClient?.sendAction("update")
                }
                .disabled(appState.connectionState != .connected)
                .keyboardShortcut("u", modifiers: [.command, .shift])
                Button("Restart background service") {
                    appState.ipcClient?.sendAction("restart")
                }
                .disabled(appState.connectionState != .connected)
                .keyboardShortcut("r", modifiers: [.command, .shift])
                Button("Replay tutorial") {
                    openWindow(id: AppWindowID.onboarding)
                    closePanel()
                }
            } label: {
                Image(systemName: "ellipsis.circle")
                    .font(.system(size: 13, weight: .medium))
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("More actions")

            FooterIconButton(icon: "power", help: "Quit Local Whisper") {
                appState.ipcClient?.sendAction("quit")
                // Give the async socket write a beat to flush — terminating
                // immediately raced it and could leave the service running
                // headless with no menu bar icon.
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    NSApplication.shared.terminate(nil)
                }
            }
            .keyboardShortcut("q", modifiers: .command)
        }
    }

    // MARK: - Actions

    private func openSettings() {
        openWindow(id: AppWindowID.settings)
        ActivationPolicy.shared.acquire()
        // The settings root view holds its own acquire in onAppear; this one
        // balances out right after, but guarantees the window comes forward
        // even when it was already open behind other apps.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            ActivationPolicy.shared.release()
        }
        closePanel()
    }

    private func copyEntry(_ entry: HistoryEntry) {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(entry.text, forType: .string)
        copiedEntryID = entry.id
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 1_200_000_000)
            if copiedEntryID == entry.id { copiedEntryID = nil }
        }
    }

    private func startService() {
        guard !startingService else { return }
        startingService = true
        // Fire-and-forget through a login shell so Homebrew and venv installs
        // of `wh` both resolve. The IPC client keeps reconnecting; the pill
        // flips to Connected when the service is up.
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-l", "-c", "command wh start >/dev/null 2>&1 &"]
        try? process.run()
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 8_000_000_000)
            startingService = false
        }
    }

    private func closePanel() {
        panelWindow?.close()
    }
}

// MARK: - Status hero

private struct StatusHero: View {
    @Environment(AppState.self) private var appState
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Binding var startingService: Bool
    let onStartService: () -> Void

    @State private var rmsHistory: [Double] = Array(repeating: 0, count: 36)

    var body: some View {
        content
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(Theme.Spacing.m)
            .frame(minHeight: 58)
            .background(Theme.Surface.well, in: RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                    .strokeBorder(Theme.Surface.stroke, lineWidth: 1)
            )
            .animation(reduceMotion ? nil : Theme.Motion.state, value: appState.phase)
            .onChange(of: appState.rmsLevel) { _, newValue in
                recordRMS(newValue)
            }
            .onChange(of: appState.phase) { _, newPhase in
                if newPhase == .recording { rmsHistory = Array(repeating: 0, count: 36) }
            }
            .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var content: some View {
        if appState.connectionState != .connected {
            disconnectedContent
        } else {
            switch appState.phase {
            case .idle:       idleContent
            case .recording:  recordingContent
            case .processing: workingContent(icon: nil, label: appState.statusText.isEmpty ? "Transcribing…" : appState.statusText)
            case .speaking:   workingContent(icon: "speaker.wave.2.fill", label: appState.statusText.isEmpty ? "Speaking…" : appState.statusText)
            case .done:       doneContent
            case .error:      errorContent
            }
        }
    }

    private var disconnectedContent: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: "bolt.slash.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.Tone.warning.color)
                .symbolRenderingMode(.hierarchical)
            VStack(alignment: .leading, spacing: 1) {
                Text(appState.connectionState == .connecting ? "Connecting to service…" : "Service not running")
                    .font(Theme.Typography.bodyEmphasized)
                Text("Dictation is unavailable until the background service is up.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
            if appState.connectionState == .disconnected {
                Button(startingService ? "Starting…" : "Start") {
                    onStartService()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(startingService)
            }
        }
    }

    private var idleContent: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: "mic.fill")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.Brand.accent)
                .symbolRenderingMode(.hierarchical)
            VStack(alignment: .leading, spacing: 3) {
                Text(idleTitle)
                    .font(Theme.Typography.bodyEmphasized)
                    .lineLimit(2)
                HStack(spacing: 4) {
                    Text("Double-tap")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                    ForEach(Array(KeyboardGlyph.triggerTokens(for: appState.config.hotkey.key).enumerated()), id: \.offset) { _, token in
                        KeyCap(label: token)
                    }
                    Text("to dictate")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 0)
        }
    }

    private var idleTitle: String {
        if !appState.latchedErrorText.isEmpty { return appState.latchedErrorText }
        return "Ready"
    }

    private var recordingContent: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: "record.circle.fill")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.Tone.danger.color)
                .symbolRenderingMode(.hierarchical)
            Text(formattedDuration)
                .font(Theme.Typography.monoLarge)
                .monospacedDigit()
                .contentTransition(.numericText())
            WaveformBars(samples: rmsHistory)
                .frame(maxWidth: .infinity)
                .frame(height: 24)
        }
    }

    private func workingContent(icon: String?, label: String) -> some View {
        HStack(spacing: Theme.Spacing.m) {
            if let icon {
                Image(systemName: icon)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.Brand.accent)
                    .symbolRenderingMode(.hierarchical)
            } else {
                ProgressView()
                    .controlSize(.small)
            }
            Text(label)
                .font(Theme.Typography.bodyEmphasized)
                .lineLimit(2)
            Spacer(minLength: 0)
        }
    }

    private var doneContent: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.Tone.success.color)
                .symbolRenderingMode(.hierarchical)
            Text(appState.doneStatusText.isEmpty ? "Copied!" : appState.doneStatusText)
                .font(Theme.Typography.bodyEmphasized)
                .lineLimit(2)
            Spacer(minLength: 0)
        }
    }

    private var errorContent: some View {
        HStack(alignment: .top, spacing: Theme.Spacing.m) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.Tone.warning.color)
                .symbolRenderingMode(.hierarchical)
            Text(errorLabel)
                .font(Theme.Typography.bodyEmphasized)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
    }

    private var errorLabel: String {
        let latched = appState.latchedErrorText
        if !latched.isEmpty { return latched }
        let status = appState.statusText
        return status.isEmpty ? "Something went wrong." : status
    }

    private var formattedDuration: String {
        let total = Int(appState.durationSeconds)
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        if h > 0 { return String(format: "%d:%02d:%02d", h, m, s) }
        return String(format: "%d:%02d", m, s)
    }

    private func recordRMS(_ rms: Double) {
        guard appState.phase == .recording else { return }
        let normalized: Double
        if rms <= 0.001 {
            normalized = 0
        } else {
            normalized = max(0, min(1, log10(rms / 0.001) / 2.5))
        }
        var next = rmsHistory
        next.append(normalized)
        if next.count > 36 { next.removeFirst(next.count - 36) }
        if reduceMotion {
            rmsHistory = next
        } else {
            withAnimation(.smooth(duration: 0.15)) { rmsHistory = next }
        }
    }
}

// MARK: - Waveform bars (menu panel hero)

private struct WaveformBars: View {
    let samples: [Double]

    var body: some View {
        GeometryReader { geo in
            HStack(alignment: .center, spacing: 2) {
                ForEach(Array(samples.enumerated()), id: \.offset) { index, value in
                    Capsule()
                        .fill(Theme.Brand.accent.opacity(0.35 + 0.65 * Double(index) / Double(max(1, samples.count - 1))))
                        .frame(width: 2.5, height: max(2, geo.size.height * CGFloat(value)))
                }
            }
            .frame(width: geo.size.width, height: geo.size.height, alignment: .trailing)
        }
        .accessibilityHidden(true)
    }
}

// MARK: - Picker row

private struct PanelPickerRow<Control: View>: View {
    let icon: String
    let title: String
    @ViewBuilder var control: () -> Control

    var body: some View {
        HStack(spacing: Theme.Spacing.s) {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
                .frame(width: 16)
            Text(title)
                .font(Theme.Typography.body)
            Spacer(minLength: Theme.Spacing.s)
            control()
        }
        .padding(.vertical, 3)
    }
}

// MARK: - Recent transcription row

private struct RecentRow: View {
    let entry: HistoryEntry
    let copied: Bool
    let onCopy: () -> Void
    var onReveal: (() -> Void)?

    @State private var hovering = false

    var body: some View {
        Button(action: onCopy) {
            HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
                Text(timeAgo(entry.timestamp))
                    .font(Theme.Typography.monoSmall)
                    .foregroundStyle(.tertiary)
                    .frame(width: 52, alignment: .leading)
                Text(truncated(entry.text, limit: 64))
                    .font(Theme.Typography.body)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 0)
                if copied {
                    Label("Copied", systemImage: "checkmark")
                        .font(Theme.Typography.captionEmphasized)
                        .foregroundStyle(Theme.Brand.accent)
                        .labelStyle(.titleAndIcon)
                        .transition(.opacity)
                } else if hovering {
                    HStack(spacing: 6) {
                        if let onReveal {
                            Image(systemName: "waveform.circle")
                                .foregroundStyle(.secondary)
                                .onTapGesture(perform: onReveal)
                                .help("Reveal the audio recording in Finder.")
                        }
                        Image(systemName: "doc.on.doc")
                            .foregroundStyle(.secondary)
                    }
                    .font(.system(size: 11, weight: .medium))
                }
            }
            .padding(.horizontal, Theme.Spacing.s + 2)
            .padding(.vertical, 5)
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.small))
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                    .fill(hovering ? Theme.Surface.hover : Color.clear)
            )
        }
        .buttonStyle(.plain)
        .padding(.horizontal, Theme.Spacing.s)
        .onHover { hovering = $0 }
        .animation(Theme.Motion.hover, value: hovering)
        .animation(Theme.Motion.hover, value: copied)
        .help("Click to copy this transcription.")
        .accessibilityLabel("Copy transcription from \(timeAgo(entry.timestamp)): \(truncated(entry.text, limit: 64))")
    }

    private static let dateFormatter: DateFormatter = {
        let fmt = DateFormatter()
        fmt.dateFormat = "MMM d"
        return fmt
    }()

    private func timeAgo(_ timestamp: Double) -> String {
        let elapsed = Date().timeIntervalSince1970 - timestamp
        if elapsed < 60 { return "\(max(0, Int(elapsed)))s ago" }
        if elapsed < 3600 { return "\(Int(elapsed / 60))m ago" }
        if elapsed < 86400 { return "\(Int(elapsed / 3600))h ago" }
        if elapsed < 172800 { return "Yesterday" }
        if elapsed < 2592000 { return "\(Int(elapsed / 86400))d ago" }
        return Self.dateFormatter.string(from: Date(timeIntervalSince1970: timestamp))
    }

    private func truncated(_ s: String, limit: Int) -> String {
        let collapsed = s.replacingOccurrences(of: "\n", with: " ")
        if collapsed.count <= limit { return collapsed }
        return collapsed.prefix(limit).trimmingCharacters(in: .whitespaces) + "…"
    }
}

// MARK: - Footer icon button

private struct FooterIconButton: View {
    let icon: String
    let help: String
    let action: () -> Void

    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(.secondary)
                .frame(width: 26, height: 24)
                .background(
                    RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                        .fill(hovering ? Theme.Surface.hover : Color.clear)
                )
                .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.small))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .animation(Theme.Motion.hover, value: hovering)
        .help(help)
        .accessibilityLabel(help)
    }
}

// MARK: - Full-width hairline divider

private struct PanelDivider: View {
    var body: some View {
        Rectangle()
            .fill(Theme.Surface.divider)
            .frame(height: 1)
    }
}
