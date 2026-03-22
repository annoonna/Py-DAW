"""Sampler Registry (v0.0.20.1).

Global sampler instance manager for per-track audio instruments.

Design:
- One sampler engine per instrument track (no duplicates)
- note_preview signal → registry → correct track's sampler engine
- Piano Roll + Notation editor both route through this registry
- Thread safety: GUI thread for registration, audio thread reads via GIL-safe dict
"""
from __future__ import annotations

from typing import Dict, Optional, Any

from PySide6.QtCore import QObject, Signal


class SamplerRegistry(QObject):
    """Global registry for per-track sampler instances.

    Ensures:
    - No duplicate samplers per track
    - Unified note triggering from any editor
    - Clean lifecycle management (register/unregister)
    """

    sampler_registered = Signal(str)    # track_id
    sampler_unregistered = Signal(str)  # track_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engines: Dict[str, Any] = {}   # track_id → sampler engine
        self._widgets: Dict[str, Any] = {}   # track_id → sampler widget

    def register(self, track_id: str, engine: Any,
                 widget: Any = None) -> None:
        """Register a sampler engine for a track."""
        track_id = str(track_id)
        self._engines[track_id] = engine
        if widget is not None:
            self._widgets[track_id] = widget
        self.sampler_registered.emit(track_id)

    def unregister(self, track_id: str) -> None:
        """Remove sampler for a track (on track deletion)."""
        track_id = str(track_id)
        engine = self._engines.pop(track_id, None)
        self._widgets.pop(track_id, None)
        if engine is not None:
            try:
                if hasattr(engine, "shutdown"):
                    engine.shutdown()
            except Exception:
                pass
        self.sampler_unregistered.emit(track_id)

    def get_engine(self, track_id: str) -> Optional[Any]:
        """Get sampler engine for track (audio-thread safe via GIL)."""
        return self._engines.get(str(track_id))

    def get_widget(self, track_id: str) -> Optional[Any]:
        """Get sampler widget for track (GUI thread only)."""
        return self._widgets.get(str(track_id))

    def has_sampler(self, track_id: str) -> bool:
        return str(track_id) in self._engines

    def trigger_note(self, track_id: str, pitch: int,
                     velocity: int = 100,
                     duration_ms: int = 140) -> bool:
        """Trigger a note on the track's sampler.

        Called from Piano Roll, Notation editor, or MIDI input.
        Returns True if a sampler was found and triggered.
        """
        engine = self._engines.get(str(track_id))
        if engine is None:
            return False
        try:
            if hasattr(engine, "trigger_note"):
                engine.trigger_note(int(pitch), int(velocity),
                                    int(duration_ms))
                return True
            if hasattr(engine, "note_on_preview"):
                engine.note_on_preview(int(pitch), int(velocity),
                                       int(duration_ms))
                return True
        except Exception:
            pass
        return False

    def note_on(self, track_id: str, pitch: int, velocity: int = 100, *, pitch_offset_semitones: float = 0.0, micropitch_curve: list = None, note_duration_samples: int = 0) -> bool:
        """Live-monitoring sustain: start note until note_off.

        Returns True if a sampler exists for the track and accepted the note.
        """
        try:
            engine = self._engines.get(str(track_id))
            if engine is None:
                return False
            if hasattr(engine, "note_on"):
                try:
                    return bool(engine.note_on(int(pitch), int(velocity), pitch_offset_semitones=float(pitch_offset_semitones or 0.0), micropitch_curve=micropitch_curve or [], note_duration_samples=int(note_duration_samples or 0)))
                except TypeError:
                    # Fallback for engines that don't support v2 kwargs yet
                    try:
                        return bool(engine.note_on(int(pitch), int(velocity), pitch_offset_semitones=float(pitch_offset_semitones or 0.0)))
                    except TypeError:
                        return bool(engine.note_on(int(pitch), int(velocity)))
            # Fallback: one-shot trigger
            if hasattr(engine, "trigger_note"):
                engine.trigger_note(int(pitch), int(velocity), None)
                return True
        except Exception:
            return False
        return False

    def note_off(self, track_id: str, pitch: int = -1) -> None:
        """Live-monitoring sustain: release/stop note.

        v0.0.20.380: If pitch >= 0, sends pitch to engine for polyphonic release.
        If pitch < 0 (default), sends generic note_off (legacy mono behaviour).
        """
        try:
            engine = self._engines.get(str(track_id))
            if engine is None:
                return
            if hasattr(engine, "note_off"):
                if pitch >= 0:
                    # Try polyphonic note_off(pitch=...) first
                    try:
                        engine.note_off(pitch=int(pitch))
                        return
                    except TypeError:
                        pass
                # Fallback: no pitch argument (mono engines)
                engine.note_off()
            elif hasattr(engine, "all_notes_off"):
                engine.all_notes_off()
        except Exception:
            pass

    def all_notes_off(self, track_id: str | None = None) -> None:
        """Panic: stop one or all tracks."""
        try:
            if track_id is None:
                for eng in list(self._engines.values()):
                    try:
                        eng.all_notes_off()
                    except Exception:
                        pass
            else:
                eng = self._engines.get(str(track_id))
                if eng:
                    eng.all_notes_off()
        except Exception:
            pass


    def stop_all(self, track_id: str) -> None:
        """Stop all playing notes on a track's sampler."""
        engine = self._engines.get(str(track_id))
        if engine is None:
            return
        try:
            if hasattr(engine, "stop_all"):
                engine.stop_all()
            elif hasattr(engine, "all_notes_off"):
                engine.all_notes_off()
        except Exception:
            pass

    def all_track_ids(self) -> list[str]:
        return list(self._engines.keys())

    def cleanup(self) -> None:
        """Shutdown all engines on app exit."""
        for tid in list(self._engines.keys()):
            self.unregister(tid)


# Module-level singleton
_registry: Optional[SamplerRegistry] = None


def get_sampler_registry() -> SamplerRegistry:
    """Get or create the global sampler registry."""
    global _registry
    if _registry is None:
        _registry = SamplerRegistry()
    return _registry
