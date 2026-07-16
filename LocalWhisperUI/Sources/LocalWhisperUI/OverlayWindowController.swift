import AppKit
import QuartzCore
import SwiftUI

// MARK: - Overlay window controller

@MainActor
final class OverlayWindowController {
    private var panel: NSPanel?
    private let appState: AppState
    private var safetyHideTask: Task<Void, Never>?
    private var disconnectGraceTask: Task<Void, Never>?
    private var lastVisibilityRepair: CFTimeInterval = 0

    init(appState: AppState) {
        self.appState = appState
        appState.onPhaseChange = { [weak self] phase in
            self?.handlePhaseChange(phase)
        }
        appState.onStateUpdate = { [weak self] phase in
            self?.repairLiveOverlay(for: phase)
        }
        observeOverlayConfig()
        observeConnection()
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

    /// If the service dies (kill -9, crash) mid-recording, no further state
    /// updates will ever arrive — without this, the pill sat frozen on
    /// "Recording…" above every Space forever. Give a reconnect a short
    /// grace period, then retreat to idle.
    private func observeConnection() {
        withObservationTracking {
            _ = appState.connectionState
        } onChange: { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                self.handleConnectionChange()
                self.observeConnection()
            }
        }
    }

    private func handleConnectionChange() {
        guard appState.connectionState == .disconnected, appState.phase != .idle else { return }
        disconnectGraceTask?.cancel()
        disconnectGraceTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard let self, !Task.isCancelled else { return }
            if self.appState.connectionState != .connected && self.appState.phase != .idle {
                self.appState.phase = .idle
                self.hidePanel()
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
        // .screenSaver (1000) sits above fullscreen apps; .statusBar (25) got
        // occluded by fullscreen windows for an accessory app, so the pill
        // went invisible until the user switched spaces.
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
        // Prefer the screen under the cursor so the pill lands where the user
        // is actually working. Fall back to NSScreen.main (key-window screen)
        // and finally the first screen. The one-off "jumped to the left"
        // report traced to NSScreen.main returning a secondary display on the
        // logical left of the primary — following the cursor avoids it.
        let screen = screenUnderCursor()
            ?? NSScreen.main
            ?? NSScreen.screens.first
        guard let screen else { return }
        let visibleFrame = screen.visibleFrame

        // Guard against a degenerate frame (can happen during display
        // reconfig / sleep-wake). Leave the pill at its current origin rather
        // than slamming it to (0, 0) on the primary display.
        guard visibleFrame.width >= 200, visibleFrame.height >= 100 else {
            return
        }

        let x = visibleFrame.midX - panel.frame.width / 2
        let y = visibleFrame.minY + visibleFrame.height * 0.22
        panel.setFrameOrigin(NSPoint(x: x, y: y))
    }

    private func screenUnderCursor() -> NSScreen? {
        let location = NSEvent.mouseLocation
        return NSScreen.screens.first { $0.frame.contains(location) }
    }

    private func handlePhaseChange(_ phase: AppPhase) {
        // Cancel any pending safety hide on every phase change. The new phase
        // either drives its own retreat or we'll re-arm the safety below.
        safetyHideTask?.cancel()
        safetyHideTask = nil

        // Safety net: Python schedules an idle state ~1.5s after done /
        // ~2s after error, but if that message is dropped or the service
        // is killed mid-flight the done/error phase would latch forever —
        // freezing the menu bar icon even when the overlay is disabled.
        // Armed regardless of show_overlay for exactly that reason.
        switch phase {
        case .done, .error:
            armSafetyHide(after: 6.0)
        default:
            break
        }

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
        }
    }

    private func repairLiveOverlay(for phase: AppPhase) {
        switch phase {
        case .done, .error:
            // A SECOND done/error arriving within the safety window must
            // restart the clock, or result #2 gets force-hidden ~1s in.
            safetyHideTask?.cancel()
            armSafetyHide(after: 6.0)
        default:
            break
        }

        guard appState.config.ui.showOverlay else { return }
        switch phase {
        case .recording, .processing, .speaking:
            ensurePanelVisible()
        case .done, .error:
            if panel?.isVisible != true {
                showPanel()
            }
        case .idle:
            break
        }
    }

    private func ensurePanelVisible() {
        guard let panel else {
            showPanel()
            return
        }
        if !panel.isVisible || panel.alphaValue < 0.05 {
            showPanel()
            return
        }

        // Recording state_update messages arrive every 0.1s. Reasserting the
        // level/order once a second repairs Spaces/full-screen/display changes
        // without making the pill flicker on every waveform tick.
        let now = CACurrentMediaTime()
        guard now - lastVisibilityRepair >= 1.0 else { return }
        lastVisibilityRepair = now

        // Display unplugged / arrangement changed since the pill was placed:
        // a frame that no longer intersects any screen is "visible" to AppKit
        // but invisible to the user. Re-place it on the live screen.
        if !NSScreen.screens.contains(where: { $0.frame.intersects(panel.frame) }) {
            positionPanel(panel)
        }

        panel.level = .screenSaver
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        panel.orderFrontRegardless()
        panel.alphaValue = appState.config.ui.overlayOpacity
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
            lastVisibilityRepair = CACurrentMediaTime()
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
