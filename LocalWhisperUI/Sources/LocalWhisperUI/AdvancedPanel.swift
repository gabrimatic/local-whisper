import SwiftUI
import AppKit

// MARK: - Advanced panel (status + permissions + storage + diagnostics)

struct AdvancedPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        PanelScaffold(
            title: "Advanced",
            subtitle: "Service status, permissions, storage, and diagnostics."
        ) {
            statusCard
            permissionsCard
            storageCard
            lifecycleCard
            diagnosticsCard
        }
    }

    // MARK: - Live status

    private var statusCard: some View {
        SettingsCard(
            icon: "antenna.radiowaves.left.and.right",
            title: "Live status",
            description: "What the running service is doing right now."
        ) {
            SettingRow(title: "Service") {
                HStack(spacing: Theme.Spacing.s) {
                    StatusPill(text: appState.connectionState.label, tone: appState.connectionState.tone)
                    Button("Restart") {
                        appState.ipcClient?.sendAction("restart")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(appState.connectionState != .connected)
                    .help("Relaunch the background recording / transcription service. Reloads models cleanly.")
                }
            }
            SettingRow(title: "Engine") {
                Text(engineDisplay)
                    .font(Theme.Typography.body)
                    .foregroundStyle(.secondary)
            }
            SettingRow(title: "Grammar") {
                Text(backendDisplay)
                    .font(Theme.Typography.body)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var engineDisplay: String {
        if let active = appState.engines.first(where: { $0.active }) {
            return active.name
        }
        switch appState.config.transcription.engine {
        case "parakeet_v3": return "Parakeet-TDT v3"
        case "qwen3_asr":   return "Qwen3-ASR"
        case "apple_speech": return "Apple SpeechTranscriber"
        case "whisperkit":  return "WhisperKit"
        default:            return appState.config.transcription.engine
        }
    }

    private var backendDisplay: String {
        guard appState.config.grammar.enabled else { return "Disabled" }
        switch appState.config.grammar.backend {
        case "apple_intelligence": return "Apple Intelligence"
        case "ollama":             return "Ollama"
        case "lm_studio":          return "LM Studio"
        default:                   return appState.config.grammar.backend
        }
    }

    // MARK: - Permissions

    private var permissionsCard: some View {
        SettingsCard(
            icon: "lock.shield",
            title: "Permissions",
            description: "Ask macOS for the access needed by global dictation."
        ) {
            WideRow {
                HStack(spacing: Theme.Spacing.s) {
                    Button {
                        appState.ipcClient?.sendAction("request_microphone_permission")
                    } label: {
                        Label("Request microphone", systemImage: "mic.fill")
                    }
                    Button {
                        appState.ipcClient?.sendAction("request_accessibility_permission")
                    } label: {
                        Label("Request accessibility", systemImage: "keyboard.fill")
                    }
                }

                InlineNotice(
                    kind: .info,
                    text: "Use these when macOS did not show the prompt during setup. If access was denied before, the matching System Settings page opens."
                )
            }
        }
    }

    // MARK: - Storage

    private var storageCard: some View {
        SettingsCard(
            icon: "internaldrive",
            title: "Storage",
            description: "Where Local Whisper writes audio backups, transcripts, and config."
        ) {
            SettingRow(
                title: "Backup directory",
                subtitle: "Transcription history and audio recordings live here. Restart required after changing."
            ) {
                DeferredTextField(label: "~/.whisper", initialValue: appState.config.backup.directory) { v in
                    let trimmed = v.trimmingCharacters(in: .whitespaces)
                    // An empty directory would send history to the service's
                    // working directory — refuse rather than persist garbage.
                    guard !trimmed.isEmpty else { return }
                    appState.config.backup.directory = trimmed
                    appState.ipcClient?.sendConfigUpdate(section: "backup", key: "directory", value: trimmed)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 260)
            }

            WideRow {
                HStack(spacing: Theme.Spacing.s) {
                    Button {
                        NSWorkspace.shared.open(URL(fileURLWithPath: AppDirectories.backupRoot(appState.config)))
                    } label: {
                        Label("Open backup folder", systemImage: "folder")
                    }
                    Button {
                        NSWorkspace.shared.selectFile(AppDirectories.config, inFileViewerRootedAtPath: "")
                    } label: {
                        Label("Reveal config.toml", systemImage: "doc.text.magnifyingglass")
                    }
                }
            }
        }
    }

    // MARK: - Lifecycle

    private var lifecycleCard: some View {
        SettingsCard(
            icon: "memorychip",
            title: "Model lifecycle",
            description: "Balance memory pressure against first-word latency."
        ) {
            SettingRow(
                title: "Unload models after idle",
                subtitle: "Lower values free memory sooner; higher values make the next dictation start faster. 0 keeps models loaded."
            ) {
                StepperRowControl(
                    value: appState.config.service.idleUnloadMinutes,
                    range: 0...240,
                    step: 5,
                    display: idleUnloadLabel,
                    displayWidth: 60
                ) { value in
                    appState.config.service.idleUnloadMinutes = value
                    appState.ipcClient?.sendConfigUpdate(section: "service", key: "idle_unload_minutes", value: value)
                }
            }
        }
    }

    private var idleUnloadLabel: String {
        let minutes = appState.config.service.idleUnloadMinutes
        return minutes == 0 ? "Never" : "\(minutes)m"
    }

    // MARK: - Diagnostics

    private var diagnosticsCard: some View {
        SettingsCard(
            icon: "stethoscope",
            title: "Diagnostics",
            description: "Inspect the running service and its environment."
        ) {
            WideRow {
                HStack(spacing: Theme.Spacing.s) {
                    Button {
                        let path = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/service.log")
                        NSWorkspace.shared.open(URL(fileURLWithPath: path))
                    } label: {
                        Label("Open service log", systemImage: "doc.plaintext")
                    }
                    Button {
                        runWhInTerminal("doctor")
                    } label: {
                        Label("Run wh doctor", systemImage: "stethoscope")
                    }
                }

                InlineNotice(
                    kind: .info,
                    text: "If something feels off, the doctor command checks dependencies, models, permissions, and the service. To update Local Whisper, run `wh update` in Terminal."
                )
            }
        }
    }

    private func runWhInTerminal(_ command: String) {
        let script = """
        tell application "Terminal"
            activate
            do script "wh \(command)"
        end tell
        """
        if let appleScript = NSAppleScript(source: script) {
            var error: NSDictionary?
            appleScript.executeAndReturnError(&error)
        }
    }
}
