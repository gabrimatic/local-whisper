import SwiftUI
import AppKit

// MARK: - About tab

struct AboutView: View {
    @Environment(AppState.self) private var appState

    private var version: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Hero
                VStack(spacing: 10) {
                    Image(systemName: "waveform.badge.mic")
                        .font(.system(size: 56))
                        .foregroundStyle(.primary)
                        .symbolRenderingMode(.hierarchical)
                        .symbolEffect(.breathe)
                        .padding(.top, 32)

                    Text("Local Whisper")
                        .font(.system(size: 22, weight: .semibold))

                    Text("Version \(version)")
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                        .fixedSize()

                    Text("100% local voice transcription for macOS.\nNo cloud, no tracking, no internet required.")
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(3)
                        .padding(.horizontal, 32)
                        .padding(.top, 4)
                }

                Divider().padding(.vertical, 20)

                // Author + links
                VStack(spacing: 8) {
                    HStack(spacing: 6) {
                        Text("Soroush Yousefpour")
                            .font(.system(size: 13))
                        Button("gabrimatic.info") {
                            NSWorkspace.shared.open(URL(string: "https://gabrimatic.info")!)
                        }
                        .buttonStyle(.link)
                        .font(.system(size: 13))
                    }

                    Button("GitHub") {
                        NSWorkspace.shared.open(URL(string: "https://github.com/gabrimatic/local-whisper")!)
                    }
                    .buttonStyle(.link)
                    .font(.system(size: 13))
                }

                Divider().padding(.vertical, 20)

                // Credits
                VStack(alignment: .leading, spacing: 0) {
                    Text("Credits")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .padding(.bottom, 10)

                    creditRow(category: "Speech", name: "Qwen3-ASR by Alibaba Qwen Team", url: "https://github.com/QwenLM/Qwen3-ASR")
                    creditRow(category: "Speech", name: "WhisperKit by Argmax", url: "https://github.com/argmaxinc/WhisperKit")
                    creditRow(category: "Speech", name: "mlx-audio by Prince Canuma", url: "https://github.com/Blaizzy/mlx-audio")
                    creditRow(category: "Grammar", name: "Apple Foundation Models", url: "https://developer.apple.com/machine-learning/foundation-models/")
                    creditRow(category: "LLM", name: "Ollama", url: "https://ollama.ai")
                    creditRow(category: "LLM", name: "LM Studio", url: "https://lmstudio.ai")
                }
                .frame(maxWidth: 400, alignment: .leading)

                // Quick actions
                Divider().padding(.vertical, 20)

                HStack(spacing: 16) {
                    Button("Open Config File") {
                        NSWorkspace.shared.selectFile(AppDirectories.config, inFileViewerRootedAtPath: "")
                    }
                    .buttonStyle(.link)

                    Button("Open Backup Folder") {
                        NSWorkspace.shared.open(URL(fileURLWithPath: AppDirectories.whisper))
                    }
                    .buttonStyle(.link)
                }
                .padding(.bottom, 32)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private func creditRow(category: String, name: String, url: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(category)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .frame(width: 56, alignment: .leading)
            Button(name) {
                NSWorkspace.shared.open(URL(string: url)!)
            }
            .buttonStyle(.link)
            .font(.system(size: 12))
        }
        .padding(.vertical, 3)
    }
}
