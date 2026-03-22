# -*- coding: utf-8 -*-
"""Rust Audio Takeover — Handoff from Python to Rust audio engine.

v0.0.20.708 — Phase RA3

Orchestrates the transition from Python's sounddevice audio engine
to the Rust cpal engine. Handles:

1. Reading audio settings (SR, buffer size, device) from QSettings
2. Stopping the Python AudioEngine (releasing the audio device)
3. Starting the Rust engine subprocess (with matching settings)
4. Connecting IPC and wiring events (Playhead, Meters) to GUI
5. Fallback: if Rust fails → restart Python engine

Usage:
    from pydaw.services.rust_audio_takeover import RustAudioTakeover

    takeover = RustAudioTakeover(
        audio_engine=engine,
        bridge=rust_bridge,
        project_service=project_svc,
    )

    # Switch to Rust
    ok = takeover.activate()

    # Switch back to Python
    takeover.deactivate()

    # Check state
    if takeover.is_rust_active:
        ...

Events forwarded from Rust → Qt Signals:
    - PlayheadPosition → transport_service playhead updates
    - MeterLevels → mixer VU meter updates
    - MasterMeterLevel → master meter updates
    - TransportState → play/stop state sync
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

_log = logging.getLogger(__name__)

try:
    from PySide6.QtCore import QObject, Signal, QTimer
    _QT = True
except ImportError:
    _QT = False
    QObject = object  # type: ignore


# ---------------------------------------------------------------------------
# Audio Settings Reader
# ---------------------------------------------------------------------------

def _read_audio_settings() -> Dict[str, Any]:
    """Read audio settings from QSettings.

    Returns dict with: sample_rate, buffer_size, backend, device_name.
    """
    settings: Dict[str, Any] = {
        "sample_rate": 48000,
        "buffer_size": 256,
        "backend": "sounddevice",
        "device_name": "",
    }

    try:
        from pydaw.core.settings import SettingsKeys, get_value
        keys = SettingsKeys()

        sr = get_value(keys.sample_rate, 48000)
        settings["sample_rate"] = int(sr) if sr else 48000

        bs = get_value(keys.buffer_size, 256)
        settings["buffer_size"] = int(bs) if bs else 256

        be = get_value(keys.audio_backend, "sounddevice")
        settings["backend"] = str(be) if be else "sounddevice"

        # Device name (for cpal device selection)
        dev = get_value(keys.audio_output, "")
        settings["device_name"] = str(dev) if dev else ""

    except Exception as e:
        _log.debug("Could not read audio settings: %s", e)

    return settings


# ---------------------------------------------------------------------------
# Rust Audio Takeover
# ---------------------------------------------------------------------------

class RustAudioTakeover:
    """Orchestrates the handoff from Python to Rust audio engine.

    Manages the lifecycle: stop Python → start Rust → wire events.
    Falls back to Python if Rust cannot be started.
    """

    def __init__(
        self,
        audio_engine: Any = None,
        bridge: Any = None,
        project_service: Any = None,
    ):
        self._audio_engine = audio_engine
        self._bridge = bridge
        self._project_svc = project_service
        self._is_rust_active = False
        self._python_was_running = False

        # Event forwarding timer (polls bridge for GUI updates)
        self._event_timer: Optional[Any] = None

        # Callbacks for GUI updates (set by main_window or transport)
        self._playhead_callback: Optional[Callable] = None
        self._meter_callback: Optional[Callable] = None
        self._master_meter_callback: Optional[Callable] = None
        self._transport_state_callback: Optional[Callable] = None

    @property
    def is_rust_active(self) -> bool:
        """True if the Rust engine is currently the active audio backend."""
        return self._is_rust_active

    def set_playhead_callback(self, cb: Callable) -> None:
        """Set callback for playhead position updates from Rust.

        cb(beat: float, sample_pos: int, is_playing: bool)
        """
        self._playhead_callback = cb

    def set_meter_callback(self, cb: Callable) -> None:
        """Set callback for per-track meter levels from Rust.

        cb(levels: list of (track_index, peak_l, peak_r, rms_l, rms_r))
        """
        self._meter_callback = cb

    def set_master_meter_callback(self, cb: Callable) -> None:
        """Set callback for master meter levels.

        cb(peak_l, peak_r, rms_l, rms_r)
        """
        self._master_meter_callback = cb

    def set_transport_state_callback(self, cb: Callable) -> None:
        """Set callback for transport state changes.

        cb(is_playing: bool, beat: float)
        """
        self._transport_state_callback = cb

    # ------------------------------------------------------------------
    # Activate: Python → Rust
    # ------------------------------------------------------------------

    def activate(self) -> bool:
        """Switch from Python to Rust audio engine.

        Steps:
            1. Read audio settings from QSettings
            2. Stop Python AudioEngine
            3. Start Rust engine subprocess
            4. Connect IPC + wire events
            5. Sync project data (RA1 + RA2)

        Returns True if Rust engine is now active.
        """
        if self._is_rust_active:
            _log.info("Rust engine already active")
            return True

        bridge = self._bridge
        if bridge is None:
            _log.error("No RustEngineBridge available")
            return False

        # 1. Read settings
        settings = _read_audio_settings()
        sr = settings["sample_rate"]
        bs = settings["buffer_size"]
        _log.info("Audio takeover: SR=%d, Buffer=%d", sr, bs)

        # 2. Stop Python engine
        self._python_was_running = False
        if self._audio_engine is not None:
            try:
                # Check if Python engine is running
                if hasattr(self._audio_engine, "_engine_thread"):
                    thread = self._audio_engine._engine_thread
                    if thread is not None and hasattr(thread, "isRunning"):
                        if thread.isRunning():
                            self._python_was_running = True
                self._audio_engine.stop()
                _log.info("Python AudioEngine stopped")
            except Exception as e:
                _log.warning("Python engine stop failed: %s", e)

        # 3. Start Rust engine
        try:
            ok = bridge.start_engine(
                sample_rate=sr,
                buffer_size=bs,
            )
            if not ok:
                _log.error("Rust engine failed to start")
                self._fallback_to_python()
                return False
        except Exception as e:
            _log.error("Rust engine start error: %s", e)
            self._fallback_to_python()
            return False

        # 4. Wire events
        self._wire_events()

        # 5. Sync project
        try:
            from pydaw.services.rust_project_sync import RustProjectSyncer
            syncer = RustProjectSyncer(bridge, self._project_svc)
            syncer.sync()
            _log.info("Project synced to Rust engine")
        except Exception as e:
            _log.warning("Project sync failed (non-fatal): %s", e)

        # 6. Sync samples
        try:
            from pydaw.services.rust_sample_sync import RustSampleSyncer
            sample_syncer = RustSampleSyncer(bridge, self._project_svc)
            count = sample_syncer.sync_all()
            _log.info("Sample sync: %d clips", count)
        except Exception as e:
            _log.warning("Sample sync failed (non-fatal): %s", e)

        self._is_rust_active = True
        _log.info("Rust audio engine is now ACTIVE")
        return True

    # ------------------------------------------------------------------
    # Deactivate: Rust → Python
    # ------------------------------------------------------------------

    def deactivate(self) -> None:
        """Switch back from Rust to Python audio engine.

        Steps:
            1. Stop Rust engine
            2. Disconnect event wiring
            3. Restart Python AudioEngine
        """
        if not self._is_rust_active:
            return

        # 1. Stop Rust engine
        bridge = self._bridge
        if bridge is not None:
            try:
                bridge.shutdown()
                _log.info("Rust engine shutdown")
            except Exception as e:
                _log.warning("Rust engine shutdown error: %s", e)

        # 2. Disconnect events
        self._unwire_events()

        # 3. Restart Python engine
        self._fallback_to_python()

        self._is_rust_active = False
        _log.info("Switched back to Python audio engine")

    # ------------------------------------------------------------------
    # Event Wiring
    # ------------------------------------------------------------------

    def _wire_events(self) -> None:
        """Connect Rust engine events to GUI callbacks.

        Uses Qt signals from the bridge if available, otherwise
        polls via timer.
        """
        bridge = self._bridge
        if bridge is None:
            return

        # Connect Qt signals if available
        try:
            if hasattr(bridge, "playhead_changed") and self._playhead_callback:
                bridge.playhead_changed.connect(self._playhead_callback)

            if hasattr(bridge, "track_meters_changed") and self._meter_callback:
                bridge.track_meters_changed.connect(self._meter_callback)

            if hasattr(bridge, "master_meter_changed") and self._master_meter_callback:
                bridge.master_meter_changed.connect(self._master_meter_callback)

            if hasattr(bridge, "transport_state_changed") and self._transport_state_callback:
                bridge.transport_state_changed.connect(self._transport_state_callback)

            _log.info("Rust events wired to GUI")
        except Exception as e:
            _log.debug("Event wiring error: %s", e)

    def _unwire_events(self) -> None:
        """Disconnect Rust engine events from GUI."""
        bridge = self._bridge
        if bridge is None:
            return

        try:
            if hasattr(bridge, "playhead_changed") and self._playhead_callback:
                try:
                    bridge.playhead_changed.disconnect(self._playhead_callback)
                except (TypeError, RuntimeError):
                    pass

            if hasattr(bridge, "track_meters_changed") and self._meter_callback:
                try:
                    bridge.track_meters_changed.disconnect(self._meter_callback)
                except (TypeError, RuntimeError):
                    pass

            if hasattr(bridge, "master_meter_changed") and self._master_meter_callback:
                try:
                    bridge.master_meter_changed.disconnect(self._master_meter_callback)
                except (TypeError, RuntimeError):
                    pass

            if hasattr(bridge, "transport_state_changed") and self._transport_state_callback:
                try:
                    bridge.transport_state_changed.disconnect(self._transport_state_callback)
                except (TypeError, RuntimeError):
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _fallback_to_python(self) -> None:
        """Restart Python AudioEngine as fallback."""
        if self._audio_engine is None:
            return

        if self._python_was_running:
            try:
                settings = _read_audio_settings()
                self._audio_engine.start(
                    backend=settings.get("backend", "sounddevice"),
                    config=settings,
                )
                _log.info("Python AudioEngine restarted (fallback)")
            except Exception as e:
                _log.error("Python engine restart failed: %s", e)
        else:
            _log.info("Python engine was not running — no fallback needed")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get current engine status."""
        bridge = self._bridge
        return {
            "rust_active": self._is_rust_active,
            "rust_connected": (
                bridge is not None and
                getattr(bridge, "_connected", False)
            ),
            "rust_pid": (
                getattr(getattr(bridge, "_process", None), "pid", 0)
                if bridge else 0
            ),
            "python_was_running": self._python_was_running,
        }
