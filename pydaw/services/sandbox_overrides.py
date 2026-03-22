# -*- coding: utf-8 -*-
"""Per-Plugin Sandbox Override — opt-in / opt-out per Plugin.

v0.0.20.709 — Phase P6C: Pro-Plugin Override

Stores per-plugin sandbox preferences in QSettings so that individual
plugins can be forced into sandbox mode or forced to run in-process,
regardless of the global sandbox toggle.

Override modes:
    "default"   — follow global setting (audio/plugin_sandbox_enabled)
    "sandbox"   — always run in sandbox subprocess
    "inprocess" — always run in-process (no sandbox)

Key format in QSettings:
    audio/sandbox_override/<plugin_type>/<plugin_name_hash> = "default"|"sandbox"|"inprocess"

Thread-safe: all access via QSettings (file-backed, per-call).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Override modes
# ---------------------------------------------------------------------------

OVERRIDE_DEFAULT = "default"     # follow global setting
OVERRIDE_SANDBOX = "sandbox"     # force sandbox
OVERRIDE_INPROCESS = "inprocess" # force in-process

_VALID_MODES = {OVERRIDE_DEFAULT, OVERRIDE_SANDBOX, OVERRIDE_INPROCESS}

_PREFIX = "audio/sandbox_override/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_key(plugin_type: str, plugin_path: str) -> str:
    """Build a stable QSettings key for a plugin.

    Uses a short hash of the path to keep the key safe for QSettings.
    """
    ptype = str(plugin_type or "unknown").lower().replace("/", "_")
    path_hash = hashlib.md5(str(plugin_path or "").encode("utf-8")).hexdigest()[:12]
    return f"{_PREFIX}{ptype}/{path_hash}"


def _make_display_key(plugin_type: str, plugin_name: str) -> str:
    """Human-readable key for logging / UI display."""
    return f"{plugin_type}:{plugin_name}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_override(plugin_type: str, plugin_path: str) -> str:
    """Get sandbox override for a specific plugin.

    Returns one of: "default", "sandbox", "inprocess".
    """
    try:
        from pydaw.core.settings_store import get_value
        key = _make_key(plugin_type, plugin_path)
        raw = get_value(key, OVERRIDE_DEFAULT)
        if isinstance(raw, str) and raw in _VALID_MODES:
            return raw
        return OVERRIDE_DEFAULT
    except Exception:
        return OVERRIDE_DEFAULT


def set_override(plugin_type: str, plugin_path: str, mode: str,
                 plugin_name: str = "") -> None:
    """Set sandbox override for a specific plugin.

    Args:
        plugin_type: "vst3", "vst2", "clap", "lv2", "ladspa"
        plugin_path: full path or URI of the plugin
        mode: "default", "sandbox", or "inprocess"
        plugin_name: optional display name for logging
    """
    if mode not in _VALID_MODES:
        _log.warning("Invalid sandbox override mode: %r (using 'default')", mode)
        mode = OVERRIDE_DEFAULT

    try:
        from pydaw.core.settings_store import set_value
        key = _make_key(plugin_type, plugin_path)
        set_value(key, mode)
        display = _make_display_key(plugin_type, plugin_name or plugin_path)
        _log.info("Sandbox override set: %s → %s", display, mode)
    except Exception as e:
        _log.error("Failed to set sandbox override: %s", e)


def should_sandbox(plugin_type: str, plugin_path: str,
                   global_sandbox_enabled: bool) -> bool:
    """Determine whether a plugin should run in sandbox.

    Checks per-plugin override first, falls back to global setting.

    Args:
        plugin_type: "vst3", "vst2", "clap", "lv2", "ladspa"
        plugin_path: full path or URI
        global_sandbox_enabled: current global sandbox toggle state

    Returns:
        True if the plugin should run in a sandbox subprocess.
    """
    override = get_override(plugin_type, plugin_path)
    if override == OVERRIDE_SANDBOX:
        return True
    if override == OVERRIDE_INPROCESS:
        return False
    # "default" → follow global
    return global_sandbox_enabled


def clear_override(plugin_type: str, plugin_path: str) -> None:
    """Remove per-plugin override (revert to global setting)."""
    try:
        from pydaw.core.settings_store import get_settings
        key = _make_key(plugin_type, plugin_path)
        s = get_settings()
        s.remove(key)
    except Exception as e:
        _log.error("Failed to clear sandbox override: %s", e)


def get_all_overrides() -> list:
    """Get all stored per-plugin overrides (for UI display).

    Returns list of dicts: [{"key": str, "mode": str}, ...]
    """
    result = []
    try:
        from pydaw.core.settings_store import get_settings
        s = get_settings()
        s.beginGroup("audio/sandbox_override")
        for ptype in s.childGroups():
            s.beginGroup(ptype)
            for phash in s.childKeys():
                mode = str(s.value(phash, OVERRIDE_DEFAULT) or OVERRIDE_DEFAULT)
                result.append({
                    "key": f"{ptype}/{phash}",
                    "mode": mode,
                })
            s.endGroup()
        s.endGroup()
    except Exception as e:
        _log.error("Failed to enumerate sandbox overrides: %s", e)
    return result
