import AppKit
import QuartzCore
import SwiftUI

// MARK: - Overlay window controller

@MainActor
final class OverlayWindowController {
    private var panel: NSPanel?
    private let appState: AppState
    private var safetyHideTask: Task<Void, Never>?

    init(appState: AppState) {
        self.appState = appState
        appState.onPhaseChange = { [weak self] phase in
            self?.handlePhaseChange(phase)
        }
        observeOverlayConfig()
    }

    /// Observe `show_overlay` and `overlay_opacity` so the live pill reacts when the user
    /// toggles or drags the slider mid-recording. `withObservationTracking` only fires
    /// once per change cycle, so we re-arm at the end of each callback.
    private func observeOverlayConfig() {
        withObservationTracking {
            _ = appState.config.ui.showOverlay
            _ = appState.config.ui.overlayOpacity
        } onChange: { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                self.applyOverlayConfig()
                self.observeOverlayConfig()
            }
        }
    }

    private func applyOverlayConfig() {
        if !appState.config.ui.showOverlay {
            hidePanel()
            return
        }
        // Re-show or update opacity if a recording / processing / done state is live.
        switch appState.phase {
        case .idle:
            return
        case .recording, .processing, .done, .error, .speaking:
            if let panel, panel.isVisible {
                panel.alphaValue = appState.config.ui.overlayOpacity
            } else {
                showPanel()
            }
        }
    }

    private func createPanel() -> NSPanel {
        // Sized to fit the pill plus shadow margin. The OverlayView is a
        // fixed-size capsule (290 × 46) and we leave room for the drop shadow.
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 340, height: 90),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: true
        )
        panel.isFloatingPanel = true
        panel.level = .statusBar
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
        // Cancel any pending safety hide on every phase change. The new phase
        // either drives its own retreat or we'll re-arm the safety below.
        safetyHideTask?.cancel()
        safetyHideTask = nil

        guard appState.config.ui.showOverlay else {
            hidePanel()
            return
        }

        switch phase {
        case .idle:
            hidePanel()
        case .recording, .processing, .speaking:
            showPanel()
        case .done, .error:
            showPanel()
            // Safety net: Python schedules an idle state ~1.5s after done /
            // ~2s after error, but if that message is dropped or the service
            // is killed mid-flight the overlay would stay forever. After 6s
            // of done/error with no further updates, force the pill out.
            armSafetyHide(after: 6.0)
        }
    }

    private func armSafetyHide(after seconds: Double) {
        safetyHideTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            guard let self, !Task.isCancelled else { return }
            // Only retreat if we're still in a terminal phase (no new
            // recording started in the meantime).
            switch self.appState.phase {
            case .done, .error:
                self.appState.phase = .idle
                self.hidePanel()
            default:
                break
            }
        }
    }

    private func showPanel() {
        let p: NSPanel
        if let existing = panel {
            p = existing
        } else {
            let newPanel = createPanel()
            panel = newPanel
            p = newPanel
        }

        let target = appState.config.ui.overlayOpacity
        if !p.isVisible {
            // Reposition only on first show — once the pill is on screen,
            // inter-phase transitions (recording → done) must not jump it.
            positionPanel(p)
            p.alphaValue = 0
            p.orderFrontRegardless()
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.18
                ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
                p.animator().alphaValue = target
            }
        } else {
            // Already visible: just keep alpha aligned with the live opacity
            // setting. Do NOT reposition or call orderFrontRegardless — that
            // makes the pill flicker on every state_update.
            p.alphaValue = target
        }
    }

    private func hidePanel() {
        guard let panel, panel.isVisible else { return }
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.16
            ctx.timingFunction = CAMediaTimingFunction(name: .easeIn)
            panel.animator().alphaValue = 0
        }, completionHandler: { [weak panel] in
            Task { @MainActor in
                // If a new show came in mid-fade, alpha is back up — leave the panel mounted.
                guard let panel, panel.alphaValue < 0.05 else { return }
                panel.orderOut(nil)
            }
        })
    }
}
