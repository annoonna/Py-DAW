# -*- coding: utf-8 -*-
"""Plugin Crash Indicator Widget — Bitwig-style crash badge.

v0.0.20.702 — Phase P6A

Shows the crash/health status of a sandboxed plugin on a track.
Three states:
    ✅ Running  — green dot, no text (unobtrusive)
    ⚠️ Crashed  — orange/red badge with "Crashed" label
    🔄 Restart  — spinning/pulsing blue while restarting

Click on the badge opens a context menu:
    - "Plugin neu laden" → restart with last state
    - "Plugin deaktivieren" → bypass, no more restarts
    - "Plugin entfernen" → remove from FX chain
    - "Crash-Info anzeigen" → show error message

Can be embedded in:
    - Arranger track header (small inline badge)
    - Mixer channel strip (color border)
    - Statusbar (summary: "2 Plugins crashed")

Usage:
    badge = CrashIndicatorBadge(parent=track_header_widget)
    badge.set_state(CrashState.CRASHED, "Segfault in Diva VST3")
    badge.reload_requested.connect(on_reload)
"""
from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QHBoxLayout, QMenu, QToolTip,
    )
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
    from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QFont, QAction
    _QT = True
except ImportError:
    _QT = False

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Crash State Enum
# ---------------------------------------------------------------------------

class CrashState(Enum):
    """Plugin health state."""
    HIDDEN = auto()      # No sandbox active (badge invisible)
    RUNNING = auto()     # Plugin running in sandbox (green dot)
    CRASHED = auto()     # Plugin crashed (red/orange badge)
    RESTARTING = auto()  # Plugin being restarted (blue pulse)
    DISABLED = auto()    # User disabled after crash (grey)


# ---------------------------------------------------------------------------
# Crash Indicator Badge
# ---------------------------------------------------------------------------

if _QT:
    class CrashIndicatorBadge(QWidget):
        """Small inline badge showing plugin sandbox health.

        Signals:
            reload_requested(track_id, slot_id)
            disable_requested(track_id, slot_id)
            remove_requested(track_id, slot_id)
        """

        reload_requested = pyqtSignal(str, str)   # track_id, slot_id
        factory_reset_requested = pyqtSignal(str, str)  # restart without state
        disable_requested = pyqtSignal(str, str)
        remove_requested = pyqtSignal(str, str)

        # Colors
        _COLOR_RUNNING = QColor("#4caf50")     # green
        _COLOR_CRASHED = QColor("#ff5722")     # red-orange
        _COLOR_RESTARTING = QColor("#2196f3")  # blue
        _COLOR_DISABLED = QColor("#666666")    # grey
        _COLOR_BG_CRASHED = QColor(255, 87, 34, 40)  # translucent red

        def __init__(self, track_id: str = "", slot_id: str = "",
                     parent: Optional[QWidget] = None):
            super().__init__(parent)
            self._track_id = track_id
            self._slot_id = slot_id
            self._state = CrashState.HIDDEN
            self._error_msg = ""
            self._plugin_name = ""
            self._crash_count = 0

            # Pulse animation for RESTARTING state
            self._pulse_timer = QTimer(self)
            self._pulse_timer.setInterval(80)
            self._pulse_timer.timeout.connect(self._on_pulse)
            self._pulse_alpha = 255
            self._pulse_dir = -15

            # Layout
            self._label = QLabel("")
            self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._label.setStyleSheet("padding: 0 3px;")

            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self._label)

            self.setFixedHeight(18)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_menu)

            self.setVisible(False)

        def set_ids(self, track_id: str, slot_id: str) -> None:
            self._track_id = str(track_id)
            self._slot_id = str(slot_id)

        def set_plugin_name(self, name: str) -> None:
            self._plugin_name = str(name)

        def set_state(self, state: CrashState, error_msg: str = "",
                      crash_count: int = 0) -> None:
            """Update the crash state."""
            self._state = state
            self._error_msg = str(error_msg)
            self._crash_count = crash_count
            self._update_display()

        def _update_display(self) -> None:
            """Update visual appearance based on state."""
            state = self._state

            if state == CrashState.HIDDEN:
                self.setVisible(False)
                self._pulse_timer.stop()
                return

            self.setVisible(True)

            if state == CrashState.RUNNING:
                self._label.setText("●")
                self._label.setStyleSheet(
                    f"QLabel {{ color: {self._COLOR_RUNNING.name()}; "
                    f"font-size: 10px; padding: 0 2px; }}"
                )
                self.setToolTip(
                    f"🛡️ Plugin läuft in Sandbox (crash-sicher)\n"
                    f"Plugin: {self._plugin_name}"
                )
                self._pulse_timer.stop()

            elif state == CrashState.CRASHED:
                count_text = f" (×{self._crash_count})" if self._crash_count > 1 else ""
                self._label.setText(f"⚠ Crash{count_text}")
                self._label.setStyleSheet(
                    f"QLabel {{ color: white; background: {self._COLOR_CRASHED.name()}; "
                    f"border-radius: 3px; font-size: 9px; font-weight: bold; "
                    f"padding: 1px 4px; }}"
                )
                tip = (
                    f"⚠️ Plugin gecrasht!\n\n"
                    f"Plugin: {self._plugin_name}\n"
                    f"Fehler: {self._error_msg}\n"
                    f"Crashes: {self._crash_count}\n\n"
                    f"Klick → Optionen (Neuladen / Deaktivieren / Entfernen)"
                )
                self.setToolTip(tip)
                self._pulse_timer.stop()

            elif state == CrashState.RESTARTING:
                self._label.setText("🔄")
                self._label.setStyleSheet(
                    f"QLabel {{ color: {self._COLOR_RESTARTING.name()}; "
                    f"font-size: 10px; padding: 0 2px; }}"
                )
                self.setToolTip(f"🔄 Plugin wird neu gestartet...\n{self._plugin_name}")
                self._pulse_timer.start()

            elif state == CrashState.DISABLED:
                self._label.setText("⊘")
                self._label.setStyleSheet(
                    f"QLabel {{ color: {self._COLOR_DISABLED.name()}; "
                    f"font-size: 10px; padding: 0 2px; }}"
                )
                self.setToolTip(
                    f"Plugin deaktiviert nach Crash\n"
                    f"Plugin: {self._plugin_name}\n"
                    f"Letzter Fehler: {self._error_msg}"
                )
                self._pulse_timer.stop()

        def _on_pulse(self) -> None:
            """Pulse animation tick."""
            self._pulse_alpha += self._pulse_dir
            if self._pulse_alpha <= 80:
                self._pulse_dir = 15
            elif self._pulse_alpha >= 255:
                self._pulse_dir = -15
            a = max(80, min(255, self._pulse_alpha))
            self._label.setStyleSheet(
                f"QLabel {{ color: rgba(33, 150, 243, {a}); "
                f"font-size: 10px; padding: 0 2px; }}"
            )

        def mousePressEvent(self, event) -> None:
            """Left click opens context menu."""
            if event.button() == Qt.MouseButton.LeftButton:
                self._show_menu(event.pos())
            super().mousePressEvent(event)

        def _show_menu(self, pos) -> None:
            """Show crash recovery context menu."""
            if self._state not in (CrashState.CRASHED, CrashState.DISABLED,
                                    CrashState.RUNNING):
                return

            menu = QMenu(self)
            menu.setStyleSheet(
                "QMenu { background: #2b2b2b; color: #ddd; border: 1px solid #555; }"
                "QMenu::item:selected { background: #ff6e40; color: white; }"
            )

            if self._state == CrashState.CRASHED:
                a_reload = menu.addAction("🔄 Plugin neu laden (letzter State)")
                a_reload.triggered.connect(lambda: self.reload_requested.emit(
                    self._track_id, self._slot_id))

                a_reset = menu.addAction("🔄 Plugin neu laden (Factory Default)")
                a_reset.triggered.connect(lambda: self.factory_reset_requested.emit(
                    self._track_id, self._slot_id))

                menu.addSeparator()

                a_disable = menu.addAction("⊘ Plugin deaktivieren")
                a_disable.triggered.connect(lambda: self.disable_requested.emit(
                    self._track_id, self._slot_id))

            elif self._state == CrashState.DISABLED:
                a_reload = menu.addAction("🔄 Plugin wieder aktivieren")
                a_reload.triggered.connect(lambda: self.reload_requested.emit(
                    self._track_id, self._slot_id))

            if self._state in (CrashState.CRASHED, CrashState.DISABLED):
                menu.addSeparator()
                a_remove = menu.addAction("✕ Plugin entfernen")
                a_remove.triggered.connect(lambda: self.remove_requested.emit(
                    self._track_id, self._slot_id))

            if self._error_msg:
                menu.addSeparator()
                a_info = menu.addAction(f"ℹ️ Fehler: {self._error_msg[:60]}")
                a_info.setEnabled(False)

            menu.exec(self.mapToGlobal(pos))


    # -----------------------------------------------------------------------
    # Statusbar Summary Widget
    # -----------------------------------------------------------------------

    class SandboxStatusWidget(QWidget):
        """Statusbar widget showing sandbox summary.

        Displays: "🛡️ 3/5 sandboxed" or "⚠️ 1 crashed"
        """

        details_requested = pyqtSignal()  # user wants to see details

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self._label = QLabel("")
            self._label.setStyleSheet("padding: 0 4px;")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._label)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setVisible(False)

        def update_status(self, total_sandboxed: int, crashed: int,
                          alive: int) -> None:
            """Update the displayed status."""
            if total_sandboxed == 0:
                self.setVisible(False)
                return

            self.setVisible(True)

            if crashed > 0:
                self._label.setText(f"⚠️ {crashed} crashed")
                self._label.setStyleSheet(
                    "QLabel { color: #ff5722; font-weight: bold; padding: 0 4px; }"
                )
                self.setToolTip(
                    f"Plugin Sandbox Status:\n"
                    f"  {alive} Plugin(s) laufen\n"
                    f"  {crashed} Plugin(s) gecrasht\n\n"
                    f"Klick für Details"
                )
            else:
                self._label.setText(f"🛡️ {alive}")
                self._label.setStyleSheet(
                    "QLabel { color: #4caf50; padding: 0 4px; }"
                )
                self.setToolTip(
                    f"Plugin Sandbox: {alive} Plugin(s) crash-sicher\n"
                    f"Klick für Details"
                )

        def mousePressEvent(self, event) -> None:
            if event.button() == Qt.MouseButton.LeftButton:
                self.details_requested.emit()
            super().mousePressEvent(event)


    # -----------------------------------------------------------------------
    # Crash Log
    # -----------------------------------------------------------------------

    class CrashLogEntry:
        """Single crash log entry."""
        __slots__ = ("timestamp", "track_id", "slot_id", "plugin_name",
                     "plugin_type", "error_message", "crash_count")

        def __init__(self, track_id: str = "", slot_id: str = "",
                     plugin_name: str = "", plugin_type: str = "",
                     error_message: str = "", crash_count: int = 1):
            import time
            self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.track_id = track_id
            self.slot_id = slot_id
            self.plugin_name = plugin_name
            self.plugin_type = plugin_type
            self.error_message = error_message
            self.crash_count = crash_count

        def to_line(self) -> str:
            return (f"[{self.timestamp}] {self.plugin_name} ({self.plugin_type}) "
                    f"on {self.track_id}/{self.slot_id}: {self.error_message} "
                    f"(crash #{self.crash_count})")


    class CrashLog:
        """Persistent crash log — saved to ~/.pydaw/crash_logs/."""

        def __init__(self, max_entries: int = 100):
            self._entries: list[CrashLogEntry] = []
            self._max = max_entries
            self._log_dir = ""
            try:
                import pathlib
                self._log_dir = str(pathlib.Path.home() / ".pydaw" / "crash_logs")
                pathlib.Path(self._log_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        def add(self, entry: CrashLogEntry) -> None:
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max:]
            # Append to file
            self._write_to_file(entry)

        def get_all(self) -> list[CrashLogEntry]:
            return list(self._entries)

        def get_text(self) -> str:
            return "\n".join(e.to_line() for e in self._entries)

        def _write_to_file(self, entry: CrashLogEntry) -> None:
            if not self._log_dir:
                return
            try:
                import time
                filename = time.strftime("crashes_%Y-%m-%d.log")
                path = f"{self._log_dir}/{filename}"
                with open(path, "a") as f:
                    f.write(entry.to_line() + "\n")
            except Exception:
                pass

else:
    # Stubs when Qt is not available
    class CrashIndicatorBadge:  # type: ignore
        pass
    class SandboxStatusWidget:  # type: ignore
        pass
    class CrashLogEntry:
        pass
    class CrashLog:
        pass
