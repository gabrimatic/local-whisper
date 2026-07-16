import SwiftUI
import AppKit

// MARK: - Shortcut recorder
//
// Click the field, press the combo, done — no typing "ctrl+shift+g" into a
// free-text box. Mirrors the Python service's parser rules exactly:
// modifiers ctrl/alt/shift/cmd; keys a-z, 0-9, f1-f12, common punctuation;
// bare keys allowed only for F-keys (anything else would hijack typing).

enum ShortcutSpec {
    /// ANSI virtual keycode -> canonical key name. Mirrors
    /// key_interceptor.VK_TO_CHAR on the Python side.
    static let keycodeNames: [UInt16: String] = [
        0x00: "a", 0x0B: "b", 0x08: "c", 0x02: "d", 0x0E: "e", 0x03: "f",
        0x05: "g", 0x04: "h", 0x22: "i", 0x26: "j", 0x28: "k", 0x25: "l",
        0x2E: "m", 0x2D: "n", 0x1F: "o", 0x23: "p", 0x0C: "q", 0x0F: "r",
        0x01: "s", 0x11: "t", 0x20: "u", 0x09: "v", 0x0D: "w", 0x07: "x",
        0x10: "y", 0x06: "z",
        0x12: "1", 0x13: "2", 0x14: "3", 0x15: "4", 0x17: "5",
        0x16: "6", 0x1A: "7", 0x1C: "8", 0x19: "9", 0x1D: "0",
        0x7A: "f1", 0x78: "f2", 0x63: "f3", 0x76: "f4", 0x60: "f5", 0x61: "f6",
        0x62: "f7", 0x64: "f8", 0x65: "f9", 0x6D: "f10", 0x67: "f11", 0x6F: "f12",
        0x2B: ",", 0x2F: ".", 0x2C: "/", 0x29: ";", 0x27: "'",
        0x21: "[", 0x1E: "]", 0x2A: "\\", 0x1B: "-", 0x18: "=", 0x32: "`",
    ]

    static let functionKeys: Set<String> = Set((1...12).map { "f\($0)" })

    /// Essential system/app shortcuts that a global event tap must never
    /// hijack. Only plain ⌘ combos are blocked — adding ⌃ or ⌥ is fine.
    static let reservedBareCmdKeys: Set<String> = [
        "q", "w", "c", "v", "x", "a", "z", "s", "n", "t", "f", "h", "m", "p", ",",
    ]

    /// Canonical modifier order used by the Python normalizer.
    static func canonicalCombo(modifiers: [String], key: String) -> String {
        let order = ["ctrl", "alt", "shift", "cmd"]
        let sorted = order.filter { modifiers.contains($0) }
        return (sorted + [key]).joined(separator: "+")
    }

    static func combo(from event: NSEvent) -> (combo: String, error: String?)? {
        guard let key = keycodeNames[event.keyCode] else {
            return (combo: "", error: "That key can't be used — pick a-z, 0-9, F1-F12, or common punctuation.")
        }
        var modifiers: [String] = []
        let flags = event.modifierFlags
        if flags.contains(.control) { modifiers.append("ctrl") }
        if flags.contains(.option) { modifiers.append("alt") }
        if flags.contains(.shift) { modifiers.append("shift") }
        if flags.contains(.command) { modifiers.append("cmd") }

        if modifiers.isEmpty && !functionKeys.contains(key) {
            return (combo: "", error: "Add a modifier (⌃⌥⇧⌘) — a bare \"\(key.uppercased())\" would hijack normal typing.")
        }
        if modifiers == ["cmd"] && reservedBareCmdKeys.contains(key) {
            return (combo: "", error: "⌘\(key.uppercased()) is reserved by macOS and apps — add ⌃ or ⌥ to the combo.")
        }
        return (combo: canonicalCombo(modifiers: modifiers, key: key), error: nil)
    }
}

// MARK: - One recorder at a time
//
// Two fields recording simultaneously meant a keypress committed to whichever
// installed its monitor first — visually, the wrong field. Starting a new
// capture stops any other live one.

@MainActor
enum ShortcutCaptureCoordinator {
    private static var activeID: UUID?
    private static var stopActive: (() -> Void)?

    static func begin(id: UUID, stop: @escaping () -> Void) {
        if activeID != id { stopActive?() }
        activeID = id
        stopActive = stop
    }

    static func end(id: UUID) {
        guard activeID == id else { return }
        activeID = nil
        stopActive = nil
    }
}

struct ShortcutRecorderField: View {
    let title: String
    let description: String
    let icon: String
    let tint: Color
    /// Current canonical value ("" = disabled).
    let value: String
    let defaultValue: String
    /// Other live bindings to refuse: canonical combo -> owner label.
    /// Autoclosure so conflicts are read from LIVE state at keypress time,
    /// not frozen at monitor-install time.
    private let conflictsProvider: () -> [String: String]
    /// Key parts that can never be bound regardless of modifiers (the
    /// dictation trigger key intercepts its keycode wholesale): key -> owner.
    private let blockedKeysProvider: () -> [String: String]
    let onCommit: (String) -> Void

    init(
        title: String,
        description: String,
        icon: String,
        tint: Color,
        value: String,
        defaultValue: String,
        conflicts: @autoclosure @escaping () -> [String: String],
        blockedKeys: @autoclosure @escaping () -> [String: String] = [:],
        onCommit: @escaping (String) -> Void
    ) {
        self.title = title
        self.description = description
        self.icon = icon
        self.tint = tint
        self.value = value
        self.defaultValue = defaultValue
        self.conflictsProvider = conflicts
        self.blockedKeysProvider = blockedKeys
        self.onCommit = onCommit
    }

    @Environment(AppState.self) private var appState
    @State private var isRecording = false
    @State private var errorText: String?
    @State private var monitor: Any?
    @State private var fieldID = UUID()
    @State private var captureTimeout: Task<Void, Never>?

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            HStack(alignment: .center, spacing: Theme.Spacing.s) {
                Image(systemName: icon)
                    .foregroundStyle(tint)
                    .symbolRenderingMode(.hierarchical)
                    .frame(width: 18)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(Theme.Typography.bodyEmphasized)
                    Text(description)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: Theme.Spacing.s)

                recorderButton

                Menu {
                    Button("Reset to \(KeyboardGlyph.display(defaultValue))") {
                        stopRecording()
                        // Same conflict rule as recording: a reset must not
                        // silently steal a combo another binding now owns.
                        if let owner = conflictsProvider()[defaultValue], defaultValue != value {
                            errorText = "\(KeyboardGlyph.display(defaultValue)) is already used by \(owner)."
                        } else {
                            errorText = nil
                            onCommit(defaultValue)
                        }
                    }
                    .disabled(value == defaultValue)
                    Button("Turn off shortcut") {
                        stopRecording()
                        errorText = nil
                        onCommit("")
                    }
                    .disabled(value.isEmpty)
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .accessibilityLabel("\(title) shortcut options")
            }

            if let errorText {
                InlineNotice(kind: .warning, text: errorText)
            }
        }
        .padding(.vertical, 2)
        .onDisappear { stopRecording() }
    }

    private var recorderButton: some View {
        Button {
            isRecording ? stopRecording() : startRecording()
        } label: {
            HStack(spacing: 4) {
                if isRecording {
                    Image(systemName: "record.circle")
                        .foregroundStyle(Theme.Tone.danger.color)
                    Text("Press shortcut…")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                } else if value.isEmpty {
                    Text("Off")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(Array(KeyboardGlyph.tokens(for: value).enumerated()), id: \.offset) { _, token in
                        KeyCap(label: token)
                    }
                }
            }
            .padding(.horizontal, Theme.Spacing.s)
            .padding(.vertical, 4)
            .frame(minWidth: 110)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.small)
                    .fill(isRecording ? Theme.Surface.hover : Theme.Surface.well)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.small)
                    .strokeBorder(
                        isRecording ? Theme.Tone.danger.color.opacity(0.6) : Theme.Surface.stroke,
                        lineWidth: 1
                    )
            )
        }
        .buttonStyle(.plain)
        .help(isRecording
              ? "Press the new key combination, or Esc to cancel."
              : "Click, then press the new key combination.")
        .accessibilityLabel(
            value.isEmpty
                ? "\(title) shortcut, off. Activate to record a new shortcut."
                : "\(title) shortcut, currently \(KeyboardGlyph.display(value)). Activate to record a new shortcut."
        )
    }

    private func startRecording() {
        ShortcutCaptureCoordinator.begin(id: fieldID) {
            stopRecording()
        }
        errorText = nil
        isRecording = true
        // Pause the service's global event tap so a combo that is currently
        // bound reaches this recorder instead of firing its action.
        appState.ipcClient?.send(CaptureModeMessage(active: true))
        // Auto-stop BEFORE the service's 30s capture watchdog expires, so
        // interception can never silently re-arm under a live recorder.
        captureTimeout = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 25_000_000_000)
            guard !Task.isCancelled else { return }
            stopRecording()
            errorText = "Recording timed out — click the field to try again."
        }
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            handle(event: event)
            return nil  // swallow the keystroke while recording
        }
    }

    private func stopRecording() {
        captureTimeout?.cancel()
        captureTimeout = nil
        if let monitor {
            NSEvent.removeMonitor(monitor)
        }
        monitor = nil
        if isRecording {
            appState.ipcClient?.send(CaptureModeMessage(active: false))
        }
        isRecording = false
        ShortcutCaptureCoordinator.end(id: fieldID)
    }

    private func handle(event: NSEvent) {
        // Esc cancels.
        if event.keyCode == 53 {
            stopRecording()
            return
        }
        guard let parsed = ShortcutSpec.combo(from: event) else {
            return
        }
        if let error = parsed.error {
            errorText = error
            return
        }
        let combo = parsed.combo
        if let keyPart = combo.split(separator: "+").last.map(String.init),
           let owner = blockedKeysProvider()[keyPart] {
            errorText = "\(keyPart.uppercased()) is your \(owner) — any combo on that key would be intercepted before it could fire."
            return
        }
        if let owner = conflictsProvider()[combo], !combo.isEmpty, combo != value {
            errorText = "\(KeyboardGlyph.display(combo)) is already used by \(owner)."
            return
        }
        errorText = nil
        stopRecording()
        onCommit(combo)
    }
}
