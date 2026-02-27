import AppKit
import SwiftUI

// MARK: - Overlay window controller

@MainActor
final class OverlayWindowController {
    private var panel: NSPanel?
    private let appState: AppState
    private var hideTask: Task<Void, Never>?

    init(appState: AppState) {
        self.appState = appState
        appState.onPhaseChange = { [weak self] phase in
            self?.handlePhaseChange(phase)
        }
    }

    // Called from AppMain after init, kept for API compatibility.
    func setup() {}

    private func createPanel() -> NSPanel {
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 260, height: 80),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: true
        )
        panel.isFloatingPanel = true
        panel.level = .screenSaver
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.ignoresMouseEvents = true
        panel.hidesOnDeactivate = false
        panel.animationBehavior = .none

        let hostingView = NSHostingView(
            rootView: OverlayView(appState: appState)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .ignoresSafeArea()
        )
        panel.contentView = hostingView

        return panel
    }

    private func positionPanel(_ panel: NSPanel) {
        guard let screen = NSScreen.main else { return }
        let visibleFrame = screen.visibleFrame
        let x = visibleFrame.midX - panel.frame.width / 2
        let y = visibleFrame.minY + visibleFrame.height * 0.22
        panel.setFrameOrigin(NSPoint(x: x, y: y))
    }

    private func handlePhaseChange(_ phase: AppPhase) {
        // Cancel any pending hide before deciding what to do.
        hideTask?.cancel()
        hideTask = nil

        guard appState.config.ui.showOverlay else {
            hidePanel()
            return
        }

        switch phase {
        case .idle:
            hidePanel()
        case .recording, .processing, .done, .error, .speaking:
            showPanel()
        }
    }

    private func showPanel() {
        // Belt-and-suspenders cancel of any pending hide.
        hideTask?.cancel()
        hideTask = nil

        let p: NSPanel
        if let existing = panel {
            p = existing
        } else {
            let newPanel = createPanel()
            panel = newPanel
            p = newPanel
        }

        positionPanel(p)
        p.alphaValue = appState.config.ui.overlayOpacity
        p.orderFrontRegardless()
    }

    private func hidePanel() {
        guard let panel, panel.isVisible else { return }
        panel.orderOut(nil)
        panel.alphaValue = 0
    }
}
