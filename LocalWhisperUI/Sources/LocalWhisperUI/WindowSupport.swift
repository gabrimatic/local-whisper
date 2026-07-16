import SwiftUI
import AppKit

// MARK: - Window plumbing
//
// Two small utilities that replace the old keyWindow / window-title string
// hacks with deterministic mechanisms:
//
// - `WindowAccessor` resolves the actual NSWindow hosting a SwiftUI view, so
//   chrome configuration and programmatic close never guess via NSApp.keyWindow.
// - `ActivationPolicy` reference-counts "this surface needs the app to be a
//   regular app" holds (settings window, onboarding). The app returns to a
//   menu-bar-only accessory exactly when the last hold releases.

struct WindowAccessor: NSViewRepresentable {
    let onResolve: (NSWindow) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async { [weak view] in
            if let window = view?.window { onResolve(window) }
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        DispatchQueue.main.async { [weak nsView] in
            if let window = nsView?.window { onResolve(window) }
        }
    }
}

@MainActor
final class ActivationPolicy {
    static let shared = ActivationPolicy()
    private var holds = 0
    private var releaseTask: Task<Void, Never>?

    private init() {}

    /// A user-facing window appeared: promote to a regular app (Cmd+Tab,
    /// proper focus) and bring it forward.
    func acquire() {
        holds += 1
        releaseTask?.cancel()
        releaseTask = nil
        if NSApp.activationPolicy() != .regular {
            NSApp.setActivationPolicy(.regular)
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    /// A window disappeared. Debounced so closing one window while opening
    /// another (Settings -> onboarding replay) never flickers the Dock icon.
    func release() {
        holds = max(0, holds - 1)
        guard holds == 0 else { return }
        releaseTask?.cancel()
        releaseTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 400_000_000)
            guard let self, !Task.isCancelled, self.holds == 0 else { return }
            NSApp.setActivationPolicy(.accessory)
        }
    }
}

// MARK: - Settings window chrome

enum SettingsWindowChrome {
    /// Applied once per settings window instance via WindowAccessor.
    @MainActor
    static func configure(_ window: NSWindow) {
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.styleMask.insert(.fullSizeContentView)
        window.tabbingMode = .disallowed
        window.isMovableByWindowBackground = false
    }

    /// Pull the window to the front reliably, including out of the Stage
    /// Manager side strip. Stage Manager can park a window opened from a
    /// non-active context AFTER our first order-front, so re-assert once the
    /// dust settles.
    @MainActor
    static func bringForward(_ window: NSWindow) {
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        // Cooperative activation can refuse a background app, and Stage
        // Manager then parks the window in the side strip — this orders the
        // window on screen regardless of activation.
        window.orderFrontRegardless()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak window] in
            guard let window else { return }
            NSApp.activate(ignoringOtherApps: true)
            window.makeKeyAndOrderFront(nil)
            window.orderFrontRegardless()
        }
    }
}
