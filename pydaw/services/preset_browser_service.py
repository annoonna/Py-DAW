# -*- coding: utf-8 -*-
"""Unified Preset Browser Service for all plugin types (VST3/CLAP/LV2/Built-in).

Handles scanning, saving, loading, categorizing, and managing presets
across all supported plugin formats.

Design goals:
- SAFE: Preset operations never crash the DAW; failures are logged and tolerated.
- Format-agnostic: Unified API for VST3/CLAP/LV2/built-in presets.
- User presets stored in ~/.config/ChronoScaleStudio/presets/<plugin_safe_id>/
- Factory presets read-only from plugin itself or bundled directories.
- Favorites per-user, persisted in JSON.

v0.0.20.652 — AP4 Phase 4B: Preset Browser Service
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PresetInfo:
    """Describes one preset for any plugin type."""
    name: str
    category: str = "User"          # "Factory" | "User" | "Favorites"
    plugin_type: str = ""           # "vst3" | "clap" | "lv2" | "builtin"
    plugin_id: str = ""             # stable plugin identifier
    file_path: str = ""             # path to preset file (if file-based)
    is_factory: bool = False
    is_favorite: bool = False
    tags: List[str] = field(default_factory=list)
    timestamp: float = 0.0         # creation/modification time
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PresetInfo":
        try:
            return cls(
                name=str(d.get("name", "")),
                category=str(d.get("category", "User")),
                plugin_type=str(d.get("plugin_type", "")),
                plugin_id=str(d.get("plugin_id", "")),
                file_path=str(d.get("file_path", "")),
                is_factory=bool(d.get("is_factory", False)),
                is_favorite=bool(d.get("is_favorite", False)),
                tags=list(d.get("tags", [])),
                timestamp=float(d.get("timestamp", 0.0)),
                size_bytes=int(d.get("size_bytes", 0)),
            )
        except Exception:
            return cls(name=str(d.get("name", "Unknown")))


@dataclass
class ABSlot:
    """A/B comparison slot holding a snapshot of plugin state."""
    name: str = ""
    state_blob: str = ""            # Base64-encoded state
    param_values: Dict[str, float] = field(default_factory=dict)
    is_active: bool = False
    timestamp: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Preset Browser Service
# ═══════════════════════════════════════════════════════════════════════════════

class PresetBrowserService:
    """Manages presets for all plugin types with categories, favorites, A/B compare.

    Thread-safety: All methods are safe to call from the GUI thread.
    File I/O uses try/except to never crash on permission errors, missing dirs, etc.
    """

    _CONFIG_BASE = ".config/ChronoScaleStudio"

    def __init__(self):
        self._favorites: Dict[str, Set[str]] = {}   # plugin_safe_id -> set of preset names
        self._ab_slots: Dict[str, Dict[str, ABSlot]] = {}  # plugin_key -> {"A": slot, "B": slot}
        self._load_favorites()

    # ── Directory helpers ─────────────────────────────────────────────────

    @staticmethod
    def _config_dir() -> Path:
        """Return base config directory, creating it if needed."""
        d = Path.home() / PresetBrowserService._CONFIG_BASE
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d

    @staticmethod
    def _safe_plugin_id(plugin_type: str, plugin_id: str) -> str:
        """Create a filesystem-safe identifier from plugin type and ID."""
        raw = f"{plugin_type}_{plugin_id}"
        # Replace problematic characters
        safe = re.sub(r'[^\w\-.]', '_', raw)
        # Truncate to reasonable length
        return safe[:200] if len(safe) > 200 else safe

    def preset_dir(self, plugin_type: str, plugin_id: str) -> Path:
        """Return the user preset directory for a specific plugin."""
        safe_id = self._safe_plugin_id(plugin_type, plugin_id)
        d = self._config_dir() / "presets" / safe_id
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d

    def _favorites_path(self) -> Path:
        return self._config_dir() / "preset_favorites.json"

    # ── Favorites persistence ─────────────────────────────────────────────

    def _load_favorites(self) -> None:
        """Load favorites from disk. Safe: failures produce empty favorites."""
        try:
            p = self._favorites_path()
            if not p.is_file():
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            for k, v in data.items():
                if isinstance(v, list):
                    self._favorites[str(k)] = set(str(x) for x in v)
        except Exception:
            pass

    def _save_favorites(self) -> None:
        """Persist favorites to disk."""
        try:
            data = {k: sorted(v) for k, v in self._favorites.items()}
            self._favorites_path().write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning("Failed to save preset favorites: %s", e)

    def is_favorite(self, plugin_type: str, plugin_id: str, preset_name: str) -> bool:
        safe_id = self._safe_plugin_id(plugin_type, plugin_id)
        return preset_name in self._favorites.get(safe_id, set())

    def toggle_favorite(self, plugin_type: str, plugin_id: str, preset_name: str) -> bool:
        """Toggle favorite status. Returns new is_favorite state."""
        safe_id = self._safe_plugin_id(plugin_type, plugin_id)
        favs = self._favorites.setdefault(safe_id, set())
        if preset_name in favs:
            favs.discard(preset_name)
            result = False
        else:
            favs.add(preset_name)
            result = True
        self._save_favorites()
        return result

    # ── Preset scanning ───────────────────────────────────────────────────

    def _preset_extension(self, plugin_type: str) -> str:
        """Return the file extension for presets of this plugin type."""
        ext_map = {
            "vst3": ".vstpreset",
            "vst2": ".vstpreset",
            "clap": ".clap_preset",
            "lv2": ".lv2preset",
            "builtin": ".json",
        }
        return ext_map.get(plugin_type, ".preset")

    def scan_user_presets(self, plugin_type: str, plugin_id: str) -> List[PresetInfo]:
        """Scan the user preset directory for saved presets."""
        result: List[PresetInfo] = []
        try:
            d = self.preset_dir(plugin_type, plugin_id)
            ext = self._preset_extension(plugin_type)
            safe_id = self._safe_plugin_id(plugin_type, plugin_id)
            favs = self._favorites.get(safe_id, set())

            for f in sorted(d.iterdir()):
                if not f.is_file():
                    continue
                if not f.name.endswith(ext):
                    continue
                name = f.name[: -len(ext)]
                try:
                    stat = f.stat()
                    ts = stat.st_mtime
                    size = stat.st_size
                except Exception:
                    ts = 0.0
                    size = 0
                result.append(PresetInfo(
                    name=name,
                    category="Favorites" if name in favs else "User",
                    plugin_type=plugin_type,
                    plugin_id=plugin_id,
                    file_path=str(f),
                    is_factory=False,
                    is_favorite=name in favs,
                    timestamp=ts,
                    size_bytes=size,
                ))
        except Exception as e:
            log.debug("scan_user_presets error for %s/%s: %s", plugin_type, plugin_id, e)
        return result

    def scan_vst3_factory_presets(self, vst3_path: str) -> List[PresetInfo]:
        """Scan for VST3 factory preset files in standard locations.

        VST3 presets are typically stored in:
        - Linux: ~/.vst3/presets/<vendor>/<plugin>/
        - Linux: /usr/share/vst3/presets/<vendor>/<plugin>/
        """
        result: List[PresetInfo] = []
        try:
            bundle_name = Path(vst3_path).stem
            # Standard VST3 preset locations on Linux
            search_dirs = [
                Path.home() / ".vst3" / "presets",
                Path("/usr/share/vst3/presets"),
                Path("/usr/local/share/vst3/presets"),
            ]
            # Also look inside the bundle itself
            bundle_preset_dir = Path(vst3_path) / "Contents" / "Resources" / "Presets"
            if bundle_preset_dir.is_dir():
                search_dirs.append(bundle_preset_dir)

            seen: Set[str] = set()
            for base in search_dirs:
                if not base.is_dir():
                    continue
                try:
                    self._scan_dir_recursive(
                        base, bundle_name, result, seen,
                        plugin_type="vst3", plugin_id=vst3_path,
                        is_factory=True, max_depth=4,
                    )
                except Exception:
                    continue
        except Exception as e:
            log.debug("scan_vst3_factory_presets error: %s", e)
        return result

    def _scan_dir_recursive(
        self, directory: Path, name_hint: str,
        result: List[PresetInfo], seen: Set[str],
        plugin_type: str, plugin_id: str,
        is_factory: bool, max_depth: int = 3,
        _depth: int = 0,
    ) -> None:
        """Recursively scan a directory for preset files."""
        if _depth > max_depth:
            return
        try:
            for entry in directory.iterdir():
                if entry.is_dir():
                    self._scan_dir_recursive(
                        entry, name_hint, result, seen,
                        plugin_type, plugin_id, is_factory,
                        max_depth, _depth + 1,
                    )
                elif entry.is_file() and entry.suffix in (".vstpreset", ".fxp", ".fxb"):
                    name = entry.stem
                    if name in seen:
                        continue
                    seen.add(name)
                    try:
                        stat = entry.stat()
                        ts = stat.st_mtime
                        size = stat.st_size
                    except Exception:
                        ts = 0.0
                        size = 0
                    # Derive category from parent directory name
                    cat_name = entry.parent.name if entry.parent != directory else "Factory"
                    result.append(PresetInfo(
                        name=name,
                        category=cat_name if is_factory else "User",
                        plugin_type=plugin_type,
                        plugin_id=plugin_id,
                        file_path=str(entry),
                        is_factory=is_factory,
                        tags=[cat_name] if cat_name != "Factory" else [],
                        timestamp=ts,
                        size_bytes=size,
                    ))
        except PermissionError:
            pass
        except Exception:
            pass

    def scan_all_presets(self, plugin_type: str, plugin_id: str,
                         vst3_path: str = "") -> List[PresetInfo]:
        """Scan both factory and user presets, merging them with favorites."""
        user_presets = self.scan_user_presets(plugin_type, plugin_id)
        factory_presets: List[PresetInfo] = []
        if plugin_type in ("vst3", "vst2") and vst3_path:
            factory_presets = self.scan_vst3_factory_presets(vst3_path)
        # Merge: factory first, then user
        all_presets = factory_presets + user_presets
        # Mark favorites
        safe_id = self._safe_plugin_id(plugin_type, plugin_id)
        favs = self._favorites.get(safe_id, set())
        for p in all_presets:
            if p.name in favs:
                p.is_favorite = True
        return all_presets

    # ── Preset save / load / delete ───────────────────────────────────────

    def save_preset(
        self,
        plugin_type: str,
        plugin_id: str,
        name: str,
        state_data: bytes,
        tags: Optional[List[str]] = None,
    ) -> Optional[PresetInfo]:
        """Save a preset to the user preset directory.

        state_data: raw binary state blob (format depends on plugin type).
        Returns PresetInfo on success, None on failure.
        """
        if not name or not state_data:
            return None
        try:
            safe_name = re.sub(r'[^\w\s\-.]', '', name).strip()
            if not safe_name:
                safe_name = "preset"
            ext = self._preset_extension(plugin_type)
            d = self.preset_dir(plugin_type, plugin_id)
            fpath = d / f"{safe_name}{ext}"
            fpath.write_bytes(state_data)

            safe_id = self._safe_plugin_id(plugin_type, plugin_id)
            favs = self._favorites.get(safe_id, set())

            return PresetInfo(
                name=safe_name,
                category="User",
                plugin_type=plugin_type,
                plugin_id=plugin_id,
                file_path=str(fpath),
                is_factory=False,
                is_favorite=safe_name in favs,
                tags=list(tags) if tags else [],
                timestamp=time.time(),
                size_bytes=len(state_data),
            )
        except Exception as e:
            log.warning("save_preset failed: %s", e)
            return None

    def save_preset_b64(
        self,
        plugin_type: str,
        plugin_id: str,
        name: str,
        state_b64: str,
        tags: Optional[List[str]] = None,
    ) -> Optional[PresetInfo]:
        """Save a Base64-encoded state blob as a preset."""
        try:
            data = base64.b64decode(state_b64)
            return self.save_preset(plugin_type, plugin_id, name, data, tags)
        except Exception:
            return None

    def load_preset(self, preset: PresetInfo) -> Optional[bytes]:
        """Load raw preset data from a PresetInfo.

        Returns binary state data or None on failure.
        """
        try:
            if not preset.file_path or not os.path.isfile(preset.file_path):
                return None
            return Path(preset.file_path).read_bytes()
        except Exception as e:
            log.debug("load_preset error: %s", e)
            return None

    def load_preset_b64(self, preset: PresetInfo) -> str:
        """Load preset data as Base64 string."""
        data = self.load_preset(preset)
        if data:
            try:
                return base64.b64encode(data).decode("ascii")
            except Exception:
                pass
        return ""

    def delete_preset(self, preset: PresetInfo) -> bool:
        """Delete a user preset file. Factory presets cannot be deleted."""
        if preset.is_factory:
            return False
        try:
            if preset.file_path and os.path.isfile(preset.file_path):
                os.remove(preset.file_path)
                return True
        except Exception as e:
            log.warning("delete_preset failed: %s", e)
        return False

    def rename_preset(self, preset: PresetInfo, new_name: str) -> Optional[PresetInfo]:
        """Rename a user preset. Returns updated PresetInfo or None on failure."""
        if preset.is_factory or not new_name.strip():
            return None
        try:
            safe_name = re.sub(r'[^\w\s\-.]', '', new_name).strip()
            if not safe_name:
                return None
            old_path = Path(preset.file_path)
            if not old_path.is_file():
                return None
            new_path = old_path.parent / f"{safe_name}{old_path.suffix}"
            if new_path.exists():
                return None  # Don't overwrite
            old_path.rename(new_path)
            # Update favorites if the old name was a favorite
            safe_id = self._safe_plugin_id(preset.plugin_type, preset.plugin_id)
            favs = self._favorites.get(safe_id, set())
            if preset.name in favs:
                favs.discard(preset.name)
                favs.add(safe_name)
                self._save_favorites()
            return PresetInfo(
                name=safe_name,
                category=preset.category,
                plugin_type=preset.plugin_type,
                plugin_id=preset.plugin_id,
                file_path=str(new_path),
                is_factory=False,
                is_favorite=safe_name in favs,
                tags=preset.tags,
                timestamp=time.time(),
                size_bytes=preset.size_bytes,
            )
        except Exception as e:
            log.warning("rename_preset failed: %s", e)
            return None

    # ── A/B Comparison ────────────────────────────────────────────────────

    def _ab_key(self, plugin_type: str, plugin_id: str, device_id: str) -> str:
        return f"{plugin_type}:{plugin_id}:{device_id}"

    def get_ab_slots(self, plugin_type: str, plugin_id: str,
                     device_id: str) -> Dict[str, ABSlot]:
        """Get or create A/B slots for a device instance."""
        key = self._ab_key(plugin_type, plugin_id, device_id)
        if key not in self._ab_slots:
            self._ab_slots[key] = {
                "A": ABSlot(name="A", is_active=True),
                "B": ABSlot(name="B"),
            }
        return self._ab_slots[key]

    def store_ab_snapshot(
        self,
        plugin_type: str,
        plugin_id: str,
        device_id: str,
        slot_name: str,
        state_b64: str,
        param_values: Optional[Dict[str, float]] = None,
    ) -> None:
        """Store current state into an A/B slot."""
        slots = self.get_ab_slots(plugin_type, plugin_id, device_id)
        slot = slots.get(slot_name)
        if slot is None:
            return
        slot.state_blob = str(state_b64 or "")
        slot.param_values = dict(param_values) if param_values else {}
        slot.timestamp = time.time()

    def switch_ab(
        self, plugin_type: str, plugin_id: str, device_id: str
    ) -> Optional[ABSlot]:
        """Switch between A and B. Returns the newly active slot (with its state to restore)."""
        slots = self.get_ab_slots(plugin_type, plugin_id, device_id)
        slot_a = slots.get("A")
        slot_b = slots.get("B")
        if slot_a is None or slot_b is None:
            return None
        if slot_a.is_active:
            slot_a.is_active = False
            slot_b.is_active = True
            return slot_b
        else:
            slot_b.is_active = False
            slot_a.is_active = True
            return slot_a

    def get_active_ab_slot_name(
        self, plugin_type: str, plugin_id: str, device_id: str
    ) -> str:
        """Return "A" or "B" depending on which slot is active."""
        slots = self.get_ab_slots(plugin_type, plugin_id, device_id)
        for name, slot in slots.items():
            if slot.is_active:
                return name
        return "A"

    # ── Filtering / Searching ─────────────────────────────────────────────

    @staticmethod
    def filter_presets(
        presets: List[PresetInfo],
        search: str = "",
        category: str = "",
        favorites_only: bool = False,
    ) -> List[PresetInfo]:
        """Filter a preset list by search term, category, and favorites."""
        result = list(presets)
        if favorites_only:
            result = [p for p in result if p.is_favorite]
        if category:
            cat_lower = category.lower()
            if cat_lower == "favorites":
                result = [p for p in result if p.is_favorite]
            elif cat_lower == "factory":
                result = [p for p in result if p.is_factory]
            elif cat_lower == "user":
                result = [p for p in result if not p.is_factory]
            else:
                result = [p for p in result if p.category.lower() == cat_lower]
        if search:
            terms = search.lower().split()
            result = [
                p for p in result
                if all(t in p.name.lower() or any(t in tag.lower() for tag in p.tags) for t in terms)
            ]
        return result

    @staticmethod
    def get_categories(presets: List[PresetInfo]) -> List[str]:
        """Extract unique categories from a preset list, sorted."""
        cats: Set[str] = set()
        for p in presets:
            if p.category:
                cats.add(p.category)
        # Standard order: All, Favorites, Factory, User, then others alphabetically
        order = ["All", "Favorites", "Factory", "User"]
        result = [c for c in order if c in cats or c == "All"]
        rest = sorted(c for c in cats if c not in order)
        return result + rest


# ═══════════════════════════════════════════════════════════════════════════════
# Plugin State Manager — auto-save / restore / undo
# ═══════════════════════════════════════════════════════════════════════════════

class PluginStateManager:
    """Manages automatic state saving and undo history for plugin parameters.

    Design:
    - Listens for parameter changes and auto-saves state to project at intervals.
    - Maintains an undo stack per device (max depth configurable).
    - State is stored as Base64 blobs in the project JSON.

    v0.0.20.652 — AP4 Phase 4C: Plugin State Management
    """

    _MAX_UNDO_DEPTH = 30

    def __init__(self):
        self._undo_stacks: Dict[str, List[Dict[str, Any]]] = {}   # device_key -> [snapshots]
        self._redo_stacks: Dict[str, List[Dict[str, Any]]] = {}
        self._last_auto_save: Dict[str, float] = {}
        self._auto_save_interval = 5.0  # seconds between auto-saves

    @staticmethod
    def _device_key(track_id: str, device_id: str) -> str:
        return f"{track_id}:{device_id}"

    def push_undo(self, track_id: str, device_id: str,
                  state_b64: str, param_values: Dict[str, float],
                  description: str = "") -> None:
        """Push current state onto the undo stack for a device."""
        key = self._device_key(track_id, device_id)
        stack = self._undo_stacks.setdefault(key, [])
        snapshot = {
            "state_b64": str(state_b64 or ""),
            "params": dict(param_values),
            "description": str(description or ""),
            "timestamp": time.time(),
        }
        stack.append(snapshot)
        # Trim to max depth
        if len(stack) > self._MAX_UNDO_DEPTH:
            stack[:] = stack[-self._MAX_UNDO_DEPTH:]
        # Clear redo stack on new action
        self._redo_stacks.pop(key, None)

    def undo(self, track_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        """Pop last state from undo stack. Returns snapshot dict or None."""
        key = self._device_key(track_id, device_id)
        stack = self._undo_stacks.get(key)
        if not stack or len(stack) < 2:
            return None  # Need at least 2: current + previous
        # Current state goes to redo
        current = stack.pop()
        redo = self._redo_stacks.setdefault(key, [])
        redo.append(current)
        if len(redo) > self._MAX_UNDO_DEPTH:
            redo[:] = redo[-self._MAX_UNDO_DEPTH:]
        # Return the previous state
        return stack[-1] if stack else None

    def redo(self, track_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        """Redo: pop from redo stack and push to undo."""
        key = self._device_key(track_id, device_id)
        redo = self._redo_stacks.get(key)
        if not redo:
            return None
        snapshot = redo.pop()
        stack = self._undo_stacks.setdefault(key, [])
        stack.append(snapshot)
        return snapshot

    def can_undo(self, track_id: str, device_id: str) -> bool:
        key = self._device_key(track_id, device_id)
        stack = self._undo_stacks.get(key, [])
        return len(stack) >= 2

    def can_redo(self, track_id: str, device_id: str) -> bool:
        key = self._device_key(track_id, device_id)
        return bool(self._redo_stacks.get(key))

    def should_auto_save(self, track_id: str, device_id: str) -> bool:
        """Check if enough time has passed since last auto-save for this device."""
        key = self._device_key(track_id, device_id)
        last = self._last_auto_save.get(key, 0.0)
        return (time.time() - last) >= self._auto_save_interval

    def mark_auto_saved(self, track_id: str, device_id: str) -> None:
        """Record that an auto-save just happened for this device."""
        key = self._device_key(track_id, device_id)
        self._last_auto_save[key] = time.time()

    def clear_device(self, track_id: str, device_id: str) -> None:
        """Clear undo/redo history for a device (e.g. when device is removed)."""
        key = self._device_key(track_id, device_id)
        self._undo_stacks.pop(key, None)
        self._redo_stacks.pop(key, None)
        self._last_auto_save.pop(key, None)


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton access
# ═══════════════════════════════════════════════════════════════════════════════

_preset_browser_service: Optional[PresetBrowserService] = None
_plugin_state_manager: Optional[PluginStateManager] = None


def get_preset_browser_service() -> PresetBrowserService:
    """Return the global PresetBrowserService singleton."""
    global _preset_browser_service
    if _preset_browser_service is None:
        _preset_browser_service = PresetBrowserService()
    return _preset_browser_service


def get_plugin_state_manager() -> PluginStateManager:
    """Return the global PluginStateManager singleton."""
    global _plugin_state_manager
    if _plugin_state_manager is None:
        _plugin_state_manager = PluginStateManager()
    return _plugin_state_manager
