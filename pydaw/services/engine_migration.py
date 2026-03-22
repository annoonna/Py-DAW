"""EngineMigrationController — Schrittweise Migration Python→Rust.

v0.0.20.662 — Phase 1D

Manages the gradual migration from the Python audio engine to the Rust engine.
Each subsystem (audio playback, MIDI dispatch, plugin hosting) can be toggled
independently, allowing a safe step-by-step transition.

Migration order (as designed in ROADMAP):
    1. Audio Playback  — Rust renders arrangement audio, Python still handles MIDI + plugins
    2. MIDI Dispatch    — Rust handles MIDI routing to instruments
    3. Plugin Hosting   — Rust hosts VST3/CLAP/LV2 plugins natively

Architecture:
    ┌──────────────────────────────────────────────────────┐
    │  EngineMigrationController (singleton)               │
    │                                                      │
    │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
    │  │ audio_play   │  │ midi_dispatch│  │ plugin_host  │ │
    │  │ ☑ Python     │  │ ☑ Python     │  │ ☑ Python     │ │
    │  │ ☐ Rust       │  │ ☐ Rust       │  │ ☐ Rust       │ │
    │  └─────────────┘  └─────────────┘  └──────────────┘ │
    │                                                      │
    │  State saved to QSettings → survives restarts        │
    │  Hot-swap: switch subsystems without restarting DAW  │
    └──────────────────────────────────────────────────────┘

Usage:
    ctrl = EngineMigrationController.instance()
    ctrl.set_subsystem("audio_playback", "rust")
    ctrl.set_subsystem("midi_dispatch", "python")
    if ctrl.should_use_rust("audio_playback"):
        # delegate to RustEngineBridge
    else:
        # use Python engine
"""

from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from PyQt6.QtCore import QObject, pyqtSignal, QSettings
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class EngineBackend(str, Enum):
    """Which engine handles a given subsystem."""
    PYTHON = "python"
    RUST = "rust"


class MigrationSubsystem(str, Enum):
    """The three migrateable subsystems."""
    AUDIO_PLAYBACK = "audio_playback"
    MIDI_DISPATCH = "midi_dispatch"
    PLUGIN_HOSTING = "plugin_hosting"


class MigrationStatus(str, Enum):
    """Status of a subsystem migration."""
    IDLE = "idle"              # Not started
    SWITCHING = "switching"    # In progress (brief transition)
    ACTIVE = "active"          # Running on target backend
    FAILED = "failed"          # Switch failed, rolled back
    ROLLBACK = "rollback"      # Rolling back to previous backend


@dataclass
class SubsystemState:
    """State of a single migrateable subsystem."""
    subsystem: MigrationSubsystem
    backend: EngineBackend = EngineBackend.PYTHON
    status: MigrationStatus = MigrationStatus.ACTIVE
    last_switch_time: float = 0.0
    error_message: str = ""
    switch_count: int = 0
    # Performance metrics (filled by benchmark)
    python_avg_render_us: float = 0.0
    rust_avg_render_us: float = 0.0


@dataclass
class MigrationSnapshot:
    """Complete migration state for serialization."""
    subsystems: Dict[str, str] = field(default_factory=dict)
    rust_as_default: bool = False
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Settings keys
# ---------------------------------------------------------------------------

_SETTINGS_PREFIX = "engine_migration/"
_KEY_AUDIO = _SETTINGS_PREFIX + "audio_playback"
_KEY_MIDI = _SETTINGS_PREFIX + "midi_dispatch"
_KEY_PLUGIN = _SETTINGS_PREFIX + "plugin_hosting"
_KEY_RUST_DEFAULT = _SETTINGS_PREFIX + "rust_as_default"


# ---------------------------------------------------------------------------
# EngineMigrationController
# ---------------------------------------------------------------------------

if _QT_AVAILABLE:
    _BASE = QObject
else:
    _BASE = object


class EngineMigrationController(_BASE):
    """Singleton controller for step-by-step Python→Rust engine migration.

    Thread safety:
        All public methods are thread-safe (protected by _lock).
        Signal emissions happen on the calling thread — connect with Qt::QueuedConnection
        if calling from non-GUI threads.
    """

    # Qt signals
    if _QT_AVAILABLE:
        subsystem_changed = pyqtSignal(str, str, str)   # subsystem, new_backend, status
        migration_error = pyqtSignal(str, str)           # subsystem, error_message
        rust_default_changed = pyqtSignal(bool)          # is_default

    # Singleton
    _instance: Optional[EngineMigrationController] = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls) -> EngineMigrationController:
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        if _QT_AVAILABLE:
            super().__init__()

        self._lock = threading.RLock()

        # Per-subsystem state
        self._states: Dict[MigrationSubsystem, SubsystemState] = {
            MigrationSubsystem.AUDIO_PLAYBACK: SubsystemState(
                subsystem=MigrationSubsystem.AUDIO_PLAYBACK,
            ),
            MigrationSubsystem.MIDI_DISPATCH: SubsystemState(
                subsystem=MigrationSubsystem.MIDI_DISPATCH,
            ),
            MigrationSubsystem.PLUGIN_HOSTING: SubsystemState(
                subsystem=MigrationSubsystem.PLUGIN_HOSTING,
            ),
        }

        # Whether Rust is the default for new projects
        self._rust_as_default = False

        # Callbacks for pre/post switch hooks
        self._pre_switch_hooks: Dict[MigrationSubsystem, List[Callable]] = {
            s: [] for s in MigrationSubsystem
        }
        self._post_switch_hooks: Dict[MigrationSubsystem, List[Callable]] = {
            s: [] for s in MigrationSubsystem
        }

        # Validation callbacks: return True if Rust subsystem is functional
        self._validators: Dict[MigrationSubsystem, Optional[Callable]] = {
            s: None for s in MigrationSubsystem
        }

        # Load saved state
        self._load_settings()

    # --- Public API: Query ---------------------------------------------------

    def should_use_rust(self, subsystem: str) -> bool:
        """Check if a subsystem should use the Rust engine.

        v0.0.20.700: Toggle ist ON by default wenn Binary existiert.
        ABER: audio_playback bleibt bei Python bis die IPC-Bridge
        Rust→Python Instrumente rendern kann. Alle anderen Subsysteme
        (midi_dispatch, plugin_hosting) können Rust nutzen.

        Der R: ON Status zeigt: Rust-Engine ist gebaut und bereit.
        Audio-Rendering bleibt in Python bis Plugin Sandbox (P1-P6) fertig.
        """
        import os

        env = os.environ.get("USE_RUST_ENGINE", "").lower()

        # Notfall-Override
        if env in ("0", "false", "no"):
            return False

        # AUDIO PLAYBACK: Bleibt IMMER bei Python
        # Rust hat die DSP-Module aber kann Python-Instrumente noch nicht
        # rendern (keine IPC Audio Bridge aktiv). Einschalten würde
        # stummes Audio und blockierten Stop-Button verursachen.
        if subsystem == "audio_playback":
            return False

        # Alle anderen Subsysteme: check Binary + Settings
        if not self._is_rust_available():
            return False

        if env in ("1", "true", "yes"):
            return True

        # QSettings Toggle
        try:
            from pydaw.core.settings import SettingsKeys, get_value
            raw = get_value(SettingsKeys.audio_rust_engine_enabled, None)
            if raw is not None:
                if isinstance(raw, str):
                    return raw.lower() in ("true", "1", "yes", "on")
                return bool(raw)
        except Exception:
            pass

        # Default: True wenn Binary da (R1–R13 komplett)
        return True

    # --- R13B: Per-track Rust capability check (v0.0.20.694) ----------------

    # Instrument types with Rust implementations
    _RUST_INSTRUMENTS = frozenset({
        'pro_sampler', 'chrono.pro_audio_sampler', 'sampler',
        'multi_sample', 'multisample', 'chrono.multi_sample',
        'drum_machine', 'chrono.pro_drum_machine',
        'aeterna', 'chrono.aeterna',
        'fusion', 'chrono.fusion',
        'bach_orgel', 'chrono.bach_orgel',
        'sf2',
    })

    # Built-in FX types with Rust implementations
    _RUST_FX = frozenset({
        'parametric_eq', 'compressor', 'limiter', 'reverb', 'delay',
        'chorus', 'phaser', 'flanger', 'distortion', 'tremolo',
        'gate', 'deesser', 'stereo_widener', 'utility', 'spectrum_analyzer',
    })

    def can_track_use_rust(self, track) -> tuple[bool, str]:
        """Check if a specific track can be rendered by the Rust engine.

        Returns (can_use_rust, reason_string).
        """
        try:
            inst_type = str(getattr(track, 'plugin_type', '') or '')
            if inst_type and inst_type not in self._RUST_INSTRUMENTS:
                return False, f"Instrument '{inst_type}' nicht in Rust"

            # Check FX chain
            chain = getattr(track, 'audio_fx_chain', None)
            if isinstance(chain, dict):
                for dev in (chain.get('devices') or []):
                    if not isinstance(dev, dict):
                        continue
                    pid = str(dev.get('plugin_id') or dev.get('type') or '')
                    if pid.startswith('ext.'):
                        continue  # external plugins handled by Rust plugin host
                    fx_name = pid.split('.')[-1] if '.' in pid else pid
                    if fx_name and fx_name not in self._RUST_FX:
                        return False, f"FX '{fx_name}' nicht in Rust"

            return True, "Vollständig in Rust"
        except Exception as e:
            return False, f"Fehler: {e}"

    def get_migration_report(self, tracks=None) -> dict:
        """Generate a migration readiness report for all tracks.

        Returns dict with:
          - tracks: list of {track_id, name, can_use_rust, reason, backend}
          - rust_count: how many tracks can use Rust
          - total: total track count
          - recommendation: human-readable recommendation
          - mode: "off" | "hybrid" | "full"
        """
        if tracks is None:
            tracks = []
        results = []
        rust_count = 0
        for t in tracks:
            tid = str(getattr(t, 'id', '') or '')
            name = str(getattr(t, 'name', '') or tid)
            can, reason = self.can_track_use_rust(t)
            if can:
                rust_count += 1
            results.append({
                'track_id': tid,
                'name': name,
                'can_use_rust': can,
                'reason': reason,
                'backend': 'rust' if can else 'python',
            })
        total = len(results)
        if total == 0:
            rec, mode = "Kein Track vorhanden", "off"
        elif rust_count == total:
            rec = f"Alle {total} Tracks können in Rust laufen — Full Mode empfohlen"
            mode = "full"
        elif rust_count > 0:
            rec = f"{rust_count} von {total} Tracks in Rust — Hybrid Mode empfohlen"
            mode = "hybrid"
        else:
            rec, mode = "Kein Track kann in Rust laufen", "off"
        return {
            'tracks': results,
            'rust_count': rust_count,
            'total': total,
            'recommendation': rec,
            'mode': mode,
        }

    def get_backend(self, subsystem: str) -> str:
        """Get the configured backend for a subsystem.

        Returns 'python' or 'rust'.
        """
        with self._lock:
            try:
                sub = MigrationSubsystem(subsystem)
            except ValueError:
                return "python"
            return self._states[sub].backend.value

    def get_state(self, subsystem: str) -> Optional[SubsystemState]:
        """Get the full state of a subsystem."""
        with self._lock:
            try:
                sub = MigrationSubsystem(subsystem)
            except ValueError:
                return None
            # Return a copy to prevent external mutation
            import copy
            return copy.copy(self._states[sub])

    def get_all_states(self) -> Dict[str, SubsystemState]:
        """Get states of all subsystems."""
        with self._lock:
            import copy
            return {s.value: copy.copy(self._states[s]) for s in MigrationSubsystem}

    @property
    def rust_as_default(self) -> bool:
        """Whether Rust is the default engine for new projects."""
        with self._lock:
            return self._rust_as_default

    def get_migration_summary(self) -> Dict[str, Any]:
        """Get a summary suitable for display in UI / settings dialog."""
        with self._lock:
            rust_avail = self._is_rust_available()
            return {
                "rust_available": rust_avail,
                "rust_as_default": self._rust_as_default,
                "subsystems": {
                    s.value: {
                        "backend": self._states[s].backend.value,
                        "status": self._states[s].status.value,
                        "error": self._states[s].error_message,
                        "switch_count": self._states[s].switch_count,
                        "python_avg_us": self._states[s].python_avg_render_us,
                        "rust_avg_us": self._states[s].rust_avg_render_us,
                    }
                    for s in MigrationSubsystem
                },
            }

    # --- Public API: Mutation ------------------------------------------------

    def set_subsystem(self, subsystem: str, backend: str) -> bool:
        """Switch a subsystem to a different backend.

        Args:
            subsystem: 'audio_playback', 'midi_dispatch', or 'plugin_hosting'
            backend: 'python' or 'rust'

        Returns:
            True if the switch was successful.
        """
        with self._lock:
            try:
                sub = MigrationSubsystem(subsystem)
                be = EngineBackend(backend)
            except ValueError as e:
                log.error("Invalid subsystem or backend: %s", e)
                return False

            state = self._states[sub]

            # Already on this backend?
            if state.backend == be:
                log.debug("Subsystem %s already on %s", subsystem, backend)
                return True

            # Switching to Rust requires the engine to be available
            if be == EngineBackend.RUST and not self._is_rust_available():
                msg = (
                    "Rust engine binary not found. "
                    "Build with: cd pydaw_engine && cargo build --release"
                )
                log.warning(msg)
                state.error_message = msg
                state.status = MigrationStatus.FAILED
                self._emit_error(subsystem, msg)
                return False

            # Dependency check: MIDI needs audio, plugins need MIDI
            if be == EngineBackend.RUST:
                if sub == MigrationSubsystem.MIDI_DISPATCH:
                    if self._states[MigrationSubsystem.AUDIO_PLAYBACK].backend != EngineBackend.RUST:
                        msg = "MIDI dispatch requires audio_playback to be on Rust first"
                        log.warning(msg)
                        state.error_message = msg
                        self._emit_error(subsystem, msg)
                        return False
                elif sub == MigrationSubsystem.PLUGIN_HOSTING:
                    if self._states[MigrationSubsystem.MIDI_DISPATCH].backend != EngineBackend.RUST:
                        msg = "Plugin hosting requires midi_dispatch to be on Rust first"
                        log.warning(msg)
                        state.error_message = msg
                        self._emit_error(subsystem, msg)
                        return False

            # Reverse dependency: switching back to Python cascades
            if be == EngineBackend.PYTHON:
                if sub == MigrationSubsystem.AUDIO_PLAYBACK:
                    # Must also switch MIDI and plugins back
                    self._force_subsystem(MigrationSubsystem.PLUGIN_HOSTING, EngineBackend.PYTHON)
                    self._force_subsystem(MigrationSubsystem.MIDI_DISPATCH, EngineBackend.PYTHON)
                elif sub == MigrationSubsystem.MIDI_DISPATCH:
                    self._force_subsystem(MigrationSubsystem.PLUGIN_HOSTING, EngineBackend.PYTHON)

            # Execute switch
            return self._do_switch(sub, be)

    def set_rust_as_default(self, enabled: bool):
        """Set whether Rust should be the default engine.

        Only takes effect if all three subsystems are stable on Rust.
        """
        with self._lock:
            if enabled:
                # All subsystems must be on Rust and active
                for sub in MigrationSubsystem:
                    st = self._states[sub]
                    if st.backend != EngineBackend.RUST or st.status != MigrationStatus.ACTIVE:
                        log.warning(
                            "Cannot set Rust as default: %s is %s/%s",
                            sub.value, st.backend.value, st.status.value,
                        )
                        return
            self._rust_as_default = enabled
            self._save_settings()
            if _QT_AVAILABLE:
                try:
                    self.rust_default_changed.emit(enabled)
                except Exception:
                    pass
            log.info("Rust as default: %s", enabled)

    def migrate_all_to_rust(self) -> bool:
        """Migrate all subsystems to Rust in the correct order.

        Returns True if all subsystems switched successfully.
        """
        order = [
            MigrationSubsystem.AUDIO_PLAYBACK,
            MigrationSubsystem.MIDI_DISPATCH,
            MigrationSubsystem.PLUGIN_HOSTING,
        ]
        for sub in order:
            if not self.set_subsystem(sub.value, EngineBackend.RUST.value):
                log.error("Migration stopped at %s", sub.value)
                return False
        return True

    def rollback_all_to_python(self) -> bool:
        """Roll back all subsystems to Python (safe fallback)."""
        order = [
            MigrationSubsystem.PLUGIN_HOSTING,
            MigrationSubsystem.MIDI_DISPATCH,
            MigrationSubsystem.AUDIO_PLAYBACK,
        ]
        success = True
        for sub in order:
            if not self.set_subsystem(sub.value, EngineBackend.PYTHON.value):
                log.error("Rollback failed at %s", sub.value)
                success = False
        return success

    # --- Hooks ---------------------------------------------------------------

    def register_pre_switch_hook(self, subsystem: str, callback: Callable):
        """Register a callback to be called before a subsystem switch.

        Callback signature: callback(subsystem: str, new_backend: str) -> None
        """
        with self._lock:
            try:
                sub = MigrationSubsystem(subsystem)
            except ValueError:
                return
            self._pre_switch_hooks[sub].append(callback)

    def register_post_switch_hook(self, subsystem: str, callback: Callable):
        """Register a callback after a successful subsystem switch.

        Callback signature: callback(subsystem: str, new_backend: str) -> None
        """
        with self._lock:
            try:
                sub = MigrationSubsystem(subsystem)
            except ValueError:
                return
            self._post_switch_hooks[sub].append(callback)

    def register_validator(self, subsystem: str, callback: Callable):
        """Register a validation callback for a subsystem.

        Called during switch-to-Rust to verify the engine is functional.
        Callback signature: callback() -> bool  (True = OK)
        """
        with self._lock:
            try:
                sub = MigrationSubsystem(subsystem)
            except ValueError:
                return
            self._validators[sub] = callback

    def update_performance_metrics(
        self,
        subsystem: str,
        python_avg_us: float = 0.0,
        rust_avg_us: float = 0.0,
    ):
        """Update performance metrics for a subsystem (called by benchmark)."""
        with self._lock:
            try:
                sub = MigrationSubsystem(subsystem)
            except ValueError:
                return
            if python_avg_us > 0:
                self._states[sub].python_avg_render_us = python_avg_us
            if rust_avg_us > 0:
                self._states[sub].rust_avg_render_us = rust_avg_us

    # --- Internal: Switch Execution ------------------------------------------

    def _do_switch(self, sub: MigrationSubsystem, new_be: EngineBackend) -> bool:
        """Execute the actual backend switch for a subsystem."""
        state = self._states[sub]
        old_be = state.backend

        log.info("Switching %s: %s → %s", sub.value, old_be.value, new_be.value)
        state.status = MigrationStatus.SWITCHING

        # Pre-switch hooks
        for hook in self._pre_switch_hooks[sub]:
            try:
                hook(sub.value, new_be.value)
            except Exception as e:
                log.error("Pre-switch hook error for %s: %s", sub.value, e)

        # Validate if switching to Rust
        if new_be == EngineBackend.RUST:
            validator = self._validators[sub]
            if validator is not None:
                try:
                    ok = validator()
                    if not ok:
                        msg = f"Validation failed for {sub.value} on Rust"
                        log.warning(msg)
                        state.backend = old_be
                        state.status = MigrationStatus.FAILED
                        state.error_message = msg
                        self._emit_error(sub.value, msg)
                        return False
                except Exception as e:
                    msg = f"Validation error for {sub.value}: {e}"
                    log.error(msg)
                    state.backend = old_be
                    state.status = MigrationStatus.FAILED
                    state.error_message = msg
                    self._emit_error(sub.value, msg)
                    return False

        # Apply
        state.backend = new_be
        state.status = MigrationStatus.ACTIVE
        state.error_message = ""
        state.last_switch_time = time.monotonic()
        state.switch_count += 1

        # Post-switch hooks
        for hook in self._post_switch_hooks[sub]:
            try:
                hook(sub.value, new_be.value)
            except Exception as e:
                log.error("Post-switch hook error for %s: %s", sub.value, e)

        # Save and emit
        self._save_settings()
        self._emit_changed(sub.value, new_be.value, "active")

        log.info("Switched %s to %s (count: %d)", sub.value, new_be.value, state.switch_count)
        return True

    def _force_subsystem(self, sub: MigrationSubsystem, be: EngineBackend):
        """Force a subsystem to a backend without dependency checks (cascade)."""
        state = self._states[sub]
        if state.backend == be:
            return
        old = state.backend
        state.backend = be
        state.status = MigrationStatus.ACTIVE
        state.error_message = ""
        state.last_switch_time = time.monotonic()
        state.switch_count += 1
        self._emit_changed(sub.value, be.value, "active")
        log.info("Force-switched %s: %s → %s (cascade)", sub.value, old.value, be.value)

    # --- Internal: Rust availability -----------------------------------------

    @staticmethod
    def _is_rust_available() -> bool:
        """Check if the Rust engine binary is available."""
        try:
            from pydaw.services.rust_engine_bridge import RustEngineBridge
            return RustEngineBridge.is_available()
        except Exception:
            return False

    # --- Internal: Settings persistence --------------------------------------

    def _load_settings(self):
        """Load migration state from QSettings."""
        if not _QT_AVAILABLE:
            return
        try:
            s = QSettings()
            audio_be = s.value(_KEY_AUDIO, "python")
            midi_be = s.value(_KEY_MIDI, "python")
            plugin_be = s.value(_KEY_PLUGIN, "python")
            rust_default = s.value(_KEY_RUST_DEFAULT, False)
            if isinstance(rust_default, str):
                rust_default = rust_default.lower() in ("true", "1", "yes")

            # Only load Rust if the binary is actually available
            if self._is_rust_available():
                try:
                    self._states[MigrationSubsystem.AUDIO_PLAYBACK].backend = EngineBackend(audio_be)
                except ValueError:
                    pass
                try:
                    self._states[MigrationSubsystem.MIDI_DISPATCH].backend = EngineBackend(midi_be)
                except ValueError:
                    pass
                try:
                    self._states[MigrationSubsystem.PLUGIN_HOSTING].backend = EngineBackend(plugin_be)
                except ValueError:
                    pass
                self._rust_as_default = bool(rust_default)
            else:
                # Rust not available — force everything to Python
                for sub in MigrationSubsystem:
                    self._states[sub].backend = EngineBackend.PYTHON
                self._rust_as_default = False
        except Exception as e:
            log.debug("Could not load migration settings: %s", e)

    def _save_settings(self):
        """Save migration state to QSettings."""
        if not _QT_AVAILABLE:
            return
        try:
            s = QSettings()
            s.setValue(_KEY_AUDIO, self._states[MigrationSubsystem.AUDIO_PLAYBACK].backend.value)
            s.setValue(_KEY_MIDI, self._states[MigrationSubsystem.MIDI_DISPATCH].backend.value)
            s.setValue(_KEY_PLUGIN, self._states[MigrationSubsystem.PLUGIN_HOSTING].backend.value)
            s.setValue(_KEY_RUST_DEFAULT, self._rust_as_default)
        except Exception as e:
            log.debug("Could not save migration settings: %s", e)

    # --- Internal: Signal emission -------------------------------------------

    def _emit_changed(self, subsystem: str, backend: str, status: str):
        """Emit subsystem_changed signal."""
        if _QT_AVAILABLE:
            try:
                self.subsystem_changed.emit(subsystem, backend, status)
            except Exception:
                pass

    def _emit_error(self, subsystem: str, message: str):
        """Emit migration_error signal."""
        if _QT_AVAILABLE:
            try:
                self.migration_error.emit(subsystem, message)
            except Exception:
                pass
