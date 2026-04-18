import SwiftUI
import AppKit

// MARK: - Advanced settings tab

struct AdvancedSettingsView: View {
    @Environment(AppState.self) var appState

    @State var ollamaModels: [String] = []
    @State var ollamaFetchError: String? = nil
    @State var ollamaFetching = false
    @State var ollamaLastAutoFetched: String = ""

    @State var lmStudioModels: [String] = []
    @State var lmStudioFetchError: String? = nil
    @State var lmStudioFetching = false
    @State var lmStudioLastAutoFetched: String = ""

    @State var appleIntelligenceStatus: AppleIntelligenceProbe = .unknown

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
                Task { await autoFetchAllBackends() }
            }
        }
    }

    @MainActor
    func autoFetchAllBackends() async {
        await autoFetchOllamaIfNeeded()
        await autoFetchLMStudioIfNeeded()
        probeAppleIntelligence()
    }
}

enum AppleIntelligenceProbe: Equatable {
    case unknown
    case supported
    case unsupported(String)
}
