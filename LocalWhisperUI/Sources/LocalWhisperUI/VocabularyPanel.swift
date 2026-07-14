import SwiftUI
import AppKit
import UniformTypeIdentifiers

// MARK: - Vocabulary panel (replacements editor)

struct VocabularyPanel: View {
    @Environment(AppState.self) private var appState
    @Environment(\.colorScheme) private var colorScheme

    @State private var searchText: String = ""
    @State private var newSpoken: String = ""
    @State private var newReplacement: String = ""
    @FocusState private var addFocus: AddField?
    @State private var importStatus: String? = nil
    @State private var importStatusKind: InlineNotice.Kind = .info
    @State private var testInput: String = ""

    private enum AddField { case spoken, replacement }

    var body: some View {
        ScrollView {
            Form {
                masterSection
                if appState.config.replacements.enabled {
                    rulesSection
                    addSection
                    testSection
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
            .help("Apply your replacement rules after grammar correction. Matching is case-insensitive and word-bounded; longer phrases win.")
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
                        Text(rule.value.isEmpty ? "removed" : rule.value)
                            .font(Theme.Typography.body)
                            .italic(rule.value.isEmpty)
                            .foregroundStyle(rule.value.isEmpty ? .secondary : .primary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                        Spacer()
                        Button {
                            // Load into the editor row for tweaking; saving
                            // overwrites the rule (same spoken form).
                            newSpoken = rule.key
                            newReplacement = rule.value
                            addFocus = .replacement
                        } label: {
                            Image(systemName: "pencil.circle.fill")
                                .foregroundStyle(.secondary)
                                .symbolRenderingMode(.hierarchical)
                        }
                        .buttonStyle(.plain)
                        .help("Edit rule for \"\(rule.key)\".")
                        .accessibilityLabel("Edit replacement for \(rule.key)")
                        Button {
                            removeRule(rule.key)
                        } label: {
                            Image(systemName: "minus.circle.fill")
                                .foregroundStyle(Theme.Tone.danger.color(for: colorScheme))
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
                TextField("Replacement (empty = remove word)", text: $newReplacement)
                    .textFieldStyle(.roundedBorder)
                    .focused($addFocus, equals: .replacement)
                    .onSubmit { commitNewRule() }
                Button(isEditingExisting ? "Save" : "Add") { commitNewRule() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(!canSubmit)
            }
        } header: {
            SettingsSectionHeader(
                symbol: "plus.rectangle",
                title: "Add a rule",
                description: "Press Return to commit. An empty replacement deletes the spoken word from transcripts."
            )
        }
    }

    // MARK: - Live tester

    private var testSection: some View {
        Section {
            HStack(spacing: Theme.Spacing.s) {
                TextField("Type a sample sentence…", text: $testInput)
                    .textFieldStyle(.roundedBorder)
                    .disableAutocorrection(true)
                    .onSubmit { runTest() }
                Button("Test") { runTest() }
                    .disabled(testInput.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            if let result = appState.replacementTestResult {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    HStack(alignment: .top, spacing: Theme.Spacing.s) {
                        Text("In")
                            .font(Theme.Typography.captionEmphasized)
                            .foregroundStyle(.secondary)
                            .frame(width: 28, alignment: .trailing)
                        Text(result.input)
                            .font(Theme.Typography.body)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                    HStack(alignment: .top, spacing: Theme.Spacing.s) {
                        Text("Out")
                            .font(Theme.Typography.captionEmphasized)
                            .foregroundStyle(.secondary)
                            .frame(width: 28, alignment: .trailing)
                        Text(result.output)
                            .font(Theme.Typography.bodyEmphasized)
                            .textSelection(.enabled)
                    }
                    if result.input == result.output {
                        Text("No rule matched this text.")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 2)
            }
        } header: {
            SettingsSectionHeader(
                symbol: "checkmark.bubble",
                title: "Try it out",
                description: "Runs your sample through the real replacement engine in the service."
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
                InlineNotice(kind: importStatusKind, text: status)
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
        !newSpoken.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private var isEditingExisting: Bool {
        let s = newSpoken.trimmingCharacters(in: .whitespaces)
        return !s.isEmpty && appState.config.replacements.rules[s] != nil
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
        // The replacement is used verbatim (minus line breaks): leading or
        // trailing spaces can be intentional, and empty means "remove word".
        let replacement = newReplacement
            .replacingOccurrences(of: "\r", with: "")
            .replacingOccurrences(of: "\n", with: " ")
        guard !spoken.isEmpty else { return }
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

    private func runTest() {
        let text = testInput.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        appState.ipcClient?.sendReplacementTest(text: text)
    }

    // MARK: - Import

    private func importRules() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.commaSeparatedText, .tabSeparatedText, .plainText]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            if let parsed = RuleFileCodec.parse(url: url), !parsed.isEmpty {
                let existing = appState.config.replacements.rules
                let updated = parsed.keys.filter { existing[$0] != nil }.count
                for (k, v) in parsed {
                    appState.config.replacements.rules[k] = v
                }
                // One bulk IPC message: a single config rewrite + snapshot
                // instead of hammering the service once per rule.
                appState.ipcClient?.sendReplacementImport(rules: parsed)
                importStatusKind = .success
                importStatus = "Imported \(parsed.count) rule\(parsed.count == 1 ? "" : "s") from \(url.lastPathComponent)"
                    + (updated > 0 ? " (\(updated) updated)." : ".")
            } else {
                importStatusKind = .error
                importStatus = "Could not parse \(url.lastPathComponent)."
            }
        }
    }

    // MARK: - Export

    private func exportRules() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.commaSeparatedText]
        panel.nameFieldStringValue = "local-whisper-replacements.csv"
        if panel.runModal() == .OK, let url = panel.url {
            let csv = RuleFileCodec.encodeCSV(appState.config.replacements.rules)
            do {
                try csv.write(to: url, atomically: true, encoding: .utf8)
                importStatusKind = .success
                importStatus = "Exported \(appState.config.replacements.rules.count) rule\(appState.config.replacements.rules.count == 1 ? "" : "s") to \(url.lastPathComponent)."
            } catch {
                importStatusKind = .error
                importStatus = "Export failed: \(error.localizedDescription)"
            }
        }
    }
}

// MARK: - Rule file parsing / encoding
//
// One codec whose CSV output round-trips through its own parser (proper
// RFC-4180 quoting both ways) and through `wh replace import`.

enum RuleFileCodec {

    static func encodeCSV(_ rules: [String: String]) -> String {
        rules
            .sorted { $0.key.localizedCaseInsensitiveCompare($1.key) == .orderedAscending }
            .map { "\(quote($0.key)),\(quote($0.value))" }
            .joined(separator: "\n") + "\n"
    }

    private static func quote(_ field: String) -> String {
        "\"" + field.replacingOccurrences(of: "\"", with: "\"\"") + "\""
    }

    static func parse(url: URL) -> [String: String]? {
        guard var raw = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        // Excel exports: BOM + CRLF line endings.
        if raw.hasPrefix("\u{FEFF}") { raw.removeFirst() }
        raw = raw.replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")

        let dataLines = raw.split(separator: "\n", omittingEmptySubsequences: true)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && !$0.hasPrefix("#") }
        guard let first = dataLines.first else { return nil }

        // Decide the file's format once, from the first data line —
        // per-line guessing misparses values that merely contain "->".
        var out: [String: String] = [:]
        if parseQuotedAssignment(first) != nil {
            for line in dataLines {
                if let pair = parseQuotedAssignment(line) { out[pair.0] = pair.1 }
            }
        } else if first.contains("->") && !first.contains(",") && !first.contains("\t") {
            for line in dataLines {
                let parts = line.components(separatedBy: "->")
                guard parts.count == 2 else { continue }
                let k = parts[0].trimmingCharacters(in: .whitespaces)
                let v = parts[1].trimmingCharacters(in: .whitespaces)
                if !k.isEmpty { out[k] = v }
            }
        } else {
            // CSV/TSV: scan the WHOLE text so quoted fields may legally
            // contain the delimiter, doubled quotes, and even newlines
            // (this codec's own export writes such values).
            let delimiter: Character = first.contains("\t") ? "\t" : ","
            for record in scanRecords(raw, delimiter: delimiter) {
                guard record.count >= 2 else { continue }
                let keyField = record[0]
                let valueField = record[1]
                // RFC 4180: quoted content is verbatim; only unquoted
                // fields tolerate stray padding.
                let key = keyField.wasQuoted
                    ? keyField.value
                    : keyField.value.trimmingCharacters(in: .whitespaces)
                if key.isEmpty || key.hasPrefix("#") { continue }
                let value = valueField.wasQuoted
                    ? valueField.value
                    : valueField.value.trimmingCharacters(in: .whitespaces)
                out[key] = value
            }
        }
        return out.isEmpty ? nil : out
    }

    private static func parseQuotedAssignment(_ s: String) -> (String, String)? {
        // "a" = "b" — with doubled-quote escapes inside the quoted parts.
        let pattern = #"^"((?:[^"]|"")+)"\s*=\s*"((?:[^"]|"")*)"$"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let range = NSRange(s.startIndex..., in: s)
        guard let m = regex.firstMatch(in: s, range: range), m.numberOfRanges == 3 else { return nil }
        guard let kR = Range(m.range(at: 1), in: s), let vR = Range(m.range(at: 2), in: s) else { return nil }
        let unescape = { (raw: Substring) in String(raw).replacingOccurrences(of: "\"\"", with: "\"") }
        let key = unescape(s[kR])
        return key.isEmpty ? nil : (key, unescape(s[vR]))
    }

    struct Field {
        var value: String
        var wasQuoted: Bool
    }

    /// RFC-4180 record scanner over the whole text: quoted fields may span
    /// newlines and contain doubled-quote escapes and the delimiter.
    private static func scanRecords(_ text: String, delimiter: Character) -> [[Field]] {
        var records: [[Field]] = []
        var record: [Field] = []
        var current = ""
        var wasQuoted = false
        var inQuotes = false

        var iterator = text.makeIterator()
        var pending: Character? = iterator.next()

        func endField() {
            record.append(Field(value: current, wasQuoted: wasQuoted))
            current = ""
            wasQuoted = false
        }

        func endRecord() {
            endField()
            if !(record.count == 1 && !record[0].wasQuoted
                 && record[0].value.trimmingCharacters(in: .whitespaces).isEmpty) {
                records.append(record)
            }
            record = []
        }

        while let ch = pending {
            pending = iterator.next()
            if inQuotes {
                if ch == "\"" {
                    if pending == "\"" {  // escaped quote
                        current.append("\"")
                        pending = iterator.next()
                    } else {
                        inQuotes = false
                    }
                } else {
                    current.append(ch)
                }
            } else if ch == "\"" && current.trimmingCharacters(in: .whitespaces).isEmpty {
                current = ""
                wasQuoted = true
                inQuotes = true
            } else if ch == delimiter {
                endField()
            } else if ch == "\n" {
                endRecord()
            } else {
                current.append(ch)
            }
        }
        if !current.isEmpty || !record.isEmpty {
            endRecord()
        }
        return records
    }
}
