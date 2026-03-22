# -*- coding: utf-8 -*-
"""Persistent browser places / favorite directories (UI-only, safe).

Stored outside projects so project portability is unaffected.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Dict


def _prefs_path() -> Path:
    base = Path(os.path.expanduser("~/.cache")) / "ChronoScaleStudio"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        return Path("browser_places.json")
    return base / "browser_places.json"


class BrowserPlacesPrefs:
    def __init__(self, places: List[Dict[str, str]] | None = None):
        self.places: List[Dict[str, str]] = list(places or [])

    @classmethod
    def load(cls) -> "BrowserPlacesPrefs":
        path = _prefs_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        arr = raw.get("places") if isinstance(raw, dict) else []
        out: List[Dict[str, str]] = []
        if isinstance(arr, list):
            for it in arr:
                if not isinstance(it, dict):
                    continue
                label = str(it.get("label") or "").strip()
                path_str = str(it.get("path") or "").strip()
                if not path_str:
                    continue
                out.append({"label": label or Path(path_str).name or path_str, "path": path_str})
        return cls(out)

    def save(self) -> None:
        path = _prefs_path()
        data = {"places": list(self.places)}
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def add_place(self, label: str, path_str: str) -> bool:
        path_norm = str(Path(path_str).expanduser())
        if not path_norm:
            return False
        for it in self.places:
            if str(it.get("path") or "") == path_norm:
                return False
        self.places.append({"label": str(label or Path(path_norm).name or path_norm), "path": path_norm})
        return True

    def remove_place(self, path_str: str) -> None:
        path_norm = str(Path(path_str).expanduser())
        self.places = [it for it in self.places if str(it.get("path") or "") != path_norm]
