"""QSettings convenience wrapper.

v0.0.2 introduces first real preferences:
- selected audio backend
- selected input/output device/port
- sample rate / buffer size (placeholders for later audio graph work)

Keep all persistence here so UI and engine modules stay clean.
"""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QSettings

from .settings import SettingsKeys


def get_settings() -> QSettings:
    """Return application QSettings instance."""
    keys = SettingsKeys()
    return QSettings(keys.organization, keys.application)


def get_value(key: str, default: Any = None) -> Any:
    s = get_settings()
    return s.value(key, default)


def set_value(key: str, value: Any) -> None:
    s = get_settings()
    s.setValue(key, value)
