import SwiftUI

// MARK: - Output panel

struct OutputPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            Form {
                overlaySection
                deliverySection
                feedbackSection
                historySection
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Overlay

    private var overlaySection: some View {
        Section {
            Toggle("Show floating overlay", isOn: Binding(
                get: { appState.config.ui.showOverlay },
                set: { v in
                    appState.config.ui.showOverlay = v
                    appState.ipcClient?.sendConfigUpdate(section: "ui", key: "show_overlay", value: v)
                }
            ))
            .help("A glassy pill near the bottom of the screen showing live recording state.")

            if appState.config.ui.showOverlay {
                LabeledContent("Opacity") {
                    HStack {
                        Slider(value: Binding(
                            get: { appState.config.ui.overlayOpacity },
                            set: { v in
                                appState.config.ui.overlayOpacity = v
                                appState.ipcClient?.sendConfigUpdate(section: "ui", key: "overlay_opacity", value: v)
                            }
                        ), in: 0.3...1.0, step: 0.05)
                        Text(String(format: "%.0f%%", appState.config.ui.overlayOpacity * 100))
                            .monoStat(width: 44)
                    }
                }
            }
        } header: {
            SettingsSectionHeader(
                symbol: "rectangle.on.rectangle",
                title: "Live overlay",
                description: "What appears on-screen while recording, transcribing, or speaking."
            )
        }
    }

    // MARK: - Delivery (paste / clipboard)

    private var deliverySection: some View {
        Section {
            Toggle("Paste at cursor", isOn: Binding(
                get: { appState.config.ui.autoPaste },
                set: { v in
                    appState.config.ui.autoPaste = v
                    appState.ipcClient?.sendConfigUpdate(section: "ui", key: "auto_paste", value: v)
                }
            ))
            .help("Pastes the transcription directly where your cursor is. Your clipboard is preserved.")
        } header: {
            SettingsSectionHeader(
                symbol: "doc.on.clipboard",
                title: "Delivery",
                description: appState.config.ui.autoPaste
                    ? "Transcription pastes at the cursor, then your clipboard is restored."
                    : "Transcription is copied to the clipboard so you can paste manually."
            )
        }
    }

    // MARK: - Feedback (sounds / notifications)

    private var feedbackSection: some View {
        Section {
            Toggle("Play sounds", isOn: Binding(
                get: { appState.config.ui.soundsEnabled },
                set: { v in
                    appState.config.ui.soundsEnabled = v
                    appState.ipcClient?.sendConfigUpdate(section: "ui", key: "sounds_enabled", value: v)
                }
            ))
            .help("Subtle start/stop chimes and an error blip.")

            Toggle("Show notifications", isOn: Binding(
                get: { appState.config.ui.notificationsEnabled },
                set: { v in
                    appState.config.ui.notificationsEnabled = v
                    appState.ipcClient?.sendConfigUpdate(section: "ui", key: "notifications_enabled", value: v)
                }
            ))
            .help("System notifications for completion and errors.")
        } header: {
            SettingsSectionHeader(
                symbol: "bell.badge",
                title: "Feedback",
                description: "Audio cues and macOS notifications."
            )
        }
    }

    // MARK: - History

    private var historySection: some View {
        Section {
            LabeledContent("Keep entries") {
                HStack(spacing: Theme.Spacing.xs + 2) {
                    DeferredIntTextField(
                        label: "100",
                        initialValue: appState.config.backup.historyLimit
                    ) { value in
                        let clamped = min(max(value, 1), 1000)
                        appState.config.backup.historyLimit = clamped
                        appState.ipcClient?.sendConfigUpdate(section: "backup", key: "history_limit", value: clamped)
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 70)
                    Stepper("",
                        value: Binding(
                            get: { appState.config.backup.historyLimit },
                            set: { v in
                                appState.config.backup.historyLimit = v
                                appState.ipcClient?.sendConfigUpdate(section: "backup", key: "history_limit", value: v)
                            }
                        ),
                        in: 1...1000
                    )
                    .labelsHidden()
                    Text("of 1,000 max")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .help("Number of past transcriptions to keep on disk and show in the menu (1 to 1,000).")
        } header: {
            SettingsSectionHeader(
                symbol: "clock.arrow.circlepath",
                title: "History",
                description: "Past transcriptions live at ~/.whisper/history."
            )
        }
    }
}
