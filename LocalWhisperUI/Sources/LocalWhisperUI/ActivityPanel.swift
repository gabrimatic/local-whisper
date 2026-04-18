import SwiftUI
import Charts

// MARK: - Activity panel

struct ActivityPanel: View {
    @Environment(AppState.self) private var appState
    @State private var snapshot: ActivitySnapshot = .empty
    @State private var loading = false

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.l + 2) {
                statCards
                activityChart
                Grid(alignment: .leading, horizontalSpacing: Theme.Spacing.l + 2, verticalSpacing: Theme.Spacing.l + 2) {
                    GridRow {
                        topWordsCard
                        topRepsCard
                    }
                }
                refreshFooter
            }
            .padding(Theme.Spacing.xl)
        }
        .task { await refresh() }
        .onChange(of: appState.phase) { _, newPhase in
            // Refresh once a transcription lands so stats update in real time.
            if newPhase == .done {
                Task { await refresh() }
            }
        }
    }

    // MARK: - Stat cards

    private var statCards: some View {
        Grid(horizontalSpacing: Theme.Spacing.l - 2, verticalSpacing: Theme.Spacing.l - 2) {
            GridRow {
                statCard(title: "Sessions", value: "\(snapshot.totalSessions)", icon: "waveform", tint: .red, footnote: snapshot.firstSessionFootnote)
                statCard(title: "Words", value: snapshot.totalWords.formatted(.number), icon: "textformat", tint: .blue, footnote: snapshot.wordsPerSessionFootnote)
                statCard(title: "Today", value: "\(snapshot.todaySessions)", icon: "sun.max.fill", tint: .orange, footnote: "\(snapshot.todayWords.formatted(.number)) words")
                statCard(title: "Last 7 days", value: "\(snapshot.weekSessions)", icon: "calendar", tint: .green, footnote: "\(snapshot.weekWords.formatted(.number)) words")
            }
        }
    }

    private func statCard(title: String, value: String, icon: String, tint: Color, footnote: String?) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs + 2) {
            HStack(spacing: Theme.Spacing.xs + 2) {
                Image(systemName: icon)
                    .foregroundStyle(tint)
                    .symbolRenderingMode(.hierarchical)
                Text(title)
                    .font(Theme.Typography.captionEmphasized)
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
            }
            Text(value)
                .font(Theme.Typography.display)
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .contentTransition(.numericText())
            if let footnote {
                Text(footnote)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
        .padding(Theme.Spacing.l - 2)
        .cardSurface(radius: Theme.Radius.medium)
    }

    // MARK: - 30-day chart

    @ViewBuilder
    private var activityChart: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m - 2) {
            HStack {
                Text("Last 30 days")
                    .font(Theme.Typography.headline)
                Spacer()
                Text("\(snapshot.monthWords.formatted(.number)) words · \(snapshot.monthSessions) sessions")
                    .font(Theme.Typography.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            if snapshot.dailyBuckets.isEmpty {
                emptyChart
            } else {
                Chart(snapshot.dailyBuckets, id: \.date) { bucket in
                    BarMark(
                        x: .value("Day", bucket.date, unit: .day),
                        y: .value("Words", bucket.words)
                    )
                    .foregroundStyle(Color.accentColor.gradient)
                    .cornerRadius(3)
                }
                .chartXAxis {
                    AxisMarks(values: .stride(by: .day, count: 5)) { value in
                        AxisGridLine()
                        AxisTick()
                        AxisValueLabel(format: .dateTime.month(.abbreviated).day())
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading)
                }
                .frame(height: 180)
            }
        }
        .padding(Theme.Spacing.l)
        .cardSurface(radius: Theme.Radius.medium)
    }

    private var emptyChart: some View {
        VStack(spacing: Theme.Spacing.xs + 2) {
            Image(systemName: "chart.bar")
                .font(.title2)
                .foregroundStyle(.secondary)
                .symbolRenderingMode(.hierarchical)
            Text("No activity yet")
                .font(Theme.Typography.bodyEmphasized)
            Text("Record something. The chart fills in as you go.")
                .font(Theme.Typography.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 180)
    }

    // MARK: - Top word / replacement cards

    private var topWordsCard: some View {
        listCard(title: "Top words", icon: "textformat.size", tint: .indigo, items: snapshot.topWords, emptyText: "Words you say often will appear here.")
    }

    private var topRepsCard: some View {
        listCard(title: "Top replacements", icon: "arrow.left.arrow.right", tint: .orange, items: snapshot.topReplacements, emptyText: "Replacement triggers you actually use will rank here.")
    }

    private func listCard(title: String, icon: String, tint: Color, items: [ActivityCount], emptyText: String) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m - 2) {
            HStack(spacing: Theme.Spacing.xs + 2) {
                Image(systemName: icon)
                    .foregroundStyle(tint)
                    .symbolRenderingMode(.hierarchical)
                Text(title).font(Theme.Typography.headline)
                Spacer()
            }
            if items.isEmpty {
                Text(emptyText)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 120, alignment: .center)
                    .multilineTextAlignment(.center)
            } else {
                VStack(spacing: Theme.Spacing.xs + 2) {
                    ForEach(items.prefix(10).enumerated().map({ ($0.offset, $0.element) }), id: \.0) { index, item in
                        HStack {
                            Text("\(index + 1).")
                                .foregroundStyle(.tertiary)
                                .frame(width: 22, alignment: .leading)
                                .monospacedDigit()
                                .font(Theme.Typography.mono)
                            Text(item.label)
                                .font(Theme.Typography.body)
                                .lineLimit(1)
                                .truncationMode(.tail)
                            Spacer()
                            Text("\(item.count)")
                                .font(Theme.Typography.mono)
                                .foregroundStyle(.secondary)
                                .monospacedDigit()
                        }
                    }
                }
            }
        }
        .padding(Theme.Spacing.l)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .cardSurface(radius: Theme.Radius.medium)
    }

    // MARK: - Refresh footer

    private var refreshFooter: some View {
        HStack(spacing: Theme.Spacing.s) {
            if loading {
                ProgressView().controlSize(.small)
                Text("Reading history…")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            } else {
                Image(systemName: "clock.arrow.circlepath")
                    .foregroundStyle(.secondary)
                    .symbolRenderingMode(.hierarchical)
                Text(snapshot.lastUpdatedFootnote)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Refresh") {
                Task { await refresh() }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(loading)
        }
    }

    // MARK: - Loading

    @MainActor
    private func refresh() async {
        loading = true
        defer { loading = false }
        let triggers = Set(appState.config.replacements.rules.keys.map { $0.lowercased() })
        let snap = await Task.detached(priority: .userInitiated) {
            ActivitySnapshot.compute(historyDir: AppDirectories.text, replacementTriggers: triggers)
        }.value
        snapshot = snap
    }
}

// MARK: - Snapshot model

struct ActivityCount: Hashable, Sendable {
    let label: String
    let count: Int
}

struct DailyBucket: Hashable, Sendable {
    let date: Date
    let words: Int
    let sessions: Int
}

struct ActivitySnapshot: Sendable {
    var totalSessions: Int
    var totalWords: Int
    var todaySessions: Int
    var todayWords: Int
    var weekSessions: Int
    var weekWords: Int
    var monthSessions: Int
    var monthWords: Int
    var dailyBuckets: [DailyBucket]
    var topWords: [ActivityCount]
    var topReplacements: [ActivityCount]
    var firstSession: Date?
    var lastSession: Date?
    var generatedAt: Date

    static let empty = ActivitySnapshot(
        totalSessions: 0, totalWords: 0,
        todaySessions: 0, todayWords: 0,
        weekSessions: 0, weekWords: 0,
        monthSessions: 0, monthWords: 0,
        dailyBuckets: [],
        topWords: [], topReplacements: [],
        firstSession: nil, lastSession: nil,
        generatedAt: .distantPast
    )

    var firstSessionFootnote: String? {
        guard let first = firstSession else { return nil }
        return "Since \(first.formatted(date: .abbreviated, time: .omitted))"
    }

    var wordsPerSessionFootnote: String? {
        guard totalSessions > 0 else { return nil }
        return "≈ \(totalWords / max(totalSessions, 1)) per session"
    }

    var lastUpdatedFootnote: String {
        if generatedAt == .distantPast { return "Not loaded yet." }
        return "Updated \(generatedAt.formatted(date: .omitted, time: .shortened))."
    }

    static func compute(historyDir: String, replacementTriggers: Set<String>) -> ActivitySnapshot {
        let fm = FileManager.default
        let url = URL(fileURLWithPath: historyDir)
        guard let files = try? fm.contentsOfDirectory(at: url, includingPropertiesForKeys: nil)
            .filter({ $0.pathExtension == "txt" }) else {
            return .empty
        }

        let calendar = Calendar.current
        let now = Date()
        let todayStart = calendar.startOfDay(for: now)
        let weekStart = calendar.date(byAdding: .day, value: -6, to: todayStart) ?? todayStart
        let monthStart = calendar.date(byAdding: .day, value: -29, to: todayStart) ?? todayStart

        var totalSessions = 0
        var totalWords = 0
        var todaySessions = 0
        var todayWords = 0
        var weekSessions = 0
        var weekWords = 0
        var monthSessions = 0
        var monthWords = 0
        var firstSession: Date?
        var lastSession: Date?
        var wordCounts: [String: Int] = [:]
        var triggerCounts: [String: Int] = [:]
        var bucketByDate: [Date: (words: Int, sessions: Int)] = [:]

        // Pre-seed 30-day buckets so empty days appear in the chart.
        for offset in 0..<30 {
            if let day = calendar.date(byAdding: .day, value: -offset, to: todayStart) {
                bucketByDate[day] = (0, 0)
            }
        }

        for file in files {
            guard let content = try? String(contentsOf: file, encoding: .utf8) else { continue }
            let timestamp = parseTimestamp(file: file)
            let parsed = splitRawAndFinal(content)
            let text = parsed.fixed.isEmpty ? parsed.raw : parsed.fixed

            let words = wordTokens(in: text)
            let wordCount = words.count
            totalSessions += 1
            totalWords += wordCount
            firstSession = min(firstSession ?? timestamp, timestamp)
            lastSession = max(lastSession ?? timestamp, timestamp)

            if calendar.isDate(timestamp, inSameDayAs: now) {
                todaySessions += 1
                todayWords += wordCount
            }
            if timestamp >= weekStart {
                weekSessions += 1
                weekWords += wordCount
            }
            if timestamp >= monthStart {
                monthSessions += 1
                monthWords += wordCount
                let day = calendar.startOfDay(for: timestamp)
                let prev = bucketByDate[day] ?? (0, 0)
                bucketByDate[day] = (prev.words + wordCount, prev.sessions + 1)
            }

            for w in words where !stopwords.contains(w) && w.count > 2 {
                wordCounts[w, default: 0] += 1
            }

            // Replacement-trigger detection: count occurrences of each trigger
            // in the raw text (pre-substitution). Match word-bounded, case-insensitive.
            if !replacementTriggers.isEmpty {
                let raw = parsed.raw.lowercased()
                for trigger in replacementTriggers where !trigger.isEmpty {
                    if let regex = try? NSRegularExpression(pattern: "\\b" + NSRegularExpression.escapedPattern(for: trigger) + "\\b") {
                        let range = NSRange(raw.startIndex..., in: raw)
                        let count = regex.numberOfMatches(in: raw, range: range)
                        if count > 0 {
                            triggerCounts[trigger, default: 0] += count
                        }
                    }
                }
            }
        }

        let topWords = wordCounts
            .sorted { $0.value > $1.value }
            .prefix(10)
            .map { ActivityCount(label: $0.key, count: $0.value) }

        let topReplacements = triggerCounts
            .sorted { $0.value > $1.value }
            .prefix(10)
            .map { ActivityCount(label: $0.key, count: $0.value) }

        let buckets = bucketByDate
            .map { DailyBucket(date: $0.key, words: $0.value.words, sessions: $0.value.sessions) }
            .sorted { $0.date < $1.date }

        return ActivitySnapshot(
            totalSessions: totalSessions,
            totalWords: totalWords,
            todaySessions: todaySessions,
            todayWords: todayWords,
            weekSessions: weekSessions,
            weekWords: weekWords,
            monthSessions: monthSessions,
            monthWords: monthWords,
            dailyBuckets: buckets,
            topWords: topWords,
            topReplacements: topReplacements,
            firstSession: firstSession,
            lastSession: lastSession,
            generatedAt: Date()
        )
    }

    private static func parseTimestamp(file: URL) -> Date {
        let stem = file.deletingPathExtension().lastPathComponent
        let parts = stem.split(separator: "_")
        if parts.count >= 3 {
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyyMMdd_HHmmss_SSSSSS"
            formatter.locale = Locale(identifier: "en_US_POSIX")
            let candidate = "\(parts[0])_\(parts[1])_\(parts[2])"
            if let date = formatter.date(from: candidate) {
                return date
            }
        }
        if let attrs = try? FileManager.default.attributesOfItem(atPath: file.path),
           let mtime = attrs[.modificationDate] as? Date {
            return mtime
        }
        return Date()
    }

    private static func splitRawAndFinal(_ content: String) -> (raw: String, fixed: String) {
        guard let rawRange = content.range(of: "RAW:\n"),
              let fixedRange = content.range(of: "\n\nFIXED:\n") else {
            return (content, content)
        }
        let raw = String(content[rawRange.upperBound..<fixedRange.lowerBound])
        let fixed = String(content[fixedRange.upperBound...])
        return (raw, fixed)
    }

    private static func wordTokens(in text: String) -> [String] {
        let cleaned = text.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
        return cleaned
    }

    static let stopwords: Set<String> = [
        "the","and","for","that","this","with","you","are","was","but","not","have","had","has","were",
        "from","they","what","when","your","just","can","one","all","get","got","like","its","into","out",
        "about","because","there","then","than","them","their","over","also","more","some","other","such",
        "would","could","should","will","been","being","does","did","doing","done","make","made","make","very",
        "really","right","know","think","thing","things","stuff","yeah","okay","ok","actually","basically"
    ]
}
