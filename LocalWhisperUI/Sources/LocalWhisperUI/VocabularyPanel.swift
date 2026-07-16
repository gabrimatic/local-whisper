import SwiftUI
import AppKit
import UniformTypeIdentifiers

// MARK: - Vocabulary panel (replacements editor)

struct VocabularyPanel: View {
    @Environment(AppState.self) private var appState

    @State private var searchText: String = ""
    @State private var newSpoken: String = ""
    @State private var newReplacement: String = ""
    /// Set when the pencil loads an existing rule — a changed spoken form
    /// then means RENAME (remove old + add new), not a second rule.
    @State private var editingOriginalKey: String? = nil
    @FocusState private var addFocus: AddField?
    @State private var importStatus: String? = nil
    @State private var importStatusKind: InlineNotice.Kind = .info
    @State private var testInput: String = ""

    private enum AddField { case spoken, replacement }

    var body: some View {
        PanelScaffold(
            title: "Vocabulary",
            subtitle: "Teach Local Whisper your jargon, names, and slang."
        ) {
            masterCard
            if appState.config.replacements.enabled {
                rulesCard
                addCard
                testCard
                importExportCard
            }
        }
        .onChange(of: newSpoken) { _, newValue in
            // Clearing the spoken field abandons a pencil-loaded edit: a
            // stale editingOriginalKey would otherwise delete the original
            // rule when the user types an unrelated new one.
            if newValue.trimmingCharacters(in: .whitespaces).isEmpty {
                editingOriginalKey = nil
            }
        }
    }

    // MARK: - Master toggle

    private var masterCard: some View {
        SettingsCard(
            icon: "character.book.closed",
            title: "Replacements",
            description: "Applied after grammar correction, before delivery."
        ) {
            ToggleRow(
                title: "Replace recurring words and phrases",
                subtitle: "Matching is case-insensitive and word-bounded; longer phrases win.",
                isOn: appState.config.replacements.enabled
            ) { v in
                appState.config.replacements.enabled = v
                appState.ipcClient?.sendConfigUpdate(section: "replacements", key: "enabled", value: v)
            }
        }
    }

    // MARK: - Rules list

    private var rulesCard: some View {
        SettingsCard(
            icon: "list.bullet.rectangle",
            title: "Rules",
            description: ruleCountLabel
        ) {
            WideRow {
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
                .background(Theme.Surface.well, in: RoundedRectangle(cornerRadius: Theme.Radius.small + 2))
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.Radius.small + 2)
                        .strokeBorder(Theme.Surface.stroke, lineWidth: 1)
                )
            }

            if filteredRules.isEmpty {
                WideRow {
                    EmptyStateView(
                        icon: searchText.isEmpty ? "tray" : "questionmark.circle",
                        title: searchText.isEmpty ? "No rules yet" : "No matches",
                        message: searchText.isEmpty
                            ? "Add a rule below, e.g. \"gonna\" → \"going to\"."
                            : "Try a different search term."
                    )
                }
            } else {
                ForEach(filteredRules, id: \.key) { rule in
                    RuleRow(
                        spoken: rule.key,
                        replacement: rule.value,
                        onEdit: {
                            // Load into the editor row for tweaking. Focusing
                            // the field also scrolls the add card into view.
                            newSpoken = rule.key
                            newReplacement = rule.value
                            editingOriginalKey = rule.key
                            addFocus = .replacement
                        },
                        onRemove: { removeRule(rule.key) }
                    )
                }
            }
        }
    }

    private var ruleCountLabel: String {
        let count = appState.config.replacements.rules.count
        return count == 1 ? "1 rule" : "\(count) rules"
    }

    // MARK: - Add row

    private var addCard: some View {
        SettingsCard(
            icon: "plus.rectangle",
            title: "Add a rule",
            description: "Press Return to commit. An empty replacement deletes the spoken word from transcripts."
        ) {
            WideRow {
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
            }
        }
    }

    // MARK: - Live tester

    private var testCard: some View {
        SettingsCard(
            icon: "checkmark.bubble",
            title: "Try it out",
            description: "Runs your sample through the real replacement engine in the service."
        ) {
            WideRow {
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
            }
        }
    }

    // MARK: - Import / export

    private var importExportCard: some View {
        SettingsCard(
            icon: "tray.full",
            title: "Bulk operations",
            description: "Supports CSV, TSV, and \"spoken\" = \"replacement\" lines."
        ) {
            WideRow {
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
            }
        }
    }

    // MARK: - Helpers

    private var canSubmit: Bool {
        !newSpoken.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private var isEditingExisting: Bool {
        let s = newSpoken.trimmingCharacters(in: .whitespaces).lowercased()
        guard !s.isEmpty else { return false }
        // Case-insensitive: the engine matches case-insensitively, so "BTW"
        // and "btw" are the same rule.
        return appState.config.replacements.rules.keys.contains { $0.lowercased() == s }
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

        // Rename: the pencil loaded an existing rule and the spoken form
        // changed — remove the original instead of leaving a duplicate.
        if let original = editingOriginalKey, original != spoken,
           appState.config.replacements.rules[original] != nil {
            appState.config.replacements.rules.removeValue(forKey: original)
            appState.ipcClient?.sendReplacementRemove(spoken: original)
        }
        // Case-insensitive duplicate: matching ignores case, so two casings
        // of one spoken form shadow each other. Replace the old casing.
        for existing in appState.config.replacements.rules.keys
        where existing.lowercased() == spoken.lowercased() && existing != spoken {
            appState.config.replacements.rules.removeValue(forKey: existing)
            appState.ipcClient?.sendReplacementRemove(spoken: existing)
        }

        appState.config.replacements.rules[spoken] = replacement
        appState.ipcClient?.sendReplacementAdd(spoken: spoken, replacement: replacement)
        newSpoken = ""
        newReplacement = ""
        editingOriginalKey = nil
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

// MARK: - Rule row

private struct RuleRow: View {
    let spoken: String
    let replacement: String
    let onEdit: () -> Void
    let onRemove: () -> Void

    @State private var hovering = false

    var body: some View {
        HStack(spacing: Theme.Spacing.m - 2) {
            Text(spoken)
                .font(Theme.Typography.mono)
                .foregroundStyle(.primary)
                .lineLimit(1)
                .truncationMode(.tail)
                .frame(minWidth: 80, alignment: .leading)
            Image(systemName: "arrow.right")
                .font(.caption2)
                .foregroundStyle(.tertiary)
            Text(replacement.isEmpty ? "removed" : replacement)
                .font(Theme.Typography.body)
                .italic(replacement.isEmpty)
                .foregroundStyle(replacement.isEmpty ? .secondary : .primary)
                .lineLimit(1)
                .truncationMode(.tail)
            Spacer()
            HStack(spacing: Theme.Spacing.xs + 2) {
                Button(action: onEdit) {
                    Image(systemName: "pencil.circle.fill")
                        .foregroundStyle(.secondary)
                        .symbolRenderingMode(.hierarchical)
                }
                .buttonStyle(.plain)
                .help("Edit rule for \"\(spoken)\".")
                .accessibilityLabel("Edit replacement for \(spoken)")
                Button(action: onRemove) {
                    Image(systemName: "minus.circle.fill")
                        .foregroundStyle(Theme.Tone.danger.color)
                        .symbolRenderingMode(.hierarchical)
                }
                .buttonStyle(.plain)
                .help("Remove rule for \"\(spoken)\".")
                .accessibilityLabel("Remove replacement for \(spoken)")
            }
            // Always present (keyboard / VoiceOver reachable), emphasized on hover.
            .opacity(hovering ? 1.0 : 0.45)
        }
        .padding(.horizontal, Theme.Spacing.l)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
        .background(hovering ? Theme.Surface.hover : Color.clear)
        .onHover { hovering = $0 }
        .animation(Theme.Motion.hover, value: hovering)
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

        // Decide the file's format once, for the whole file. Majority vote
        // beats first-line guessing: one arrow line whose value contains a
        // comma must not flip the entire file into CSV parsing — and a CSV
        // whose VALUES contain "->" must not flip into arrow parsing, so
        // only delimiter-free arrow lines count as arrow evidence.
        var out: [String: String] = [:]
        let arrowLines = dataLines.filter {
            $0.contains("->") && !$0.contains(",") && !$0.contains("\t")
        }.count
        if parseQuotedAssignment(first) != nil {
            for line in dataLines {
                if let pair = parseQuotedAssignment(line) { out[pair.0] = pair.1 }
            }
        } else if arrowLines * 2 > dataLines.count {
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
            for (index, record) in scanRecords(raw, delimiter: delimiter).enumerated() {
                guard record.count >= 2 else { continue }
                let keyField = record[0]
                let valueField = record[1]
                // Excel/Numbers exports lead with a header row — importing it
                // would create a rule rewriting the word "spoken". Kept
                // narrow: "from"/"to" style pairs are legitimate rules.
                if index == 0, !keyField.wasQuoted {
                    let k = keyField.value.trimmingCharacters(in: .whitespaces).lowercased()
                    let v = valueField.value.trimmingCharacters(in: .whitespaces).lowercased()
                    if ["spoken", "spoken form"].contains(k), v == "replacement" {
                        continue
                    }
                }
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
        // "a" = "b" — accepts doubled-quote escapes AND TOML backslash
        // escapes (\" \n \t \\), since users paste lines from config.toml.
        let pattern = #"^"((?:[^"\\]|\\.|"")+)"\s*=\s*"((?:[^"\\]|\\.|"")*)"$"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let range = NSRange(s.startIndex..., in: s)
        guard let m = regex.firstMatch(in: s, range: range), m.numberOfRanges == 3 else { return nil }
        guard let kR = Range(m.range(at: 1), in: s), let vR = Range(m.range(at: 2), in: s) else { return nil }
        // Doubled-quote escapes first, then the TOML backslash escapes that
        // config.toml itself uses — users paste lines straight from there.
        let unescape = { (raw: Substring) -> String in
            var v = String(raw).replacingOccurrences(of: "\"\"", with: "\"")
            v = v.replacingOccurrences(of: "\\\\", with: "\u{0}")
                .replacingOccurrences(of: "\\n", with: "\n")
                .replacingOccurrences(of: "\\t", with: "\t")
                .replacingOccurrences(of: "\\\"", with: "\"")
                .replacingOccurrences(of: "\u{0}", with: "\\")
            return v
        }
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
