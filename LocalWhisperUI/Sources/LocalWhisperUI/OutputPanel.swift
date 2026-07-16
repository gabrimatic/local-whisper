import SwiftUI

// MARK: - Output panel

struct OutputPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        PanelScaffold(
            title: "Output",
            subtitle: "Overlay, sounds, paste behavior, and history."
        ) {
            overlayCard
            deliveryCard
            feedbackCard
            historyCard
        }
    }

    // MARK: - Overlay

    private var overlayCard: some View {
        SettingsCard(
            icon: "rectangle.on.rectangle",
            title: "Live overlay",
            description: "What appears on-screen while recording, transcribing, or speaking."
        ) {
            ToggleRow(
                title: "Show floating overlay",
                subtitle: "A glassy pill near the bottom of the screen with live recording state.",
                isOn: appState.config.ui.showOverlay
            ) { v in
                appState.config.ui.showOverlay = v
                appState.ipcClient?.sendConfigUpdate(section: "ui", key: "show_overlay", value: v)
            }

            if appState.config.ui.showOverlay {
                SettingRow(title: "Opacity") {
                    CommitSlider(
                        value: appState.config.ui.overlayOpacity,
                        in: 0.3...1.0,
                        step: 0.05,
                        onCommit: { v in
                            appState.config.ui.overlayOpacity = v
                            appState.ipcClient?.sendConfigUpdate(section: "ui", key: "overlay_opacity", value: v)
                        }
                    ) { v in
                        Text(String(format: "%.0f%%", v * 100)).monoStat(width: 44)
                    }
                }
            }
        }
    }

    // MARK: - Delivery (paste / clipboard)

    private var deliveryCard: some View {
        SettingsCard(
            icon: "doc.on.clipboard",
            title: "Delivery",
            description: appState.config.ui.autoPaste
                ? "Transcription pastes at the cursor, then your clipboard is restored."
                : "Transcription is copied to the clipboard so you can paste manually."
        ) {
            ToggleRow(
                title: "Paste at cursor",
                subtitle: "Types the transcription right where your cursor is. Your clipboard is preserved either way.",
                isOn: appState.config.ui.autoPaste
            ) { v in
                appState.config.ui.autoPaste = v
                appState.ipcClient?.sendConfigUpdate(section: "ui", key: "auto_paste", value: v)
            }
        }
    }

    // MARK: - Feedback (sounds / notifications)

    private var feedbackCard: some View {
        SettingsCard(
            icon: "bell.badge",
            title: "Feedback",
            description: "Audio cues and macOS notifications."
        ) {
            ToggleRow(
                title: "Play sounds",
                subtitle: "Subtle start/stop chimes and an error blip.",
                isOn: appState.config.ui.soundsEnabled
            ) { v in
                appState.config.ui.soundsEnabled = v
                appState.ipcClient?.sendConfigUpdate(section: "ui", key: "sounds_enabled", value: v)
            }

            ToggleRow(
                title: "Show notifications",
                subtitle: "System notifications for completion and errors.",
                isOn: appState.config.ui.notificationsEnabled
            ) { v in
                appState.config.ui.notificationsEnabled = v
                appState.ipcClient?.sendConfigUpdate(section: "ui", key: "notifications_enabled", value: v)
            }
        }
    }

    // MARK: - History

    private var historyCard: some View {
        SettingsCard(
            icon: "clock.arrow.circlepath",
            title: "History",
            description: "Past transcriptions live at \(historyDirDisplay)."
        ) {
            SettingRow(
                title: "Keep entries",
                subtitle: "How many past transcriptions stay on disk and in the menu (1 to 1,000)."
            ) {
                // Single writer: a text field AND a stepper over one config
                // key fought each other (stale field text overwrote a newer
                // stepper change on blur).
                DeferredIntTextField(
                    label: "100",
                    initialValue: appState.config.backup.historyLimit,
                    clamp: 1...1000
                ) { value in
                    appState.config.backup.historyLimit = value
                    appState.ipcClient?.sendConfigUpdate(section: "backup", key: "history_limit", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 64)
            }
        }
    }

    private var historyDirDisplay: String {
        let path = AppDirectories.historyDir(appState.config)
        return path.replacingOccurrences(of: NSHomeDirectory(), with: "~")
    }
}
