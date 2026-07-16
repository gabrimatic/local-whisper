import SwiftUI

// MARK: - Grammar panel

struct GrammarPanel: View {
    @Environment(AppState.self) private var appState

    static let validBackends: Set<String> = ["apple_intelligence", "ollama", "lm_studio"]

    var body: some View {
        PanelScaffold(
            title: "Grammar",
            subtitle: "An optional cleanup pass that fixes punctuation, capitalisation, and obvious slips."
        ) {
            masterCard
            if appState.config.grammar.enabled {
                backendChooser
                backendDetail
            }
        }
    }

    // MARK: - Master toggle

    private var masterCard: some View {
        SettingsCard(
            icon: "text.badge.checkmark",
            title: "Grammar pass",
            description: "Runs after transcription, before replacements."
        ) {
            ToggleRow(
                title: "Enable grammar correction",
                subtitle: "Transcripts are cleaned up before being copied or pasted. Off means raw transcription.",
                isOn: appState.config.grammar.enabled
            ) { newValue in
                appState.config.grammar.enabled = newValue
                if newValue {
                    // The config can legitimately hold "none" (rollback path
                    // after a failed enable). Sending it back would read as
                    // "disable" and snap the toggle off forever — sanitize.
                    var backend = appState.config.grammar.backend
                    if !GrammarPanel.validBackends.contains(backend) {
                        backend = "apple_intelligence"
                        appState.config.grammar.backend = backend
                    }
                    appState.ipcClient?.sendBackendSwitch(backend)
                } else {
                    appState.ipcClient?.sendBackendSwitch("none")
                }
            }
        }
    }

    // MARK: - Backend chooser

    private var backendChooser: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s + 2) {
            HStack(spacing: Theme.Spacing.s) {
                Image(systemName: "cpu")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.Brand.accent)
                    .frame(width: 16)
                Text("Backend")
                    .font(Theme.Typography.sectionHeader)
            }
            .padding(.leading, 2)

            VStack(spacing: Theme.Spacing.s) {
                ChoiceCard(
                    icon: "sparkles",
                    tint: Theme.Brand.sky,
                    title: "Apple Intelligence",
                    subtitle: "On-device Foundation Models. Requires macOS 26+ with Apple Intelligence enabled.",
                    isSelected: appState.config.grammar.backend == "apple_intelligence",
                    badge: "On-device"
                ) {
                    selectBackend("apple_intelligence")
                }
                ChoiceCard(
                    icon: "shippingbox.fill",
                    tint: Theme.Brand.accent,
                    title: "Ollama",
                    subtitle: "Local LLM served by the Ollama app at localhost.",
                    isSelected: appState.config.grammar.backend == "ollama"
                ) {
                    selectBackend("ollama")
                }
                ChoiceCard(
                    icon: "server.rack",
                    tint: Theme.Brand.accent,
                    title: "LM Studio",
                    subtitle: "OpenAI-compatible local server from LM Studio's Developer tab.",
                    isSelected: appState.config.grammar.backend == "lm_studio"
                ) {
                    selectBackend("lm_studio")
                }
            }
        }
    }

    private func selectBackend(_ id: String) {
        appState.config.grammar.backend = id
        appState.ipcClient?.sendBackendSwitch(id)
    }

    // MARK: - Active backend detail

    @ViewBuilder
    private var backendDetail: some View {
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
        SettingsCard(
            icon: "sparkles",
            title: "Apple Intelligence",
            description: "Foundation Models run entirely on-device."
        ) {
            SettingRow(
                title: "Max characters",
                subtitle: "Skip grammar correction on transcripts longer than this. 0 means no limit."
            ) {
                StepperRowControl(
                    value: appState.config.appleIntelligence.maxChars,
                    range: 0...50000,
                    step: 500,
                    display: appState.config.appleIntelligence.maxChars == 0 ? "Unlimited" : "\(appState.config.appleIntelligence.maxChars)",
                    displayWidth: 80
                ) { v in
                    appState.config.appleIntelligence.maxChars = v
                    appState.ipcClient?.sendConfigUpdate(section: "apple_intelligence", key: "max_chars", value: v)
                }
            }

            SettingRow(
                title: "Timeout",
                subtitle: "Maximum time to wait for the cleanup pass. 0 means no limit."
            ) {
                StepperRowControl(
                    value: Int(appState.config.appleIntelligence.timeout),
                    range: 0...300,
                    step: 5,
                    display: appState.config.appleIntelligence.timeout == 0 ? "Unlimited" : "\(Int(appState.config.appleIntelligence.timeout))s",
                    displayWidth: 80
                ) { v in
                    appState.config.appleIntelligence.timeout = Double(v)
                    appState.ipcClient?.sendConfigUpdate(section: "apple_intelligence", key: "timeout", value: Double(v))
                }
            }
        }
    }
}

// MARK: - Ollama

struct OllamaSection: View {
    @Environment(AppState.self) private var appState
    @State private var models: [String] = []
    @State private var fetchError: String? = nil
    @State private var fetching = false
    @State private var reachable = false
    @State private var lastAutoFetched: String = ""

    var body: some View {
        SettingsCard(
            icon: "shippingbox",
            title: "Ollama",
            description: "Talks to the Ollama server on this Mac."
        ) {
            WideRow {
                connectionRow
            }

            SettingRow(title: "URL", subtitle: "Generate endpoint used for cleanup requests.") {
                DeferredTextField(label: "URL", initialValue: appState.config.ollama.url) { value in
                    appState.config.ollama.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 260)
            }

            SettingRow(title: "Check URL", subtitle: "Root endpoint probed to see whether the server is up.") {
                DeferredTextField(label: "http://localhost:11434/", initialValue: appState.config.ollama.checkUrl) { value in
                    appState.config.ollama.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "check_url", value: value)
                    lastAutoFetched = ""
                    Task { await autoFetchIfNeeded() }
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 260)
            }

            SettingRow(title: "Model") {
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
                        .frame(maxWidth: 210)
                    } else {
                        DeferredTextField(label: "Model", initialValue: appState.config.ollama.model) { value in
                            appState.config.ollama.model = value
                            appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: value)
                        }
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 210)
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
                WideRow {
                    InlineNotice(kind: .warning, text: err)
                }
            }

            WideRow {
                DisclosureGroup("Performance") {
                    VStack(spacing: 0) {
                        SettingRow(
                            title: "Context window",
                            subtitle: "Tokens the model can hold at once. 0 uses the model default; larger uses more RAM."
                        ) {
                            DeferredIntTextField(label: "0 = default", initialValue: appState.config.ollama.numCtx) { v in
                                appState.config.ollama.numCtx = v
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "num_ctx", value: v)
                            }
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 100)
                        }

                        SettingRow(
                            title: "Keep alive",
                            subtitle: "How long Ollama keeps the model loaded after the last request — 30s, 5m, 1h."
                        ) {
                            DeferredTextField(label: "60m", initialValue: appState.config.ollama.keepAlive) { v in
                                appState.config.ollama.keepAlive = v
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "keep_alive", value: v)
                            }
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 100)
                        }

                        SettingRow(
                            title: "Max predict",
                            subtitle: "Maximum tokens to generate. 0 uses the model default."
                        ) {
                            StepperRowControl(
                                value: appState.config.ollama.maxPredict,
                                range: 0...32000,
                                step: 100,
                                display: appState.config.ollama.maxPredict == 0 ? "Default" : "\(appState.config.ollama.maxPredict)"
                            ) { v in
                                appState.config.ollama.maxPredict = v
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "max_predict", value: v)
                            }
                        }

                        SettingRow(
                            title: "Max characters",
                            subtitle: "Skip grammar on transcripts longer than this. 0 means no limit."
                        ) {
                            StepperRowControl(
                                value: appState.config.ollama.maxChars,
                                range: 0...50000,
                                step: 500,
                                display: appState.config.ollama.maxChars == 0 ? "Unlimited" : "\(appState.config.ollama.maxChars)",
                                displayWidth: 80
                            ) { v in
                                appState.config.ollama.maxChars = v
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "max_chars", value: v)
                            }
                        }

                        SettingRow(title: "Timeout", subtitle: "Maximum wait per request. 0 means no limit.") {
                            StepperRowControl(
                                value: Int(appState.config.ollama.timeout),
                                range: 0...300,
                                step: 5,
                                display: appState.config.ollama.timeout == 0 ? "Unlimited" : "\(Int(appState.config.ollama.timeout))s",
                                displayWidth: 80
                            ) { v in
                                appState.config.ollama.timeout = Double(v)
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "timeout", value: Double(v))
                            }
                        }

                        ToggleRow(
                            title: "Unload model on app quit",
                            subtitle: "Sends keep_alive=0 on quit to free RAM immediately.",
                            isOn: appState.config.ollama.unloadOnExit
                        ) { v in
                            appState.config.ollama.unloadOnExit = v
                            appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "unload_on_exit", value: v)
                        }
                    }
                    .padding(.top, Theme.Spacing.xs)
                }
                .font(Theme.Typography.bodyEmphasized)
            }
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
            } else if reachable {
                StatusPill(text: "Connected · no models", tone: .warning)
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
                reachable = false
                fetchError = "Server returned an error. Is Ollama running?"
                return
            }
            reachable = true
            struct Resp: Decodable { struct M: Decodable { var name: String }; var models: [M] }
            let names = try JSONDecoder().decode(Resp.self, from: data).models.map(\.name)
            if names.isEmpty {
                fetchError = "No models found. Pull one with: ollama pull <model>"
                models = []
            } else {
                // Never silently rewrite the user's configured model from a
                // read-only status probe: the configured one may simply not
                // be pulled yet. Surface it and let the user decide.
                let configured = appState.config.ollama.model
                if !configured.isEmpty && !names.contains(configured) {
                    models = [configured] + names
                    fetchError = "Configured model \"\(configured)\" isn't on the server. Pull it with: ollama pull \(configured), or pick another."
                } else {
                    models = names
                }
            }
        } catch {
            reachable = false
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
    @State private var reachable = false
    @State private var lastAutoFetched: String = ""

    var body: some View {
        SettingsCard(
            icon: "server.rack",
            title: "LM Studio",
            description: "Talks to LM Studio's OpenAI-compatible local server."
        ) {
            WideRow {
                connectionRow
            }

            SettingRow(title: "URL", subtitle: "Chat-completions endpoint used for cleanup requests.") {
                DeferredTextField(label: "URL", initialValue: appState.config.lmStudio.url) { value in
                    appState.config.lmStudio.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 260)
            }

            SettingRow(title: "Check URL", subtitle: "Root endpoint probed to see whether the server is up.") {
                DeferredTextField(label: "http://localhost:1234/", initialValue: appState.config.lmStudio.checkUrl) { value in
                    appState.config.lmStudio.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "check_url", value: value)
                    lastAutoFetched = ""
                    Task { await autoFetchIfNeeded() }
                }
                .textFieldStyle(.roundedBorder)
                .frame(width: 260)
            }

            SettingRow(title: "Model") {
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
                        .frame(maxWidth: 210)
                    } else {
                        DeferredTextField(label: "Model", initialValue: appState.config.lmStudio.model) { value in
                            appState.config.lmStudio.model = value
                            appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "model", value: value)
                        }
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 210)
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
                WideRow {
                    InlineNotice(kind: .warning, text: err)
                }
            }

            WideRow {
                DisclosureGroup("Performance") {
                    VStack(spacing: 0) {
                        SettingRow(
                            title: "Max characters",
                            subtitle: "Skip grammar on transcripts longer than this. 0 means no limit."
                        ) {
                            StepperRowControl(
                                value: appState.config.lmStudio.maxChars,
                                range: 0...50000,
                                step: 500,
                                display: appState.config.lmStudio.maxChars == 0 ? "Unlimited" : "\(appState.config.lmStudio.maxChars)",
                                displayWidth: 80
                            ) { v in
                                appState.config.lmStudio.maxChars = v
                                appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "max_chars", value: v)
                            }
                        }

                        SettingRow(
                            title: "Max tokens",
                            subtitle: "Maximum tokens to generate. 0 uses the model default."
                        ) {
                            StepperRowControl(
                                value: appState.config.lmStudio.maxTokens,
                                range: 0...32000,
                                step: 100,
                                display: appState.config.lmStudio.maxTokens == 0 ? "Default" : "\(appState.config.lmStudio.maxTokens)"
                            ) { v in
                                appState.config.lmStudio.maxTokens = v
                                appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "max_tokens", value: v)
                            }
                        }

                        SettingRow(title: "Timeout", subtitle: "Maximum wait per request. 0 means no limit.") {
                            StepperRowControl(
                                value: Int(appState.config.lmStudio.timeout),
                                range: 0...300,
                                step: 5,
                                display: appState.config.lmStudio.timeout == 0 ? "Unlimited" : "\(Int(appState.config.lmStudio.timeout))s",
                                displayWidth: 80
                            ) { v in
                                appState.config.lmStudio.timeout = Double(v)
                                appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "timeout", value: Double(v))
                            }
                        }
                    }
                    .padding(.top, Theme.Spacing.xs)
                }
                .font(Theme.Typography.bodyEmphasized)
            }
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
            } else if reachable {
                StatusPill(text: "Connected · no models", tone: .warning)
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
                reachable = false
                fetchError = "Server returned an error. Is LM Studio's server running?"
                return
            }
            reachable = true
            struct Resp: Decodable { struct M: Decodable { var id: String }; var data: [M] }
            let names = try JSONDecoder().decode(Resp.self, from: data).data.map(\.id).sorted()
            if names.isEmpty {
                fetchError = "No models loaded. Load one in LM Studio, then refresh."
                models = []
            } else {
                // Same rule as Ollama: a status probe must never rewrite the
                // configured model behind the user's back.
                let configured = appState.config.lmStudio.model
                if !configured.isEmpty && !names.contains(configured) {
                    models = [configured] + names
                    fetchError = "Configured model \"\(configured)\" isn't loaded on the server. Load it in LM Studio, or pick another."
                } else {
                    models = names
                }
            }
        } catch {
            reachable = false
            fetchError = "Could not connect: \(error.localizedDescription)"
        }
    }
}
