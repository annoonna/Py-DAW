# -*- coding: utf-8 -*-
"""SandboxedFx — Crash-safe plugin wrapper for FX chain integration.

v0.0.20.700 — Phase P1C

Provides the same API as AudioFxBase (process_inplace, get/set_param)
but routes audio through a sandboxed subprocess. If the plugin crashes,
the wrapper returns silence and reports the crash — the DAW keeps running.

Usage in fx_chain.py:
    # Instead of loading directly:
    #   fx = Vst3Fx(path, sr, ...)
    # Use sandboxed version:
    fx = SandboxedFx.create(
        track_id="trk1", slot_id="fx0",
        plugin_path="/path/to/plugin.vst3",
        plugin_type="vst3",
        sample_rate=48000,
    )
    # Same API:
    fx.process_inplace(buffer, frames, sr)
    fx.set_param("cutoff", 0.5)

Fallback:
    If sandbox launch fails, create() returns None.
    The caller (fx_chain.py) should fall back to in-process loading.
"""
from __future__ import annotations

import logging
import numpy as np
from typing import Any, Dict, List, Optional

from .sandbox_process_manager import (
    SandboxProcessManager, SandboxPluginConfig, get_process_manager,
)

_log = logging.getLogger(__name__)


class SandboxedFx:
    """Sandboxed plugin FX — crash-safe wrapper.

    Implements the same interface as AudioFxBase so it can be used
    as a drop-in replacement in the FX chain.
    """

    def __init__(
        self,
        track_id: str,
        slot_id: str,
        config: SandboxPluginConfig,
        manager: SandboxProcessManager,
    ):
        self._track_id = track_id
        self._slot_id = slot_id
        self._config = config
        self._mgr = manager
        self._bypassed = False
        self._enabled = True
        self._params: Dict[str, float] = {}

        # State
        self.crashed = False
        self.crash_message = ""

    # --- Factory ---

    @staticmethod
    def create(
        track_id: str,
        slot_id: str,
        plugin_path: str,
        plugin_name: str = "",
        plugin_type: str = "vst3",
        sample_rate: int = 48000,
        block_size: int = 512,
        channels: int = 2,
        state_b64: str = "",
        is_instrument: bool = False,
    ) -> Optional[SandboxedFx]:
        """Create a sandboxed plugin FX.

        Returns SandboxedFx on success, None on failure.
        Caller should fall back to in-process loading on None.
        """
        try:
            mgr = get_process_manager()
            config = SandboxPluginConfig(
                track_id=track_id,
                slot_id=slot_id,
                plugin_path=plugin_path,
                plugin_name=plugin_name or plugin_path.split("/")[-1],
                plugin_type=plugin_type,
                sample_rate=sample_rate,
                block_size=block_size,
                channels=channels,
                state_b64=state_b64,
                is_instrument=is_instrument,
            )

            ok = mgr.spawn(track_id, slot_id, config)
            if not ok:
                _log.warning("Sandbox spawn failed for %s/%s — use in-process fallback",
                             track_id, slot_id)
                return None

            fx = SandboxedFx(track_id, slot_id, config, mgr)
            _log.info("SandboxedFx created: %s/%s (%s)", track_id, slot_id, plugin_name)
            return fx

        except Exception as e:
            _log.error("SandboxedFx.create error: %s", e)
            return None

    # --- AudioFxBase-compatible API ---

    def process_inplace(self, buffer: np.ndarray, frames: int, sr: int) -> None:
        """Process audio in-place through the sandboxed plugin.

        If the plugin is crashed or bypassed, buffer is unchanged (passthrough).
        If the plugin doesn't return output in time, buffer is zeroed (silence).
        """
        if not self._enabled or self._bypassed:
            return  # passthrough

        if self._mgr.is_crashed(self._track_id, self._slot_id):
            if not self.crashed:
                self.crashed = True
                self.crash_message = self._mgr.get_crash_info(
                    self._track_id, self._slot_id)
                _log.warning("SandboxedFx %s/%s: plugin crashed — %s",
                             self._track_id, self._slot_id, self.crash_message)
            return  # passthrough (muted would zero the buffer)

        # Send input audio to worker
        ok = self._mgr.send_audio(self._track_id, self._slot_id, buffer, frames)
        if not ok:
            return  # couldn't send — passthrough

        # Read processed output from worker
        # Small busy-wait for worker to process (max 1 buffer cycle)
        import time
        deadline = time.monotonic() + (frames / max(sr, 1)) * 2  # 2× buffer time
        output = None
        while time.monotonic() < deadline:
            output = self._mgr.get_output(self._track_id, self._slot_id, frames)
            if output is not None:
                break
            time.sleep(0.0001)  # 100µs

        if output is not None:
            # Copy output back into the buffer
            try:
                n = min(len(output), len(buffer))
                buffer[:n] = output[:n]
            except (ValueError, IndexError):
                pass  # shape mismatch — passthrough
        # If no output: buffer unchanged (passthrough, not silence)

    def process(self, buffer: np.ndarray, sr: int) -> np.ndarray:
        """Process and return new buffer (alternative API)."""
        out = buffer.copy()
        self.process_inplace(out, len(out), sr)
        return out

    # --- Parameters ---

    def set_param(self, param_id: str, value: float) -> None:
        """Set a plugin parameter via IPC."""
        self._params[param_id] = value
        self._mgr.set_param(self._track_id, self._slot_id, param_id, value)

    def get_param(self, param_id: str) -> float:
        """Get cached parameter value."""
        return self._params.get(param_id, 0.0)

    # --- Bypass / Enable ---

    def set_bypass(self, enabled: bool) -> None:
        """Set bypass state."""
        self._bypassed = bool(enabled)
        self._mgr.set_bypass(self._track_id, self._slot_id, self._bypassed)

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable the FX slot."""
        self._enabled = bool(enabled)

    @property
    def is_bypassed(self) -> bool:
        return self._bypassed

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    # --- v0.0.20.705: Instrument support (P2C) ---

    def note_on(self, pitch: int, velocity: int = 100, **kwargs) -> bool:
        """Send MIDI note-on to instrument worker.

        Compatible with SamplerRegistry note_on interface.
        Extra kwargs (pitch_offset_semitones, etc.) are ignored for sandboxed plugins.
        """
        if not self._enabled or self.crashed:
            return False
        return self._mgr.send_note_on(self._track_id, self._slot_id,
                                       pitch, velocity)

    def note_off(self, pitch: int = -1) -> None:
        """Send MIDI note-off to instrument worker."""
        if not self._enabled:
            return
        self._mgr.send_note_off(self._track_id, self._slot_id, pitch)

    def all_notes_off(self) -> None:
        """MIDI panic — release all notes."""
        self._mgr.send_all_notes_off(self._track_id, self._slot_id)

    def pull(self, frames: int, sr: int):
        """Pull rendered audio from instrument worker.

        Returns numpy array (frames, 2) or None.
        Compatible with Vst3InstrumentEngine.pull() interface.
        """
        if not self._enabled or self._bypassed or self.crashed:
            return None
        output = self._mgr.get_output(self._track_id, self._slot_id, frames)
        if output is not None:
            try:
                import numpy as _np
                out = _np.asarray(output, dtype=_np.float32)
                # Ensure (frames, 2) shape
                if out.ndim == 1:
                    n = min(frames, len(out))
                    result = _np.zeros((frames, 2), dtype=_np.float32)
                    result[:n, 0] = out[:n]
                    result[:n, 1] = out[:n]
                    return result
                if out.ndim == 2 and out.shape[1] >= 2:
                    return out[:frames]
                if out.ndim == 2 and out.shape[1] == 1:
                    n = min(frames, out.shape[0])
                    result = _np.zeros((frames, 2), dtype=_np.float32)
                    result[:n, 0] = out[:n, 0]
                    result[:n, 1] = out[:n, 0]
                    return result
            except Exception:
                pass
        return None

    # --- v0.0.20.705: Editor support (P2B) ---

    def show_editor(self) -> bool:
        """Open plugin editor window in worker process."""
        return self._mgr.show_editor(self._track_id, self._slot_id)

    def hide_editor(self) -> bool:
        """Close plugin editor window in worker process."""
        return self._mgr.hide_editor(self._track_id, self._slot_id)

    # --- Crash recovery ---

    def get_latency(self) -> int:
        """Get plugin-reported processing latency in samples.

        v0.0.20.709: P2C — Plugin Latency Report for PDC.
        """
        return self._mgr.get_latency(self._track_id, self._slot_id)

    def reload(self) -> bool:
        """Restart the crashed plugin with last known state."""
        self.crashed = False
        self.crash_message = ""
        return self._mgr.restart(self._track_id, self._slot_id)

    def is_alive(self) -> bool:
        """Check if the worker is running."""
        return self._mgr.is_alive(self._track_id, self._slot_id)

    # --- Cleanup ---

    def close(self) -> None:
        """Kill the worker and release resources."""
        try:
            self._mgr.kill(self._track_id, self._slot_id)
        except Exception:
            pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
