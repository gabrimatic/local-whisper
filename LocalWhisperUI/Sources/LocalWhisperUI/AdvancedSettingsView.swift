import SwiftUI
import AppKit

// MARK: - Advanced settings tab

struct AdvancedSettingsView: View {
    @Environment(AppState.self) var appState

    @State var ollamaModels: [String] = []
    @State var ollamaFetchError: String? = nil
    @State var ollamaFetching = false

    var body: some View {
        ScrollView {
            Form {
                audioProcessingSection
                whisperKitSection
                qwen3Section
                ollamaSection
                lmStudioSection
                appleIntelligenceSection
                shortcutsSection
                ttsSection
                storageSection
            }
            .formStyle(.grouped)
            .onAppear {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                    NSApp.keyWindow?.makeFirstResponder(nil)
                }
            }
        }
    }
}
