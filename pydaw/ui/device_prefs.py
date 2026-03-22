# -*- coding: utf-8 -*-
"""Device Favorites / Recents (UI-only, safe).

We keep a tiny per-user JSON in:
    ~/.cache/ChronoScaleStudio/device_prefs.json

This is intentionally NOT stored in the project file (project stays portable).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


def _prefs_path() -> Path:
    base = Path(os.path.expanduser("~/.cache")) / "ChronoScaleStudio"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        return Path("device_prefs.json")
    return base / "device_prefs.json"


@dataclass
class DeviceEntry:
    plugin_id: str
    name: str


@dataclass
class DevicePrefs:
    favorites: Dict[str, List[DeviceEntry]] = field(default_factory=dict)
    recents: Dict[str, List[DeviceEntry]] = field(default_factory=dict)
    max_recents: int = 12

    @classmethod
    def load(cls) -> "DevicePrefs":
        path = _prefs_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        def _load_bucket(key: str) -> Dict[str, List[DeviceEntry]]:
            out: Dict[str, List[DeviceEntry]] = {}
            raw = data.get(key) or {}
            if not isinstance(raw, dict):
                return out
            for kind, arr in raw.items():
                if not isinstance(arr, list):
                    continue
                out[str(kind)] = [
                    DeviceEntry(str(it.get("plugin_id") or ""), str(it.get("name") or ""))
                    for it in arr
                    if isinstance(it, dict) and it.get("plugin_id")
                ]
            return out

        prefs = cls(
            favorites=_load_bucket("favorites"),
            recents=_load_bucket("recents"),
            max_recents=int(data.get("max_recents") or 12),
        )

        # Ensure known keys exist
        for k in ("instrument", "note_fx", "audio_fx"):
            prefs.favorites.setdefault(k, [])
            prefs.recents.setdefault(k, [])
        return prefs

    def save(self) -> None:
        path = _prefs_path()
        data = {
            "max_recents": int(self.max_recents),
            "favorites": {
                k: [{"plugin_id": e.plugin_id, "name": e.name} for e in v]
                for k, v in self.favorites.items()
            },
            "recents": {
                k: [{"plugin_id": e.plugin_id, "name": e.name} for e in v]
                for k, v in self.recents.items()
            },
        }
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def add_recent(self, kind: str, plugin_id: str, name: str) -> None:
        kind = str(kind)
        plugin_id = str(plugin_id)
        name = str(name)
        if not plugin_id:
            return
        bucket = self.recents.setdefault(kind, [])
        # Remove duplicates
        bucket[:] = [e for e in bucket if e.plugin_id != plugin_id]
        bucket.insert(0, DeviceEntry(plugin_id, name))
        del bucket[self.max_recents :]

    def is_favorite(self, kind: str, plugin_id: str) -> bool:
        kind = str(kind)
        plugin_id = str(plugin_id)
        return any(e.plugin_id == plugin_id for e in self.favorites.get(kind, []))

    def toggle_favorite(self, kind: str, plugin_id: str, name: str) -> bool:
        """Toggle favorite; returns True if now favorite."""
        kind = str(kind)
        plugin_id = str(plugin_id)
        name = str(name)
        bucket = self.favorites.setdefault(kind, [])
        for i, e in enumerate(list(bucket)):
            if e.plugin_id == plugin_id:
                try:
                    bucket.pop(i)
                except Exception:
                    pass
                return False
        bucket.insert(0, DeviceEntry(plugin_id, name))
        return True

    def clear_recents(self, kind: str) -> None:
        kind = str(kind)
        self.recents[kind] = []
