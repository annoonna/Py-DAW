# -*- coding: utf-8 -*-
"""Rust Hybrid Engine — Mixed Rust+Python rendering + Full Rust mode.

v0.0.20.708 — Phase RA4 + RA5

RA4: Hybrid Mode
    Tracks with only built-in instruments/FX → rendered by Rust
    Tracks with external VST/CLAP → rendered by Python (Sandbox)
    Master mix combines both in Python

RA5: Full Rust Mode
    All tracks → Rust (if all tracks are Rust-compatible)
    QSettings: "Audio Engine" = "Python" | "Hybrid" | "Rust"
    Fallback: auto-downgrade to Hybrid or Python on crash

Usage:
    from pydaw.services.rust_hybrid_engine import RustHybridEngine, EngineMode

    hybrid = RustHybridEngine(
        audio_engine=engine,
        bridge=rust_bridge,
        project_service=project_svc,
    )

    hybrid.set_mode(EngineMode.HYBRID)
    hybrid.activate()

Architecture:
    ┌─────────────────────────────────────┐
    │  RustHybridEngine                   │
    │                                     │
    │  EngineMode.PYTHON → all Python     │
    │  EngineMode.HYBRID → per-track      │
    │  EngineMode.RUST   → all Rust       │
    │                                     │
    │  Tracks:                            │
    │    "R" badge → Rust AudioGraph      │
    │    "P" badge → Python SandboxedFx   │
    │                                     │
    │  Master Mix:                        │
    │    Rust output + Python output      │
    │    → Master bus → speakers          │
    └─────────────────────────────────────┘
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine Mode
# ---------------------------------------------------------------------------

class EngineMode(Enum):
    """Audio engine rendering mode."""
    PYTHON = "python"   # All tracks rendered by Python (default, safe)
    HYBRID = "hybrid"   # Per-track: Rust for built-in, Python for external
    RUST = "rust"       # All tracks rendered by Rust (max performance)


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

_SETTINGS_KEY = "audio/engine_mode"

def _load_mode() -> EngineMode:
    """Load engine mode from QSettings."""
    try:
        from pydaw.core.settings import get_value
        raw = str(get_value(_SETTINGS_KEY, "python") or "python").lower()
        if raw == "rust":
            return EngineMode.RUST
        if raw == "hybrid":
            return EngineMode.HYBRID
        return EngineMode.PYTHON
    except Exception:
        return EngineMode.PYTHON


def _save_mode(mode: EngineMode) -> None:
    """Save engine mode to QSettings."""
    try:
        from pydaw.core.settings import set_value
        set_value(_SETTINGS_KEY, mode.value)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Track Assignment
# ---------------------------------------------------------------------------

def assign_tracks(project: Any) -> List[Dict[str, Any]]:
    """Determine which backend renders each track.

    Uses EngineMigrationController.can_track_use_rust() to decide.

    Returns list of dicts:
        [{"track_id": "trk_...", "name": "...", "backend": "rust"|"python",
          "reason": "..."}]
    """
    results: List[Dict[str, Any]] = []
    all_tracks = list(getattr(project, "tracks", []) or [])

    try:
        from pydaw.services.engine_migration import EngineMigrationController
        ctrl = EngineMigrationController()
    except Exception:
        # No migration controller → all Python
        for t in all_tracks:
            results.append({
                "track_id": str(getattr(t, "id", "")),
                "name": str(getattr(t, "name", "")),
                "backend": "python",
                "reason": "Migration controller unavailable",
            })
        return results

    for t in all_tracks:
        tid = str(getattr(t, "id", "") or "")
        name = str(getattr(t, "name", "") or tid)
        can, reason = ctrl.can_track_use_rust(t)
        results.append({
            "track_id": tid,
            "name": name,
            "backend": "rust" if can else "python",
            "reason": reason,
        })

    return results


# ---------------------------------------------------------------------------
# Hybrid Engine
# ---------------------------------------------------------------------------

class RustHybridEngine:
    """Mixed Rust+Python audio rendering with automatic track assignment.

    Manages the audio engine mode and orchestrates the transition
    between Python-only, Hybrid, and Full Rust modes.
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
        self._mode = _load_mode()
        self._active = False
        self._takeover = None  # lazy init RustAudioTakeover
        self._track_assignments: List[Dict[str, Any]] = []

    @property
    def mode(self) -> EngineMode:
        return self._mode

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def track_assignments(self) -> List[Dict[str, Any]]:
        """Current track → backend assignments."""
        return list(self._track_assignments)

    def set_mode(self, mode: EngineMode, persist: bool = True) -> None:
        """Set the engine mode.

        Does NOT activate — call activate() separately.
        """
        self._mode = mode
        if persist:
            _save_mode(mode)
        _log.info("Engine mode set to: %s", mode.value)

    def _get_takeover(self):
        """Lazy-init RustAudioTakeover."""
        if self._takeover is None:
            try:
                from pydaw.services.rust_audio_takeover import (
                    RustAudioTakeover,
                )
                self._takeover = RustAudioTakeover(
                    audio_engine=self._audio_engine,
                    bridge=self._bridge,
                    project_service=self._project_svc,
                )
            except ImportError:
                _log.debug("rust_audio_takeover not available")
        return self._takeover

    @property
    def _project(self):
        try:
            ctx = getattr(self._project_svc, "ctx", None)
            if ctx:
                return getattr(ctx, "project", None)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Activate / Deactivate
    # ------------------------------------------------------------------

    def activate(self) -> bool:
        """Activate the current engine mode.

        PYTHON: Does nothing (Python engine is the default).
        HYBRID: Assigns tracks, starts Rust for compatible tracks.
        RUST:   Full Rust takeover (all tracks must be compatible).

        Returns True if successfully activated.
        """
        mode = self._mode

        if mode == EngineMode.PYTHON:
            self._active = True
            self._track_assignments = []
            _log.info("Engine mode: Python (all tracks in Python)")
            return True

        # For HYBRID and RUST: check track assignments
        project = self._project
        if project is None:
            _log.warning("No project loaded — staying in Python mode")
            return False

        assignments = assign_tracks(project)
        self._track_assignments = assignments

        rust_count = sum(1 for a in assignments if a["backend"] == "rust")
        total = len(assignments)
        python_count = total - rust_count

        _log.info("Track assignment: %d/%d Rust, %d/%d Python",
                   rust_count, total, python_count, total)

        if mode == EngineMode.RUST and python_count > 0:
            # Cannot do full Rust — some tracks need Python
            _log.warning(
                "Full Rust mode requested but %d tracks need Python — "
                "downgrading to Hybrid", python_count)
            self._mode = EngineMode.HYBRID
            mode = EngineMode.HYBRID
            # Don't persist the downgrade — user chose RUST

        if mode == EngineMode.HYBRID and rust_count == 0:
            # No Rust tracks → pure Python
            _log.info("No Rust-compatible tracks — using Python mode")
            self._active = True
            return True

        # Start Rust engine via takeover
        takeover = self._get_takeover()
        if takeover is None:
            _log.error("RustAudioTakeover not available")
            return False

        if mode == EngineMode.RUST:
            # Full Rust: standard takeover
            ok = takeover.activate()
            if not ok:
                _log.error("Full Rust activation failed")
                return False
            self._active = True
            return True

        # HYBRID: Start Rust engine alongside Python
        # Rust renders compatible tracks, Python renders the rest
        # Both outputs combine at the master bus
        ok = takeover.activate()
        if not ok:
            _log.warning("Rust engine start failed in Hybrid — "
                         "falling back to pure Python")
            self._active = True
            return True  # Python still works

        self._active = True
        _log.info("Hybrid mode active: %d Rust + %d Python tracks",
                   rust_count, python_count)
        return True

    def deactivate(self) -> None:
        """Deactivate Rust engine, return to pure Python."""
        takeover = self._get_takeover()
        if takeover is not None:
            takeover.deactivate()
        self._active = False
        self._track_assignments = []
        _log.info("Engine deactivated → Python mode")

    # ------------------------------------------------------------------
    # Track Badge (UI: "R" or "P" per track)
    # ------------------------------------------------------------------

    def get_track_backend(self, track_id: str) -> str:
        """Get the backend for a specific track.

        Returns "rust", "python", or "unknown".
        """
        for a in self._track_assignments:
            if a.get("track_id") == track_id:
                return str(a.get("backend", "unknown"))
        # Default based on mode
        if self._mode == EngineMode.RUST:
            return "rust"
        elif self._mode == EngineMode.PYTHON:
            return "python"
        return "unknown"

    def get_track_badge(self, track_id: str) -> str:
        """Get display badge for track header.

        Returns "R" (Rust), "P" (Python), or "" (no badge).
        """
        if self._mode == EngineMode.PYTHON:
            return ""  # No badges in pure Python mode
        backend = self.get_track_backend(track_id)
        if backend == "rust":
            return "R"
        elif backend == "python":
            return "P"
        return ""

    # ------------------------------------------------------------------
    # A/B Test (RA5)
    # ------------------------------------------------------------------

    def run_ab_test(self, duration_seconds: float = 10.0) -> Dict[str, Any]:
        """Run A/B comparison: Python bounce vs Rust bounce.

        Returns dict with max_deviation_db, performance stats, pass/fail.
        This is a placeholder — actual A/B test requires bounce infrastructure.
        """
        report: Dict[str, Any] = {
            "python_render_time_ms": 0.0,
            "rust_render_time_ms": 0.0,
            "max_deviation_db": 0.0,
            "pass": False,
            "note": "A/B test requires bounce rendering infrastructure",
        }

        try:
            from pydaw.services.engine_migration import (
                EngineMigrationController,
            )
            ctrl = EngineMigrationController()
            project = self._project
            if project:
                tracks = list(getattr(project, "tracks", []) or [])
                migration_report = ctrl.get_migration_report(tracks)
                report["migration"] = migration_report
                report["note"] = (
                    f"{migration_report.get('rust_count', 0)}/"
                    f"{migration_report.get('total', 0)} tracks Rust-ready"
                )
        except Exception as e:
            report["note"] = f"Migration report failed: {e}"

        return report

    # ------------------------------------------------------------------
    # RA4 v0.0.20.709: Hybrid PDC (Latency Compensation)
    # ------------------------------------------------------------------

    def compute_hybrid_pdc(self) -> Dict[str, int]:
        """Compute per-track latency compensation for Hybrid mode.

        In Hybrid mode, Rust and Python paths may have different latencies:
        - Rust path: IPC overhead (~1 buffer cycle, e.g. 256 samples @ 48kHz)
        - Python path: direct in-process (0 extra latency) OR sandbox (+1 buffer)

        Returns dict: {track_id: compensation_samples} where the value
        is the number of samples to delay that track's output to align
        with the slowest path.
        """
        compensation: Dict[str, int] = {}

        if not self._track_assignments:
            return compensation

        # Estimate per-track latencies
        rust_latency = 0
        python_latency = 0

        # Rust IPC adds ~1 buffer cycle of latency
        try:
            from pydaw.core.settings_store import get_value
            from pydaw.core.settings import SettingsKeys
            bs = int(get_value(SettingsKeys.buffer_size, 512) or 512)
            rust_latency = bs  # 1 buffer cycle IPC overhead
        except Exception:
            rust_latency = 512

        # Python sandbox also adds ~1 buffer cycle
        try:
            from pydaw.core.settings_store import get_value
            from pydaw.core.settings import SettingsKeys
            sandbox_on = False
            raw = get_value(SettingsKeys.audio_plugin_sandbox_enabled, None)
            if isinstance(raw, str):
                sandbox_on = raw.lower() in ("true", "1", "yes", "on")
            elif raw is not None:
                sandbox_on = bool(raw)
            if sandbox_on:
                python_latency = bs  # sandbox also adds 1 buffer
        except Exception:
            pass

        # Find max latency across all tracks
        max_latency = max(rust_latency, python_latency)

        # Compute per-track compensation (delay shorter paths to match longest)
        for a in self._track_assignments:
            tid = str(a.get("track_id", ""))
            backend = str(a.get("backend", "python"))
            if backend == "rust":
                track_latency = rust_latency
            else:
                track_latency = python_latency
            compensation[tid] = max_latency - track_latency

        _log.debug("Hybrid PDC: rust=%d, python=%d, max=%d, compensations=%s",
                    rust_latency, python_latency, max_latency, compensation)
        return compensation

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive engine status."""
        takeover = self._get_takeover()
        takeover_status = (
            takeover.get_status() if takeover else {"rust_active": False}
        )

        rust_tracks = sum(
            1 for a in self._track_assignments if a.get("backend") == "rust")
        python_tracks = sum(
            1 for a in self._track_assignments if a.get("backend") == "python")

        return {
            "mode": self._mode.value,
            "active": self._active,
            "rust_tracks": rust_tracks,
            "python_tracks": python_tracks,
            "total_tracks": rust_tracks + python_tracks,
            "takeover": takeover_status,
            "pdc": self.compute_hybrid_pdc() if self._active else {},
        }
