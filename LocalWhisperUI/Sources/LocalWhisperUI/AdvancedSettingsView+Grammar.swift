import SwiftUI

extension AdvancedSettingsView {
    var ollamaSection: some View {
        Section("Ollama") {
            LabeledContent("URL") {
                DeferredTextField(
                    label: "URL",
                    initialValue: appState.config.ollama.url
                ) { value in
                    appState.config.ollama.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Check URL") {
                DeferredTextField(
                    label: "http://localhost:11434/",
                    initialValue: appState.config.ollama.checkUrl
                ) { value in
                    appState.config.ollama.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "check_url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Model") {
                HStack(spacing: 6) {
                    if !ollamaModels.isEmpty {
                        Picker("", selection: Binding(
                            get: { appState.config.ollama.model },
                            set: { newValue in
                                appState.config.ollama.model = newValue
                                appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: newValue)
                            }
                        )) {
                            ForEach(ollamaModels, id: \.self) { model in
                                Text(model).tag(model)
                            }
                        }
                        .frame(maxWidth: 220)
                    } else {
                        DeferredTextField(
                            label: "Model",
                            initialValue: appState.config.ollama.model
                        ) { value in
                            appState.config.ollama.model = value
                            appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: value)
                        }
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 220)
                    }
                    Button(ollamaFetching ? "Fetching…" : "Fetch Models") {
                        Task { await fetchOllamaModels() }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(ollamaFetching)
                }
            }

            if let error = ollamaFetchError {
                HStack {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            LabeledContent("Context window") {
                DeferredIntTextField(
                    label: "0 = default",
                    initialValue: appState.config.ollama.numCtx
                ) { value in
                    appState.config.ollama.numCtx = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "num_ctx", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 100)
            }
            .help("Number of tokens the model can hold in context at once. 0 uses the model default. Larger values use more RAM.")

            LabeledContent("Keep alive") {
                DeferredTextField(
                    label: "e.g. 60m",
                    initialValue: appState.config.ollama.keepAlive
                ) { value in
                    appState.config.ollama.keepAlive = value
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "keep_alive", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 100)
            }
            .help("How long Ollama keeps the model loaded after the last request. Examples: 30s, 5m, 1h")

            LabeledContent("Max predict") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.ollama.maxPredict },
                        set: { v in appState.config.ollama.maxPredict = v; appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "max_predict", value: v) }
                    ), in: 0...32000, step: 100)
                    Text(appState.config.ollama.maxPredict == 0 ? "Default" : "\(appState.config.ollama.maxPredict)")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 60, alignment: .trailing)
                }
            }
            .help("Maximum number of tokens to generate. 0 uses the model default. Limits how long the grammar-corrected output can be.")

            LabeledContent("Max characters") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.ollama.maxChars },
                        set: { v in appState.config.ollama.maxChars = v; appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "max_chars", value: v) }
                    ), in: 0...50000, step: 500)
                    Text(appState.config.ollama.maxChars == 0 ? "Unlimited" : "\(appState.config.ollama.maxChars)")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }
            .help("Transcriptions longer than this are not sent for grammar correction. 0 means no limit.")

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.ollama.timeout },
                        set: { v in appState.config.ollama.timeout = v; appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "timeout", value: v) }
                    ), in: 0...300, step: 5)
                    Text(appState.config.ollama.timeout == 0 ? "Unlimited" : "\(Int(appState.config.ollama.timeout))s")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }

            Toggle("Unload model on quit", isOn: Binding(
                get: { appState.config.ollama.unloadOnExit },
                set: { v in appState.config.ollama.unloadOnExit = v; appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "unload_on_exit", value: v) }
            ))
            .help("Sends a keep_alive=0 request to Ollama when the app quits, freeing RAM immediately")
        }
    }

    var lmStudioSection: some View {
        Section("LM Studio") {
            LabeledContent("URL") {
                DeferredTextField(
                    label: "URL",
                    initialValue: appState.config.lmStudio.url
                ) { value in
                    appState.config.lmStudio.url = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Check URL") {
                DeferredTextField(
                    label: "http://localhost:1234/",
                    initialValue: appState.config.lmStudio.checkUrl
                ) { value in
                    appState.config.lmStudio.checkUrl = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "check_url", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Model") {
                DeferredTextField(
                    label: "Model",
                    initialValue: appState.config.lmStudio.model
                ) { value in
                    appState.config.lmStudio.model = value
                    appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "model", value: value)
                }
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
            }

            LabeledContent("Max characters") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.lmStudio.maxChars },
                        set: { v in appState.config.lmStudio.maxChars = v; appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "max_chars", value: v) }
                    ), in: 0...50000, step: 500)
                    Text(appState.config.lmStudio.maxChars == 0 ? "Unlimited" : "\(appState.config.lmStudio.maxChars)")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }
            .help("Transcriptions longer than this are not sent for grammar correction. 0 means no limit.")

            LabeledContent("Max tokens") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.lmStudio.maxTokens },
                        set: { v in appState.config.lmStudio.maxTokens = v; appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "max_tokens", value: v) }
                    ), in: 0...32000, step: 100)
                    Text(appState.config.lmStudio.maxTokens == 0 ? "Default" : "\(appState.config.lmStudio.maxTokens)")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 60, alignment: .trailing)
                }
            }
            .help("Maximum tokens to generate in the response. 0 uses the model default.")

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.lmStudio.timeout },
                        set: { v in appState.config.lmStudio.timeout = v; appState.ipcClient?.sendConfigUpdate(section: "lm_studio", key: "timeout", value: v) }
                    ), in: 0...300, step: 5)
                    Text(appState.config.lmStudio.timeout == 0 ? "Unlimited" : "\(Int(appState.config.lmStudio.timeout))s")
                        .font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 70, alignment: .trailing)
                }
            }
        }
    }

    var appleIntelligenceSection: some View {
        Section("Apple Intelligence") {
            LabeledContent("Max characters") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.appleIntelligence.maxChars },
                        set: { v in
                            appState.config.appleIntelligence.maxChars = v
                            appState.ipcClient?.sendConfigUpdate(section: "apple_intelligence", key: "max_chars", value: v)
                        }
                    ), in: 0...50000, step: 500)
                    Text(appState.config.appleIntelligence.maxChars == 0 ? "Unlimited" : "\(appState.config.appleIntelligence.maxChars)")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .frame(width: 70, alignment: .trailing)
                }
            }
            .help("Transcriptions longer than this are not sent for grammar correction. 0 means no limit.")

            LabeledContent("Timeout") {
                HStack {
                    Stepper("", value: Binding(
                        get: { appState.config.appleIntelligence.timeout },
                        set: { v in
                            appState.config.appleIntelligence.timeout = v
                            appState.ipcClient?.sendConfigUpdate(section: "apple_intelligence", key: "timeout", value: v)
                        }
                    ), in: 0...300, step: 5)
                    Text(appState.config.appleIntelligence.timeout == 0 ? "Unlimited" : "\(Int(appState.config.appleIntelligence.timeout))s")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .frame(width: 70, alignment: .trailing)
                }
            }
        }
    }

    @MainActor
    func fetchOllamaModels() async {
        ollamaFetching = true
        ollamaFetchError = nil

        let baseUrl = appState.config.ollama.checkUrl
            .trimmingCharacters(in: .init(charactersIn: "/"))
        let urlString = "\(baseUrl)/api/tags"

        guard let url = URL(string: urlString) else {
            ollamaFetchError = "Invalid check URL: \(urlString)"
            ollamaFetching = false
            return
        }

        // Explicit 5s timeout so a stopped Ollama doesn't hang the fetch forever.
        var request = URLRequest(url: url)
        request.timeoutInterval = 5

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                ollamaFetchError = "Server returned an error. Is Ollama running?"
                ollamaFetching = false
                return
            }

            struct OllamaTagsResponse: Decodable {
                struct Model: Decodable { var name: String }
                var models: [Model]
            }

            let decoded = try JSONDecoder().decode(OllamaTagsResponse.self, from: data)
            let names = decoded.models.map(\.name)
            if names.isEmpty {
                ollamaFetchError = "No models found. Pull one with: ollama pull <model>"
            } else {
                ollamaModels = names
                if !names.contains(appState.config.ollama.model), let first = names.first {
                    appState.config.ollama.model = first
                    appState.ipcClient?.sendConfigUpdate(section: "ollama", key: "model", value: first)
                }
            }
        } catch {
            ollamaFetchError = "Could not connect to Ollama: \(error.localizedDescription)"
        }

        ollamaFetching = false
    }
}
