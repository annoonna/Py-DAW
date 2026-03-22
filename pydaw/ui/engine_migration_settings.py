"""Engine Migration Settings Widget.

v0.0.20.662 — Phase 1D

Provides a UI panel for managing the Python → Rust engine migration.
Can be embedded as a tab in AudioSettingsDialog or used standalone.

Features:
- Toggle per subsystem: Audio Playback, MIDI Dispatch, Plugin Hosting
- Rust engine availability indicator
- Performance benchmark runner with live results
- One-click "Migrate All" / "Rollback All"
- Status display per subsystem
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class EngineSubsystemRow(QWidget):
    """A single row for one subsystem (checkbox + status label)."""

    def __init__(self, subsystem: str, label: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.subsystem = subsystem

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self.cb_rust = QCheckBox(f"Rust: {label}")
        self.cb_rust.setToolTip(
            f"Wenn aktiviert, nutzt das Subsystem '{label}' die Rust Audio Engine "
            f"statt der Python Engine."
        )
        layout.addWidget(self.cb_rust)

        self.lbl_status = QLabel("Python")
        self.lbl_status.setMinimumWidth(120)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.lbl_status)

    def set_state(self, backend: str, status: str, error: str = ""):
        """Update display from migration state."""
        if backend == "rust":
            self.cb_rust.setChecked(True)
            color = "#4CAF50" if status == "active" else "#FF9800"
            self.lbl_status.setText(f"<b style='color:{color}'>Rust ({status})</b>")
        else:
            self.cb_rust.setChecked(False)
            self.lbl_status.setText("Python")

        if error:
            self.lbl_status.setToolTip(error)
        else:
            self.lbl_status.setToolTip("")


class EngineMigrationWidget(QWidget):
    """Widget for managing engine migration settings.

    Embed as a tab or use in a standalone dialog.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()
        self._refresh_state()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Rust availability banner ---
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        layout.addWidget(self.banner)

        # --- Subsystem toggles ---
        grp_sub = QGroupBox("Engine-Subsysteme")
        sub_layout = QVBoxLayout(grp_sub)

        self.row_audio = EngineSubsystemRow("audio_playback", "Audio Playback")
        self.row_midi = EngineSubsystemRow("midi_dispatch", "MIDI Dispatch")
        self.row_plugin = EngineSubsystemRow("plugin_hosting", "Plugin Hosting")
        sub_layout.addWidget(self.row_audio)
        sub_layout.addWidget(self.row_midi)
        sub_layout.addWidget(self.row_plugin)

        note = QLabel(
            "<i>Reihenfolge: Audio → MIDI → Plugins. "
            "MIDI benötigt Audio auf Rust, Plugins benötigen MIDI auf Rust.</i>"
        )
        note.setWordWrap(True)
        sub_layout.addWidget(note)

        layout.addWidget(grp_sub)

        # --- Quick actions ---
        grp_actions = QGroupBox("Schnellaktionen")
        act_layout = QHBoxLayout(grp_actions)

        self.btn_migrate_all = QPushButton("Alle → Rust")
        self.btn_migrate_all.setToolTip("Migriert alle Subsysteme auf die Rust Engine")
        act_layout.addWidget(self.btn_migrate_all)

        self.btn_rollback = QPushButton("Alle → Python")
        self.btn_rollback.setToolTip("Setzt alle Subsysteme auf die Python Engine zurück")
        act_layout.addWidget(self.btn_rollback)

        self.btn_benchmark = QPushButton("Performance-Vergleich")
        self.btn_benchmark.setToolTip("Startet einen A/B-Benchmark Python vs Rust")
        act_layout.addWidget(self.btn_benchmark)

        layout.addWidget(grp_actions)

        # --- Benchmark results ---
        self.grp_bench = QGroupBox("Benchmark-Ergebnisse")
        bench_layout = QVBoxLayout(self.grp_bench)

        self.bench_progress = QProgressBar()
        self.bench_progress.setRange(0, 4)
        self.bench_progress.setValue(0)
        self.bench_progress.setVisible(False)
        bench_layout.addWidget(self.bench_progress)

        self.bench_text = QTextEdit()
        self.bench_text.setReadOnly(True)
        self.bench_text.setMaximumHeight(200)
        self.bench_text.setPlainText("Noch kein Benchmark durchgeführt.")
        bench_layout.addWidget(self.bench_text)

        self.grp_bench.setVisible(False)
        layout.addWidget(self.grp_bench)

        # --- Rust as default ---
        self.cb_default = QCheckBox("Rust Engine als Standard für neue Projekte")
        self.cb_default.setToolTip(
            "Erst verfügbar wenn alle Subsysteme stabil auf Rust laufen."
        )
        self.cb_default.setEnabled(False)
        layout.addWidget(self.cb_default)

        layout.addStretch()

    def _connect_signals(self):
        """Connect UI signals to migration controller."""
        self.row_audio.cb_rust.toggled.connect(
            lambda on: self._on_subsystem_toggled("audio_playback", on))
        self.row_midi.cb_rust.toggled.connect(
            lambda on: self._on_subsystem_toggled("midi_dispatch", on))
        self.row_plugin.cb_rust.toggled.connect(
            lambda on: self._on_subsystem_toggled("plugin_hosting", on))

        self.btn_migrate_all.clicked.connect(self._on_migrate_all)
        self.btn_rollback.clicked.connect(self._on_rollback_all)
        self.btn_benchmark.clicked.connect(self._on_benchmark)
        self.cb_default.toggled.connect(self._on_default_toggled)

        # Connect to migration controller signals
        try:
            from pydaw.services.engine_migration import EngineMigrationController
            ctrl = EngineMigrationController.instance()
            ctrl.subsystem_changed.connect(self._on_migration_changed)
            ctrl.migration_error.connect(self._on_migration_error)
        except Exception:
            pass

    def _refresh_state(self):
        """Refresh all UI elements from migration controller state."""
        try:
            from pydaw.services.engine_migration import EngineMigrationController
            ctrl = EngineMigrationController.instance()
            summary = ctrl.get_migration_summary()
        except Exception:
            self.banner.setText(
                "<b style='color:#F44336'>Engine Migration nicht verfügbar</b>"
            )
            for row in (self.row_audio, self.row_midi, self.row_plugin):
                row.setEnabled(False)
            return

        # Rust availability
        rust_avail = summary.get("rust_available", False)
        if rust_avail:
            self.banner.setText(
                "<b style='color:#4CAF50'>✓ Rust Engine Binary gefunden</b>"
            )
        else:
            self.banner.setText(
                "<b style='color:#FF9800'>⚠ Rust Engine Binary nicht gefunden</b><br>"
                "<i>Build: cd pydaw_engine && cargo build --release</i>"
            )

        # Subsystem states
        subs = summary.get("subsystems", {})
        rows = {
            "audio_playback": self.row_audio,
            "midi_dispatch": self.row_midi,
            "plugin_hosting": self.row_plugin,
        }
        for name, row in rows.items():
            info = subs.get(name, {})
            row.setEnabled(rust_avail)
            # Block signals to prevent re-trigger
            row.cb_rust.blockSignals(True)
            row.set_state(
                backend=info.get("backend", "python"),
                status=info.get("status", "active"),
                error=info.get("error", ""),
            )
            row.cb_rust.blockSignals(False)

        # Enable "Rust as default" only if all on Rust+active
        all_rust_active = all(
            subs.get(s, {}).get("backend") == "rust" and subs.get(s, {}).get("status") == "active"
            for s in rows
        )
        self.cb_default.setEnabled(all_rust_active)
        self.cb_default.blockSignals(True)
        self.cb_default.setChecked(summary.get("rust_as_default", False))
        self.cb_default.blockSignals(False)

        self.btn_migrate_all.setEnabled(rust_avail)
        self.btn_benchmark.setEnabled(True)

    # --- Slots ---------------------------------------------------------------

    def _on_subsystem_toggled(self, subsystem: str, on: bool):
        """Handle subsystem checkbox toggle."""
        try:
            from pydaw.services.engine_migration import EngineMigrationController
            ctrl = EngineMigrationController.instance()
            backend = "rust" if on else "python"
            ok = ctrl.set_subsystem(subsystem, backend)
            if not ok:
                # Revert checkbox
                QTimer.singleShot(0, self._refresh_state)
        except Exception as e:
            log.error("Subsystem toggle error: %s", e)
            QTimer.singleShot(0, self._refresh_state)

    def _on_migrate_all(self):
        """Migrate all subsystems to Rust."""
        try:
            from pydaw.services.engine_migration import EngineMigrationController
            ctrl = EngineMigrationController.instance()
            ctrl.migrate_all_to_rust()
        except Exception as e:
            log.error("Migrate all error: %s", e)
        self._refresh_state()

    def _on_rollback_all(self):
        """Roll back all subsystems to Python."""
        try:
            from pydaw.services.engine_migration import EngineMigrationController
            ctrl = EngineMigrationController.instance()
            ctrl.rollback_all_to_python()
        except Exception as e:
            log.error("Rollback error: %s", e)
        self._refresh_state()

    def _on_benchmark(self):
        """Run performance benchmark."""
        self.grp_bench.setVisible(True)
        self.bench_progress.setVisible(True)
        self.bench_progress.setValue(0)
        self.bench_text.setPlainText("Benchmark läuft...")
        self.btn_benchmark.setEnabled(False)

        try:
            from pydaw.services.engine_benchmark import EnginePerformanceBenchmark
            bench = EnginePerformanceBenchmark()
            bench.progress.connect(self._on_bench_progress)
            bench.finished.connect(self._on_bench_finished)
            bench.run_benchmark_async(duration_sec=3.0)
        except Exception as e:
            self.bench_text.setPlainText(f"Benchmark Fehler: {e}")
            self.btn_benchmark.setEnabled(True)

    def _on_bench_progress(self, current: int, total: int, message: str):
        """Update benchmark progress."""
        self.bench_progress.setMaximum(total)
        self.bench_progress.setValue(current)

    def _on_bench_finished(self, report: Any):
        """Display benchmark results."""
        try:
            from pydaw.services.engine_benchmark import EnginePerformanceBenchmark
            text = EnginePerformanceBenchmark.format_report(report)
            self.bench_text.setPlainText(text)
        except Exception as e:
            self.bench_text.setPlainText(f"Ergebnis-Formatierung fehlgeschlagen: {e}")
        self.bench_progress.setVisible(False)
        self.btn_benchmark.setEnabled(True)

    def _on_default_toggled(self, checked: bool):
        """Set Rust as default engine."""
        try:
            from pydaw.services.engine_migration import EngineMigrationController
            ctrl = EngineMigrationController.instance()
            ctrl.set_rust_as_default(checked)
        except Exception:
            pass

    def _on_migration_changed(self, subsystem: str, backend: str, status: str):
        """React to migration controller changes."""
        self._refresh_state()

    def _on_migration_error(self, subsystem: str, message: str):
        """Display migration error."""
        log.warning("Migration error %s: %s", subsystem, message)
        self._refresh_state()


class EngineMigrationDialog(QDialog):
    """Standalone dialog wrapping EngineMigrationWidget."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Engine Migration — Python ↔ Rust")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        self.widget = EngineMigrationWidget(self)
        layout.addWidget(self.widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)
