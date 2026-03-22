# -*- coding: utf-8 -*-
"""MIDI FX Preset System (AP6 Phase 6A).

v0.0.20.644: Save/Load/Browse presets for Note-FX chains.

Presets are JSON files stored in:
- Factory presets: bundled with the app (read-only)
- User presets: PROJECT_DIR/presets/midi_fx/ (per-project)
- Global presets: ~/.config/pydaw/presets/midi_fx/ (shared)

Each preset file:
{
    "name": "Epic Arp",
    "category": "Arpeggiator",
    "author": "ChronoScaleStudio",
    "description": "Rising arp with 4 octaves",
    "devices": [
        {"plugin_id": "chrono.note_fx.arp", "enabled": true, "params": {...}},
        ...
    ]
}
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Factory presets (built-in, always available)
# ---------------------------------------------------------------------------

_FACTORY_PRESETS: List[Dict[str, Any]] = [
    {
        "name": "Simple Arp Up",
        "category": "Arpeggiator",
        "author": "ChronoScaleStudio",
        "description": "Basic upward arpeggiator, 1/8 notes",
        "devices": [
            {"plugin_id": "chrono.note_fx.arp", "enabled": True,
             "params": {"step_beats": 0.5, "mode": "up", "octaves": 1, "gate": 0.9}},
        ],
    },
    {
        "name": "Arp Up/Down 2 Oct",
        "category": "Arpeggiator",
        "author": "ChronoScaleStudio",
        "description": "Up/Down arpeggiator spanning 2 octaves",
        "devices": [
            {"plugin_id": "chrono.note_fx.arp", "enabled": True,
             "params": {"step_beats": 0.25, "mode": "up/down", "octaves": 2, "gate": 0.8}},
        ],
    },
    {
        "name": "Chord Stacker Maj7",
        "category": "Chord",
        "author": "ChronoScaleStudio",
        "description": "Adds maj7 chord voicing to every note",
        "devices": [
            {"plugin_id": "chrono.note_fx.chord", "enabled": True,
             "params": {"chord": "maj7", "voicing": "close", "spread": 0}},
        ],
    },
    {
        "name": "Drop-2 Voicing min7",
        "category": "Chord",
        "author": "ChronoScaleStudio",
        "description": "Minor 7th with drop-2 voicing for jazz",
        "devices": [
            {"plugin_id": "chrono.note_fx.chord", "enabled": True,
             "params": {"chord": "min7", "voicing": "drop2", "spread": 0}},
        ],
    },
    {
        "name": "Humanize Light",
        "category": "Humanize",
        "author": "ChronoScaleStudio",
        "description": "Subtle timing and velocity variation",
        "devices": [
            {"plugin_id": "chrono.note_fx.random", "enabled": True,
             "params": {"pitch_range": 0, "vel_range": 15, "prob": 1.0,
                        "timing_range": 0.02, "length_range": 0.1}},
        ],
    },
    {
        "name": "Humanize Heavy",
        "category": "Humanize",
        "author": "ChronoScaleStudio",
        "description": "Strong timing and velocity randomization",
        "devices": [
            {"plugin_id": "chrono.note_fx.random", "enabled": True,
             "params": {"pitch_range": 0, "vel_range": 30, "prob": 1.0,
                        "timing_range": 0.05, "length_range": 0.2}},
        ],
    },
    {
        "name": "Echo Octave Up",
        "category": "Echo",
        "author": "ChronoScaleStudio",
        "description": "3 echoes going up by octaves, decaying velocity",
        "devices": [
            {"plugin_id": "chrono.note_fx.note_echo", "enabled": True,
             "params": {"delay_beats": 0.5, "repeats": 3, "feedback": 0.6,
                        "transpose_per_repeat": 12}},
        ],
    },
    {
        "name": "Delay Shimmer",
        "category": "Echo",
        "author": "ChronoScaleStudio",
        "description": "Fast echoes with +7 semitone shimmer",
        "devices": [
            {"plugin_id": "chrono.note_fx.note_echo", "enabled": True,
             "params": {"delay_beats": 0.25, "repeats": 5, "feedback": 0.5,
                        "transpose_per_repeat": 7}},
        ],
    },
    {
        "name": "Velocity Compressor",
        "category": "Dynamics",
        "author": "ChronoScaleStudio",
        "description": "Compress velocity range for more even dynamics",
        "devices": [
            {"plugin_id": "chrono.note_fx.velocity_curve", "enabled": True,
             "params": {"type": "compress", "amount": 0.5, "min": 40, "max": 120}},
        ],
    },
    {
        "name": "Velocity Limiter Soft",
        "category": "Dynamics",
        "author": "ChronoScaleStudio",
        "description": "Limit velocity to 40-100 range",
        "devices": [
            {"plugin_id": "chrono.note_fx.velocity_curve", "enabled": True,
             "params": {"type": "limit", "amount": 0.0, "min": 40, "max": 100}},
        ],
    },
    {
        "name": "Major Scale Force",
        "category": "Scale",
        "author": "ChronoScaleStudio",
        "description": "Snap all notes to C Major scale",
        "devices": [
            {"plugin_id": "chrono.note_fx.scale_snap", "enabled": True,
             "params": {"root": 0, "scale": "major", "mode": "nearest"}},
        ],
    },
    {
        "name": "Pentatonic Filter",
        "category": "Scale",
        "author": "ChronoScaleStudio",
        "description": "Force notes to pentatonic scale",
        "devices": [
            {"plugin_id": "chrono.note_fx.scale_snap", "enabled": True,
             "params": {"root": 0, "scale": "pentatonic", "mode": "nearest"}},
        ],
    },
    {
        "name": "Arp + Chord + Echo",
        "category": "Combo",
        "author": "ChronoScaleStudio",
        "description": "Full chain: chord stacking, arpeggiation, echo tail",
        "devices": [
            {"plugin_id": "chrono.note_fx.chord", "enabled": True,
             "params": {"chord": "min7", "voicing": "close", "spread": 0}},
            {"plugin_id": "chrono.note_fx.arp", "enabled": True,
             "params": {"step_beats": 0.25, "mode": "up", "octaves": 1, "gate": 0.7}},
            {"plugin_id": "chrono.note_fx.note_echo", "enabled": True,
             "params": {"delay_beats": 0.5, "repeats": 2, "feedback": 0.4,
                        "transpose_per_repeat": 0}},
        ],
    },
]


# ---------------------------------------------------------------------------
# Preset Manager
# ---------------------------------------------------------------------------

class MidiFxPresetManager:
    """Manages MIDI FX preset save/load/browse."""

    def __init__(self, project_dir: Optional[str] = None):
        self._project_dir = project_dir
        self._global_dir = self._get_global_preset_dir()

    @staticmethod
    def _get_global_preset_dir() -> Path:
        """~/.config/pydaw/presets/midi_fx/"""
        home = Path.home()
        d = home / ".config" / "pydaw" / "presets" / "midi_fx"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d

    def _get_project_preset_dir(self) -> Optional[Path]:
        if not self._project_dir:
            return None
        d = Path(self._project_dir) / "presets" / "midi_fx"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d

    def get_factory_presets(self) -> List[Dict[str, Any]]:
        """Return all built-in factory presets."""
        return list(_FACTORY_PRESETS)

    def get_user_presets(self) -> List[Dict[str, Any]]:
        """Return all user presets (global + project)."""
        presets = []
        # Global
        presets.extend(self._load_presets_from_dir(self._global_dir, source="global"))
        # Project
        pd = self._get_project_preset_dir()
        if pd:
            presets.extend(self._load_presets_from_dir(pd, source="project"))
        return presets

    def get_all_presets(self) -> List[Dict[str, Any]]:
        """Return factory + user presets."""
        return self.get_factory_presets() + self.get_user_presets()

    def get_categories(self) -> List[str]:
        """Return sorted list of all unique categories."""
        cats = set()
        for p in self.get_all_presets():
            cat = p.get("category", "")
            if cat:
                cats.add(cat)
        return sorted(cats)

    def save_preset(self, name: str, category: str, devices: list,
                    description: str = "", project_local: bool = False) -> bool:
        """Save a preset to disk.

        Args:
            name: Preset display name
            category: Category string
            devices: List of device dicts (same format as Track.note_fx_chain["devices"])
            description: Optional description
            project_local: If True, save to project dir; else global

        Returns:
            True on success
        """
        preset = {
            "name": name,
            "category": category,
            "author": "User",
            "description": description,
            "devices": devices,
        }
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()
        if not safe_name:
            safe_name = "preset"
        filename = f"{safe_name}.json"

        target_dir = self._get_project_preset_dir() if project_local else self._global_dir
        if target_dir is None:
            target_dir = self._global_dir

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            filepath = target_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(preset, f, indent=2, ensure_ascii=False)
            _log.info("Saved MIDI FX preset: %s → %s", name, filepath)
            return True
        except Exception as e:
            _log.error("Failed to save MIDI FX preset %s: %s", name, e)
            return False

    def delete_preset(self, name: str, project_local: bool = False) -> bool:
        """Delete a user preset by name."""
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()
        filename = f"{safe_name}.json"
        target_dir = self._get_project_preset_dir() if project_local else self._global_dir
        if target_dir is None:
            return False
        try:
            filepath = target_dir / filename
            if filepath.exists():
                filepath.unlink()
                _log.info("Deleted MIDI FX preset: %s", filepath)
                return True
        except Exception as e:
            _log.error("Failed to delete MIDI FX preset %s: %s", name, e)
        return False

    @staticmethod
    def _load_presets_from_dir(directory: Path, source: str = "") -> List[Dict[str, Any]]:
        """Load all .json preset files from a directory."""
        presets = []
        if not directory or not directory.is_dir():
            return presets
        try:
            for fp in sorted(directory.glob("*.json")):
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "devices" in data:
                        data["_source"] = source
                        data["_filepath"] = str(fp)
                        presets.append(data)
                except Exception as e:
                    _log.warning("Skipping invalid preset %s: %s", fp, e)
        except Exception:
            pass
        return presets

    @staticmethod
    def apply_preset_to_chain(chain: dict, preset: Dict[str, Any]) -> dict:
        """Replace the devices in a note_fx_chain with those from a preset.

        Args:
            chain: Existing Track.note_fx_chain dict
            preset: Preset dict with "devices" key

        Returns:
            Updated chain dict (new copy, does not mutate original)
        """
        import copy
        new_chain = copy.deepcopy(chain) if chain else {"devices": []}
        devices = preset.get("devices", [])
        if isinstance(devices, list):
            new_chain["devices"] = copy.deepcopy(devices)
        return new_chain
