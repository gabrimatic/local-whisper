import SwiftUI

// MARK: - Grammar panel

struct GrammarPanel: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            Form {
                routerSection
                if appState.config.grammar.enabled {
                    backendDetailSection
                }
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Router

    private var routerSection: some View {
        Section {
            Toggle("Enable grammar correction", isOn: Binding(
                get: { appState.config.grammar.enabled },
                set: { newValue in
                    appState.config.grammar.enabled = newValue
                    if newValue {
                        appState.ipcClient?.sendBackendSwitch(appState.config.grammar.backend)
                    } else {
                        appState.ipcClient?.sendBackendSwitch("none")
                    }
                }
            ))
            .help("When enabled, transcribed text is cleaned up before being copied. Disabled means raw transcription.")

            if appState.config.grammar.enabled {
                Picker("Backend", selection: Binding(
                    get: { appState.config.grammar.backend },
                    set: { v in
                        appState.config.grammar.backend = v
                        appState.ipcClient?.sendBackendSwitch(v)
                    }
                )) {
                    Section("On-device") {
                        Text("Apple Intelligence").tag("apple_intelligence")
                    }
                    Section("Local servers") {
                        Text("Ollama").tag("ollama")
                        Text("LM Studio").tag("lm_studio")
                    }
                }
                .pickerStyle(.inline)
            }
        } header: {
            SettingsSectionHeader(
                symbol: "text.badge.checkmark",
                title: "Grammar pass",
                description: "Optional second pass that fixes punctuation, capitalisation, and obvious slips."
            )
        }
    }

    // MARK: - Active backend detail

    @ViewBuilder
    private var backendDetailSection: some View {
        switch appState.config.grammar.backend {
        case "apple_intelligence":
            AppleIntelligenceSection()
        case "ollama":
            OllamaSection()
        case "lm_studio":
            LMStudioSection()
        default:
            EmptyView()
        }
    }
}

// MARK: - Apple Intelligence

struct AppleIntelligenceSection: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Section {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.seal.fill").foregroundStyle(.green)
                Text("Foundation Models run entirely on-device. Requires macOS 15+ with Apple Intelligence enabled.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            LabeledContent("Max characters") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.appleIntelligence.maxChars },
                        set: { v in
                            appState.config.appleIntelligence.maxChars = v
                            appState.ipcClient?.sendConfigUpdate(section: "apple_intelligence", key: "max_chars", value: v)
                        }
                    ), in: 0...50000, step: 500)
                    .labelsHidden()
                    Text(appState.config.appleIntelligence.maxChars == 0 ? "Unlimited" : "\(appState.config.appleIntelligence.maxChars)")
                        .monoStat(width: 80)
                }
            }
            .help("Skip grammar correction on transcripts longer than this. 0 = no limit.")

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.appleIntelligence.timeout },
                        set: { v in
                            appState.config.appleIntelligence.timeout = v
                            appState.ipcClient?.sendConfigUpdate(section: "apple_intelligence", key: "timeout", value: v)
                        }
                    ), in: 0...300, step: 5)
                    .labelsHidden()
                    Text(appState.config.appleIntelligence.timeout == 0 ? "Unlimited" : "\(Int(appState.config.appleIntelligence.timeout))s")
                        .monoStat(width: 80)
                }
            }
        } header: {
            SettingsSectionHeader(symbol: "sparkles", title: "Apple Intelligence")
        }
    }
}

// MARK: - Ollama

struct OllamaSection: View {
    @Environment(AppState.self) private var appState
    @State private var models: [String] = []
    @State private var fetchError: String? = nil
    @State private var fetching = false
    @State private var lastAutoFetched: String = ""

    var body: some View {
        Section {
            connectionRow

            LabeledContent("URL") {
                DeferredTextField(label: "URL", initialValue: appState.config.ollama.url) { value in
                    appState.config.ollama.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }

            LabeledContent("Check URL") {
                DeferredTextField(label: "http://localhost:11434/", initialValue: appState.config.ollama.checkUrl) { value in
                    appState.config.ollama.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "check_url", value: value)
                    lastAutoFetched = ""
                    Task { await autoFetchIfNeeded() }
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }

            LabeledContent("Model") {
                HStack(spacing: 6) {
                    if !models.isEmpty {
                        Picker("", selection: Binding(
                            get: { appState.config.ollama.model },
                            set: { v in
                                appState.config.ollama.model = v
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: v)
                            }
                        )) {
                            ForEach(models, id: \.self) { Text($0).tag($0) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 240)
                    } else {
                        DeferredTextField(label: "Model", initialValue: appState.config.ollama.model) { value in
                            appState.config.ollama.model = value
                            appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: value)
                        }
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 240)
                    }
                    Button(fetching ? "Fetching…" : "Refresh") {
                        lastAutoFetched = ""
                        Task { await fetchModels() }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(fetching)
                }
            }

            if let err = fetchError {
                inlineWarning(err)
            }

            DisclosureGroup("Performance") {
                LabeledContent("Context window") {
                    DeferredIntTextField(label: "0 = default", initialValue: appState.config.ollama.numCtx) { v in
                        appState.config.ollama.numCtx = v
                        appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "num_ctx", value: v)
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 110)
                }
                .help("Tokens the model can hold at once. 0 uses model default. Larger uses more RAM.")

                LabeledContent("Keep alive") {
                    DeferredTextField(label: "60m", initialValue: appState.config.ollama.keepAlive) { v in
                        appState.config.ollama.keepAlive = v
                        appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "keep_alive", value: v)
                    }
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 110)
                }
                .help("How long Ollama keeps the model loaded after the last request. Examples: 30s, 5m, 1h.")

                LabeledContent("Max predict") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.ollama.maxPredict },
                            set: { v in
                                appState.config.ollama.maxPredict = v
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "max_predict", value: v)
                            }
                        ), in: 0...32000, step: 100)
                        .labelsHidden()
                        Text(appState.config.ollama.maxPredict == 0 ? "Default" : "\(appState.config.ollama.maxPredict)")
                            .monoStat(width: 70)
                    }
                }
                .help("Maximum tokens to generate. 0 uses the model default.")

                LabeledContent("Max characters") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.ollama.maxChars },
                            set: { v in
                                appState.config.ollama.maxChars = v
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "max_chars", value: v)
                            }
                        ), in: 0...50000, step: 500)
                        .labelsHidden()
                        Text(appState.config.ollama.maxChars == 0 ? "Unlimited" : "\(appState.config.ollama.maxChars)")
                            .monoStat(width: 80)
                    }
                }
                .help("Skip grammar on transcripts longer than this. 0 = no limit.")

                LabeledContent("Timeout") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.ollama.timeout },
                            set: { v in
                                appState.config.ollama.timeout = v
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "timeout", value: v)
                            }
                        ), in: 0...300, step: 5)
                        .labelsHidden()
                        Text(appState.config.ollama.timeout == 0 ? "Unlimited" : "\(Int(appState.config.ollama.timeout))s")
                            .monoStat(width: 80)
                    }
                }

                Toggle("Unload model on app quit", isOn: Binding(
                    get: { appState.config.ollama.unloadOnExit },
                    set: { v in
                        appState.config.ollama.unloadOnExit = v
                        appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "unload_on_exit", value: v)
                    }
                ))
                .help("Sends keep_alive=0 on quit to free RAM immediately.")
            }
        } header: {
            SettingsSectionHeader(symbol: "shippingbox", title: "Ollama")
        }
        .task { await autoFetchIfNeeded() }
    }

    private var connectionRow: some View {
        HStack(spacing: Theme.Spacing.s) {
            if fetching {
                ProgressView().controlSize(.small)
                Text("Checking server…")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            } else if !models.isEmpty {
                StatusPill(text: "Connected · \(models.count) model\(models.count == 1 ? "" : "s")", tone: .success)
            } else if fetchError != nil {
                StatusPill(text: "Not reachable", tone: .warning)
            } else {
                StatusPill(text: "Idle", tone: .neutral)
            }
            Spacer()
        }
    }

    @MainActor
    private func autoFetchIfNeeded() async {
        let key = appState.config.ollama.checkUrl
        if key.isEmpty { return }
        if key == lastAutoFetched && !models.isEmpty { return }
        lastAutoFetched = key
        await fetchModels()
    }

    @MainActor
    private func fetchModels() async {
        fetching = true
        fetchError = nil
        defer { fetching = false }

        let baseUrl = appState.config.ollama.checkUrl
            .trimmingCharacters(in: .init(charactersIn: "/"))
        guard let url = URL(string: "\(baseUrl)/api/tags") else {
            fetchError = "Invalid check URL: \(baseUrl)/api/tags"
            return
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                fetchError = "Server returned an error. Is Ollama running?"
                return
            }
            struct Resp: Decodable { struct M: Decodable { var name: String }; var models: [M] }
            let names = try JSONDecoder().decode(Resp.self, from: data).models.map(\.name)
            if names.isEmpty {
                fetchError = "No models found. Pull one with: ollama pull <model>"
                models = []
            } else {
                models = names
                if !names.contains(appState.config.ollama.model), let first = names.first {
                    appState.config.ollama.model = first
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: first)
                }
            }
        } catch {
            fetchError = "Could not connect: \(error.localizedDescription)"
        }
    }
}

// MARK: - LM Studio

struct LMStudioSection: View {
    @Environment(AppState.self) private var appState
    @State private var models: [String] = []
    @State private var fetchError: String? = nil
    @State private var fetching = false
    @State private var lastAutoFetched: String = ""

    var body: some View {
        Section {
            connectionRow

            LabeledContent("URL") {
                DeferredTextField(label: "URL", initialValue: appState.config.lmStudio.url) { value in
                    appState.config.lmStudio.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }

            LabeledContent("Check URL") {
                DeferredTextField(label: "http://localhost:1234/", initialValue: appState.config.lmStudio.checkUrl) { value in
                    appState.config.lmStudio.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "check_url", value: value)
                    lastAutoFetched = ""
                    Task { await autoFetchIfNeeded() }
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)
            }

            LabeledContent("Model") {
                HStack(spacing: 6) {
                    if !models.isEmpty {
                        Picker("", selection: Binding(
                            get: { appState.config.lmStudio.model },
                            set: { v in
                                appState.config.lmStudio.model = v
                                appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "model", value: v)
                            }
                        )) {
                            ForEach(models, id: \.self) { Text($0).tag($0) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 240)
                    } else {
                        DeferredTextField(label: "Model", initialValue: appState.config.lmStudio.model) { value in
                            appState.config.lmStudio.model = value
                            appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "model", value: value)
                        }
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 240)
                    }
                    Button(fetching ? "Fetching…" : "Refresh") {
                        lastAutoFetched = ""
                        Task { await fetchModels() }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(fetching)
                }
            }

            if let err = fetchError {
                inlineWarning(err)
            }

            DisclosureGroup("Performance") {
                LabeledContent("Max characters") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.lmStudio.maxChars },
                            set: { v in
                                appState.config.lmStudio.maxChars = v
                                appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "max_chars", value: v)
                            }
                        ), in: 0...50000, step: 500)
                        .labelsHidden()
                        Text(appState.config.lmStudio.maxChars == 0 ? "Unlimited" : "\(appState.config.lmStudio.maxChars)")
                            .monoStat(width: 80)
                    }
                }
                .help("Skip grammar on transcripts longer than this. 0 = no limit.")

                LabeledContent("Max tokens") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.lmStudio.maxTokens },
                            set: { v in
                                appState.config.lmStudio.maxTokens = v
                                appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "max_tokens", value: v)
                            }
                        ), in: 0...32000, step: 100)
                        .labelsHidden()
                        Text(appState.config.lmStudio.maxTokens == 0 ? "Default" : "\(appState.config.lmStudio.maxTokens)")
                            .monoStat(width: 70)
                    }
                }

                LabeledContent("Timeout") {
                    HStack {
                        Stepper("", value: Binding(
                            get: { appState.config.lmStudio.timeout },
                            set: { v in
                                appState.config.lmStudio.timeout = v
                                appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "timeout", value: v)
                            }
                        ), in: 0...300, step: 5)
                        .labelsHidden()
                        Text(appState.config.lmStudio.timeout == 0 ? "Unlimited" : "\(Int(appState.config.lmStudio.timeout))s")
                            .monoStat(width: 80)
                    }
                }
            }
        } header: {
            SettingsSectionHeader(symbol: "server.rack", title: "LM Studio")
        }
        .task { await autoFetchIfNeeded() }
    }

    private var connectionRow: some View {
        HStack(spacing: Theme.Spacing.s) {
            if fetching {
                ProgressView().controlSize(.small)
                Text("Checking server…")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            } else if !models.isEmpty {
                StatusPill(text: "Connected · \(models.count) model\(models.count == 1 ? "" : "s")", tone: .success)
            } else if fetchError != nil {
                StatusPill(text: "Not reachable", tone: .warning)
            } else {
                StatusPill(text: "Idle", tone: .neutral)
            }
            Spacer()
        }
    }

    @MainActor
    private func autoFetchIfNeeded() async {
        let key = appState.config.lmStudio.checkUrl
        if key.isEmpty { return }
        if key == lastAutoFetched && !models.isEmpty { return }
        lastAutoFetched = key
        await fetchModels()
    }

    @MainActor
    private func fetchModels() async {
        fetching = true
        fetchError = nil
        defer { fetching = false }

        let baseUrl = appState.config.lmStudio.checkUrl
            .trimmingCharacters(in: .init(charactersIn: "/"))
        guard let url = URL(string: "\(baseUrl)/v1/models") else {
            fetchError = "Invalid check URL: \(baseUrl)/v1/models"
            return
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                fetchError = "Server returned an error. Is LM Studio's server running?"
                return
            }
            struct Resp: Decodable { struct M: Decodable { var id: String }; var data: [M] }
            let names = try JSONDecoder().decode(Resp.self, from: data).data.map(\.id).sorted()
            if names.isEmpty {
                fetchError = "No models loaded. Load one in LM Studio, then refresh."
                models = []
            } else {
                models = names
                if !names.contains(appState.config.lmStudio.model), let first = names.first {
                    appState.config.lmStudio.model = first
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "model", value: first)
                }
            }
        } catch {
            fetchError = "Could not connect: \(error.localizedDescription)"
        }
    }
}

// MARK: - Inline warning helper (used by Ollama / LM Studio sections)

func inlineWarning(_ text: String) -> some View {
    InlineNotice(kind: .warning, text: text)
}
