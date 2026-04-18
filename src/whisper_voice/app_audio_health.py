# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""AudioHealthMixin: monitor-stream heartbeat + post-wake resync."""

from __future__ import annotations

import threading
from typing import Optional

from .utils import log


class AudioHealthMixin:
    _MONITOR_HEARTBEAT_SECONDS = 60
    _monitor_heartbeat_timer: Optional[threading.Timer]

    def _schedule_monitor_heartbeat(self):
        if self._monitor_heartbeat_timer:
            self._monitor_heartbeat_timer.cancel()
        if self.config.audio.pre_buffer <= 0:
            return
        if self._cleaned_up:
            return
        timer = threading.Timer(self._MONITOR_HEARTBEAT_SECONDS, self._monitor_heartbeat_tick)
        timer.daemon = True
        timer.start()
        self._monitor_heartbeat_timer = timer

    def _monitor_heartbeat_tick(self):
        try:
            self.recorder.heartbeat_monitoring()
        except Exception as e:
            log(f"Monitor heartbeat error: {e}", "WARN")
        finally:
            self._schedule_monitor_heartbeat()

    def _resync_audio(self):
        """Swift sends this after `NSWorkspace.didWakeNotification`."""
        if self.recorder.recording:
            log("Audio resync skipped — recording in progress", "INFO")
            return
        log("Audio resync requested (post-wake)", "INFO")
        try:
            self.recorder.stop_monitoring()
            self.recorder.start_monitoring()
        except Exception as e:
            log(f"Audio resync failed: {e}", "WARN")
