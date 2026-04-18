import SwiftUI
import AppKit
import UniformTypeIdentifiers

// MARK: - Vocabulary panel (replacements editor)

struct VocabularyPanel: View {
    @Environment(AppState.self) private var appState

    @State private var searchText: String = ""
    @State private var newSpoken: String = ""
    @State private var newReplacement: String = ""
    @FocusState private var addFocus: AddField?
    @State private var importStatus: String? = nil

    private enum AddField { case spoken, replacement }

    var body: some View {
        ScrollView {
            Form {
                masterSection
                if appState.config.replacements.enabled {
                    rulesSection
                    addSection
                    importExportSection
                }
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Master toggle

    private var masterSection: some View {
        Section {
            Toggle("Replace recurring words and phrases", isOn: Binding(
                get: { appState.config.replacements.enabled },
                set: { v in
                    appState.config.replacements.enabled = v
                    appState.ipcClient?.sendConfigUpdate(section: "replacements", key: "enabled", value: v)
                }
            ))
            .help("Apply your replacement rules after grammar correction. Matching is case-insensitive and word-bounded.")
        } header: {
            SettingsSectionHeader(
                symbol: "character.book.closed",
                title: "Replacements",
                description: "Teach Local Whisper your jargon, names, and slang."
            )
        }
    }

    // MARK: - Rules list

    private var rulesSection: some View {
        Section {
            HStack(spacing: Theme.Spacing.s) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Search rules", text: $searchText)
                    .textFieldStyle(.plain)
                    .disableAutocorrection(true)
                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.tertiary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear search")
                }
            }
            .padding(Theme.Spacing.s)
            .background(Color.secondary.opacity(0.10), in: RoundedRectangle(cornerRadius: Theme.Radius.small))

            if filteredRules.isEmpty {
                emptyStateRow
            } else {
                ForEach(filteredRules, id: \.key) { rule in
                    HStack(spacing: Theme.Spacing.m - 2) {
                        Text(rule.key)
                            .font(Theme.Typography.mono)
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .frame(minWidth: 80, alignment: .leading)
                        Image(systemName: "arrow.right")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                        Text(rule.value)
                            .font(Theme.Typography.body)
                            .lineLimit(1)
                            .truncationMode(.tail)
                        Spacer()
                        Button {
                            removeRule(rule.key)
                        } label: {
                            Image(systemName: "minus.circle.fill")
                                .foregroundStyle(Theme.Tone.danger.color)
                                .symbolRenderingMode(.hierarchical)
                        }
                        .buttonStyle(.plain)
                        .help("Remove rule for \"\(rule.key)\".")
                        .accessibilityLabel("Remove replacement for \(rule.key)")
                    }
                }
            }
        } header: {
            HStack {
                SettingsSectionHeader(symbol: "list.bullet.rectangle", title: "Rules")
                Spacer()
                Text("\(appState.config.replacements.rules.count) total")
                    .font(Theme.Typography.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var emptyStateRow: some View {
        HStack(spacing: Theme.Spacing.s) {
            Image(systemName: searchText.isEmpty ? "tray" : "questionmark.circle")
                .font(.title3)
                .foregroundStyle(.secondary)
                .symbolRenderingMode(.hierarchical)
            VStack(alignment: .leading, spacing: 2) {
                Text(searchText.isEmpty ? "No rules yet" : "No matches")
                    .font(Theme.Typography.bodyEmphasized)
                Text(searchText.isEmpty
                    ? "Add a rule below, e.g. \"gonna\" → \"going to\"."
                    : "Try a different search term.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.vertical, Theme.Spacing.s)
    }

    // MARK: - Add row

    private var addSection: some View {
        Section {
            HStack(spacing: Theme.Spacing.s) {
                TextField("Spoken form", text: $newSpoken)
                    .textFieldStyle(.roundedBorder)
                    .focused($addFocus, equals: .spoken)
                    .disableAutocorrection(true)
                    .onSubmit {
                        addFocus = .replacement
                    }
                Image(systemName: "arrow.right")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                TextField("Replacement", text: $newReplacement)
                    .textFieldStyle(.roundedBorder)
                    .focused($addFocus, equals: .replacement)
                    .onSubmit { commitNewRule() }
                Button("Add") { commitNewRule() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(!canSubmit)
            }
        } header: {
            SettingsSectionHeader(
                symbol: "plus.rectangle",
                title: "Add a rule",
                description: "Press Return to commit. Both fields are required."
            )
        }
    }

    // MARK: - Import / export

    private var importExportSection: some View {
        Section {
            HStack(spacing: Theme.Spacing.m) {
                Button {
                    importRules()
                } label: {
                    Label("Import…", systemImage: "square.and.arrow.down")
                }
                Button {
                    exportRules()
                } label: {
                    Label("Export…", systemImage: "square.and.arrow.up")
                }
                .disabled(appState.config.replacements.rules.isEmpty)
                Spacer()
            }

            if let status = importStatus {
                InlineNotice(kind: .info, text: status)
            }
        } header: {
            SettingsSectionHeader(
                symbol: "tray.full",
                title: "Bulk operations",
                description: "Supports CSV, TSV, and \"spoken\" = \"replacement\" lines."
            )
        }
    }

    // MARK: - Helpers

    private var canSubmit: Bool {
        let s = newSpoken.trimmingCharacters(in: .whitespaces)
        let r = newReplacement.trimmingCharacters(in: .whitespaces)
        return !s.isEmpty && !r.isEmpty
    }

    private var filteredRules: [(key: String, value: String)] {
        let sorted = appState.config.replacements.rules.sorted { $0.key.localizedCaseInsensitiveCompare($1.key) == .orderedAscending }
        let q = searchText.trimmingCharacters(in: .whitespaces).lowercased()
        if q.isEmpty { return sorted }
        return sorted.filter { rule in
            rule.key.lowercased().contains(q) || rule.value.lowercased().contains(q)
        }
    }

    private func commitNewRule() {
        let spoken = newSpoken.trimmingCharacters(in: .whitespaces)
        let replacement = newReplacement.trimmingCharacters(in: .whitespaces)
        guard !spoken.isEmpty, !replacement.isEmpty else { return }
        appState.config.replacements.rules[spoken] = replacement
        appState.ipcClient?.sendReplacementAdd(spoken: spoken, replacement: replacement)
        newSpoken = ""
        newReplacement = ""
        addFocus = .spoken
    }

    private func removeRule(_ key: String) {
        appState.config.replacements.rules.removeValue(forKey: key)
        appState.ipcClient?.sendReplacementRemove(spoken: key)
    }

    // MARK: - Import

    private func importRules() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.commaSeparatedText, .tabSeparatedText, .plainText]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            if let parsed = parseRules(at: url) {
                var added = 0
                for (k, v) in parsed where !k.isEmpty && !v.isEmpty {
                    appState.config.replacements.rules[k] = v
                    appState.ipcClient?.sendReplacementAdd(spoken: k, replacement: v)
                    added += 1
                }
                importStatus = "Imported \(added) rule\(added == 1 ? "" : "s") from \(url.lastPathComponent)."
            } else {
                importStatus = "Could not parse \(url.lastPathComponent)."
            }
        }
    }

    private func parseRules(at url: URL) -> [String: String]? {
        guard let raw = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        var out: [String: String] = [:]
        for line in raw.split(separator: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty || trimmed.hasPrefix("#") { continue }

            // "spoken" = "replacement" or spoken -> replacement, with CSV/TSV fallback
            if let pair = parseQuotedAssignment(trimmed) {
                out[pair.0] = pair.1; continue
            }
            if let pair = parseArrow(trimmed) {
                out[pair.0] = pair.1; continue
            }
            if let pair = parseCSVish(trimmed) {
                out[pair.0] = pair.1; continue
            }
        }
        return out.isEmpty ? nil : out
    }

    private func parseQuotedAssignment(_ s: String) -> (String, String)? {
        // "a" = "b"
        let pattern = #"^"(.+)"\s*=\s*"(.+)"$"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let range = NSRange(s.startIndex..., in: s)
        guard let m = regex.firstMatch(in: s, range: range), m.numberOfRanges == 3 else { return nil }
        guard let kR = Range(m.range(at: 1), in: s), let vR = Range(m.range(at: 2), in: s) else { return nil }
        return (String(s[kR]), String(s[vR]))
    }

    private func parseArrow(_ s: String) -> (String, String)? {
        let parts = s.components(separatedBy: "->")
        guard parts.count == 2 else { return nil }
        let k = parts[0].trimmingCharacters(in: .whitespaces)
        let v = parts[1].trimmingCharacters(in: .whitespaces)
        return (k.isEmpty || v.isEmpty) ? nil : (k, v)
    }

    private func parseCSVish(_ s: String) -> (String, String)? {
        let separators: [Character] = [",", "\t"]
        for sep in separators {
            let parts = s.split(separator: sep, maxSplits: 1).map { String($0) }
            if parts.count == 2 {
                let k = parts[0].trimmingCharacters(in: .whitespacesAndNewlines.union(.init(charactersIn: "\"")))
                let v = parts[1].trimmingCharacters(in: .whitespacesAndNewlines.union(.init(charactersIn: "\"")))
                if !k.isEmpty && !v.isEmpty { return (k, v) }
            }
        }
        return nil
    }

    // MARK: - Export

    private func exportRules() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.commaSeparatedText]
        panel.nameFieldStringValue = "local-whisper-replacements.csv"
        if panel.runModal() == .OK, let url = panel.url {
            let lines = appState.config.replacements.rules
                .sorted { $0.key.localizedCaseInsensitiveCompare($1.key) == .orderedAscending }
                .map { (k, v) in "\"\(k.replacingOccurrences(of: "\"", with: "\"\""))\",\"\(v.replacingOccurrences(of: "\"", with: "\"\""))\"" }
                .joined(separator: "\n")
            try? lines.write(to: url, atomically: true, encoding: .utf8)
            importStatus = "Exported \(appState.config.replacements.rules.count) rule\(appState.config.replacements.rules.count == 1 ? "" : "s") to \(url.lastPathComponent)."
        }
    }
}
