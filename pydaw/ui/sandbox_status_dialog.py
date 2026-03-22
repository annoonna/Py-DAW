# -*- coding: utf-8 -*-
"""Sandbox Status Dialog — Bitwig-style Plugin Sandbox overview.

v0.0.20.704 — Phase P6B/P6C

Two dialogs:
1. SandboxStatusDialog   — live table of all sandboxed plugin workers
2. CrashLogDialog        — scrollable log of all crash events

Usage:
    dlg = SandboxStatusDialog(parent=main_window)
    dlg.exec()

    log_dlg = CrashLogDialog(crash_log=crash_log_instance, parent=main_window)
    log_dlg.exec()
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit,
        QTabWidget, QWidget, QMessageBox, QAbstractItemView,
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QFont
    _QT = True
except ImportError:
    _QT = False

_log = logging.getLogger(__name__)


if _QT:

    # ------------------------------------------------------------------
    # Sandbox Status Dialog (P6C: "Sandbox-Status…")
    # ------------------------------------------------------------------

    class SandboxStatusDialog(QDialog):
        """Live overview of all sandboxed plugin workers.

        Shows a table with columns:
            Track | Plugin | Type | PID | Status | Crashes | Actions
        Auto-refreshes every 500ms.
        """

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.setWindowTitle("🛡️ Plugin Sandbox Status")
            self.setMinimumSize(720, 400)
            self.setModal(False)  # non-modal so user can work

            self._setup_ui()

            # Refresh timer
            self._timer = QTimer(self)
            self._timer.setInterval(500)
            self._timer.timeout.connect(self._refresh)
            self._timer.start()
            self._refresh()

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            # Header
            hdr = QLabel(
                "Sandboxed plugin workers — jeder Plugin-Prozess läuft "
                "isoliert vom Hauptprozess."
            )
            hdr.setWordWrap(True)
            hdr.setStyleSheet("color: #aaa; font-size: 11px;")
            layout.addWidget(hdr)

            # Table
            self._table = QTableWidget(0, 7)
            self._table.setHorizontalHeaderLabels([
                "Track", "Plugin", "Typ", "PID", "Status",
                "Crashes", "Aktion",
            ])
            self._table.horizontalHeader().setStretchLastSection(True)
            self._table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents)
            self._table.setSelectionBehavior(
                QAbstractItemView.SelectionBehavior.SelectRows)
            self._table.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers)
            self._table.setAlternatingRowColors(True)
            self._table.setStyleSheet(
                "QTableWidget { background: #1e1e1e; alternate-background-color: #252525; "
                "color: #ddd; gridline-color: #333; }"
                "QHeaderView::section { background: #2a2a2a; color: #ccc; "
                "padding: 4px; border: 1px solid #333; font-weight: bold; }"
            )
            layout.addWidget(self._table, 1)

            # v0.0.20.722: Instrument Engines table
            lbl_inst = QLabel("🎹 Instrument-Engines (in-process)")
            lbl_inst.setStyleSheet("color: #aaa; font-size: 11px; margin-top: 8px;")
            layout.addWidget(lbl_inst)

            self._inst_table = QTableWidget(0, 5)
            self._inst_table.setHorizontalHeaderLabels([
                "Track", "Plugin", "Typ", "Status", "Pfad",
            ])
            self._inst_table.horizontalHeader().setStretchLastSection(True)
            self._inst_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents)
            self._inst_table.setSelectionBehavior(
                QAbstractItemView.SelectionBehavior.SelectRows)
            self._inst_table.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers)
            self._inst_table.setAlternatingRowColors(True)
            self._inst_table.setMaximumHeight(180)
            self._inst_table.setStyleSheet(
                "QTableWidget { background: #1e1e1e; alternate-background-color: #252525; "
                "color: #ddd; gridline-color: #333; }"
                "QHeaderView::section { background: #2a2a2a; color: #ccc; "
                "padding: 4px; border: 1px solid #333; font-weight: bold; }"
            )
            layout.addWidget(self._inst_table)

            # Summary
            self._lbl_summary = QLabel("")
            self._lbl_summary.setStyleSheet(
                "font-size: 11px; color: #aaa; padding: 4px;")
            layout.addWidget(self._lbl_summary)

            # v0.0.20.718: Rust Engine status line
            self._lbl_rust = QLabel("")
            self._lbl_rust.setStyleSheet(
                "font-size: 11px; color: #aaa; padding: 4px;")
            layout.addWidget(self._lbl_rust)

            # Buttons
            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)

            btn_restart_all = QPushButton("🔄 Alle neu starten")
            btn_restart_all.setToolTip("Alle Worker killen und neu starten")
            btn_restart_all.clicked.connect(self._restart_all)
            btn_row.addWidget(btn_restart_all)

            btn_kill_all = QPushButton("⊘ Alle stoppen")
            btn_kill_all.setToolTip("Alle Worker beenden")
            btn_kill_all.clicked.connect(self._kill_all)
            btn_row.addWidget(btn_kill_all)

            btn_row.addStretch(1)

            btn_close = QPushButton("Schließen")
            btn_close.clicked.connect(self.close)
            btn_row.addWidget(btn_close)

            layout.addLayout(btn_row)

        def _refresh(self) -> None:
            """Poll process manager and update table."""
            try:
                from pydaw.services.sandbox_process_manager import (
                    get_process_manager,
                )
                mgr = get_process_manager()
                status_list = mgr.get_all_status()
            except Exception:
                status_list = []

            self._table.setRowCount(len(status_list))

            total = len(status_list)
            crashed = 0
            alive = 0

            for row, s in enumerate(status_list):
                tid = s.get("track_id", "")
                pname = s.get("plugin_name", "?")
                ptype = s.get("plugin_type", "?")
                pid = s.get("pid", 0)
                is_alive = s.get("alive", False)
                is_crashed = s.get("crashed", False)
                ccount = s.get("crash_count", 0)
                error = s.get("error", "")

                if is_crashed:
                    crashed += 1
                    status_text = "⚠️ Crashed"
                    status_color = QColor("#ff5722")
                elif is_alive:
                    alive += 1
                    status_text = "✅ Running"
                    status_color = QColor("#4caf50")
                else:
                    status_text = "⊘ Stopped"
                    status_color = QColor("#888")

                items = [
                    QTableWidgetItem(str(tid)),
                    QTableWidgetItem(str(pname)),
                    QTableWidgetItem(str(ptype).upper()),
                    QTableWidgetItem(str(pid) if pid else "—"),
                    QTableWidgetItem(status_text),
                    QTableWidgetItem(str(ccount)),
                ]

                for col, item in enumerate(items):
                    if col == 4:
                        item.setForeground(status_color)
                    self._table.setItem(row, col, item)

                # Action button
                btn = QPushButton("🔄" if is_crashed else "⊘")
                btn.setFixedWidth(36)
                btn.setToolTip("Neu starten" if is_crashed else "Stoppen")
                slot_id = s.get("slot_id", "")
                if is_crashed:
                    btn.clicked.connect(
                        lambda _, t=tid, sl=slot_id: self._restart_one(t, sl))
                else:
                    btn.clicked.connect(
                        lambda _, t=tid, sl=slot_id: self._kill_one(t, sl))
                self._table.setCellWidget(row, 6, btn)

            self._lbl_summary.setText(
                f"Gesamt: {total} Worker  |  "
                f"✅ {alive} laufend  |  "
                f"⚠️ {crashed} gecrasht"
            )

            # v0.0.20.718: Rust Engine status
            try:
                from pydaw.services.rust_engine_bridge import RustEngineBridge
                if RustEngineBridge.is_enabled():
                    bridge = RustEngineBridge.instance()
                    if bridge.is_connected:
                        cpu = getattr(bridge, '_last_cpu_load', 0.0)
                        xruns = getattr(bridge, '_last_xrun_count', 0)
                        self._lbl_rust.setText(
                            f"🦀 Rust Engine: ✅ Verbunden (PID {getattr(bridge, '_process', None) and bridge._process.pid or '?'})  |  "
                            f"CPU: {cpu:.0%}  |  XRuns: {xruns}"
                        )
                        self._lbl_rust.setStyleSheet(
                            "font-size: 11px; color: #4caf50; padding: 4px;")
                    else:
                        self._lbl_rust.setText("🦀 Rust Engine: ⊘ Nicht verbunden")
                        self._lbl_rust.setStyleSheet(
                            "font-size: 11px; color: #888; padding: 4px;")
                else:
                    self._lbl_rust.setText("🦀 Rust Engine: ➖ Nicht aktiviert (USE_RUST_ENGINE=1)")
                    self._lbl_rust.setStyleSheet(
                        "font-size: 11px; color: #666; padding: 4px;")
            except Exception:
                self._lbl_rust.setText("")

            # v0.0.20.722: Instrument Engines table
            try:
                engine = None
                # Access via parent (MainWindow) → services → audio_engine
                try:
                    p = self.parent()
                    if p and hasattr(p, 'services') and hasattr(p.services, 'audio_engine'):
                        engine = p.services.audio_engine
                except Exception:
                    pass

                if engine is not None and hasattr(engine, 'get_active_instruments'):
                    instruments = engine.get_active_instruments()
                    self._inst_table.setRowCount(len(instruments))
                    for row, info in enumerate(instruments):
                        pname = str(info.get("plugin_name", "?"))
                        ptype = str(info.get("plugin_type", "?")).upper()
                        tid = str(info.get("track_id", ""))
                        is_ok = info.get("is_ok", False)
                        ppath = str(info.get("plugin_path", ""))
                        err = str(info.get("error", ""))

                        status_text = "✅ OK" if is_ok else f"❌ {err[:40]}"
                        status_color = QColor("#4caf50") if is_ok else QColor("#ff5722")

                        items = [
                            QTableWidgetItem(tid[:16] + "…" if len(tid) > 16 else tid),
                            QTableWidgetItem(pname),
                            QTableWidgetItem(ptype),
                            QTableWidgetItem(status_text),
                            QTableWidgetItem(ppath),
                        ]
                        for col, item in enumerate(items):
                            if col == 3:
                                item.setForeground(status_color)
                            self._inst_table.setItem(row, col, item)
                else:
                    self._inst_table.setRowCount(0)
            except Exception:
                self._inst_table.setRowCount(0)

        def _restart_one(self, track_id: str, slot_id: str) -> None:
            try:
                from pydaw.services.sandbox_process_manager import (
                    get_process_manager,
                )
                get_process_manager().restart(track_id, slot_id)
                self._refresh()
            except Exception as e:
                _log.error("restart_one failed: %s", e)

        def _kill_one(self, track_id: str, slot_id: str) -> None:
            try:
                from pydaw.services.sandbox_process_manager import (
                    get_process_manager,
                )
                get_process_manager().kill(track_id, slot_id)
                self._refresh()
            except Exception as e:
                _log.error("kill_one failed: %s", e)

        def _restart_all(self) -> None:
            try:
                from pydaw.services.sandbox_process_manager import (
                    get_process_manager,
                )
                mgr = get_process_manager()
                for s in mgr.get_all_status():
                    tid = s.get("track_id", "")
                    sid = s.get("slot_id", "")
                    if tid and sid:
                        mgr.restart(tid, sid)
                self._refresh()
            except Exception as e:
                _log.error("restart_all failed: %s", e)

        def _kill_all(self) -> None:
            try:
                from pydaw.services.sandbox_process_manager import (
                    get_process_manager,
                )
                mgr = get_process_manager()
                for s in list(mgr.get_all_status()):
                    tid = s.get("track_id", "")
                    sid = s.get("slot_id", "")
                    if tid and sid:
                        mgr.kill(tid, sid)
                self._refresh()
            except Exception as e:
                _log.error("kill_all failed: %s", e)

        def closeEvent(self, event) -> None:
            self._timer.stop()
            super().closeEvent(event)

    # ------------------------------------------------------------------
    # Crash Log Dialog (P6B: "Plugin Crash Log anzeigen…")
    # ------------------------------------------------------------------

    class CrashLogDialog(QDialog):
        """Shows the persistent crash log from ~/.pydaw/crash_logs/.

        Reads both in-memory log and on-disk log files.
        """

        def __init__(self, crash_log=None,
                     parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.setWindowTitle("🔥 Plugin Crash Log")
            self.setMinimumSize(600, 400)
            self.setModal(False)

            self._crash_log = crash_log
            self._setup_ui()
            self._load_log()

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            hdr = QLabel(
                "Crash-Log — Alle Plugin-Abstürze werden hier protokolliert."
            )
            hdr.setStyleSheet("color: #aaa; font-size: 11px;")
            layout.addWidget(hdr)

            self._text = QTextEdit()
            self._text.setReadOnly(True)
            self._text.setStyleSheet(
                "QTextEdit { background: #1a1a1a; color: #e0e0e0; "
                "font-family: 'Consolas', 'Monospace', monospace; "
                "font-size: 11px; border: 1px solid #333; }"
            )
            layout.addWidget(self._text, 1)

            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)

            btn_refresh = QPushButton("🔄 Aktualisieren")
            btn_refresh.clicked.connect(self._load_log)
            btn_row.addWidget(btn_refresh)

            btn_clear = QPushButton("🗑️ Log leeren")
            btn_clear.clicked.connect(self._clear_log)
            btn_row.addWidget(btn_clear)

            btn_row.addStretch(1)

            btn_close = QPushButton("Schließen")
            btn_close.clicked.connect(self.close)
            btn_row.addWidget(btn_close)

            layout.addLayout(btn_row)

        def _load_log(self) -> None:
            """Load log from memory and disk."""
            lines: list[str] = []

            # In-memory log
            if self._crash_log is not None:
                try:
                    text = self._crash_log.get_text()
                    if text:
                        lines.append("═══ In-Memory Log ═══")
                        lines.append(text)
                        lines.append("")
                except Exception:
                    pass

            # On-disk logs
            try:
                import pathlib
                log_dir = pathlib.Path.home() / ".pydaw" / "crash_logs"
                if log_dir.exists():
                    files = sorted(log_dir.glob("crashes_*.log"), reverse=True)
                    for f in files[:10]:  # last 10 days
                        try:
                            content = f.read_text(errors="replace").strip()
                            if content:
                                lines.append(f"═══ {f.name} ═══")
                                lines.append(content)
                                lines.append("")
                        except Exception:
                            continue
            except Exception:
                pass

            if not lines:
                lines.append("Keine Crash-Einträge vorhanden.")
                lines.append("")
                lines.append("Wenn ein Plugin in der Sandbox abstürzt, "
                             "werden Details hier protokolliert.")

            self._text.setPlainText("\n".join(lines))

        def _clear_log(self) -> None:
            """Clear in-memory log (disk logs are kept)."""
            if self._crash_log is not None:
                try:
                    self._crash_log._entries.clear()
                except Exception:
                    pass
            self._text.setPlainText("Log geleert.")

else:
    class SandboxStatusDialog:  # type: ignore
        pass
    class CrashLogDialog:  # type: ignore
        pass
