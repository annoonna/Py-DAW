"""Project Compare Dialog (v0.0.20.85).

UI: Menü → Projekt → Projekt vergleichen…

Purpose:
    When multiple projects are open in tabs, it can be hard to understand what
    changed (routing, devices, clips, settings). This dialog provides a safe,
    read-only diff between two open project tabs.

Safety:
    - Never throws (best-effort only). Any failure results in a readable
      message instead of crashing the app.
    - No mutations to project state.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


try:
    from pydaw.services.project_tab_service import ProjectTabService, ProjectTab
except Exception:  # pragma: no cover
    ProjectTabService = object  # type: ignore
    ProjectTab = object  # type: ignore


@dataclass
class _TabInfo:
    idx: int
    title: str


def _safe_json(project_obj: object, ignore_timestamps: bool = True) -> str:
    """Serialize project to stable JSON for diff.

    - sort_keys=True to keep ordering stable
    - ignore_timestamps removes noisy fields that otherwise always differ
    """
    try:
        d = getattr(project_obj, "to_dict", None)
        data = d() if callable(d) else None
        if not isinstance(data, dict):
            return "(Konnte Projekt nicht serialisieren: to_dict() liefert kein dict)"

        if ignore_timestamps:
            data = dict(data)
            data.pop("created_utc", None)
            data.pop("modified_utc", None)

        return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    except Exception as exc:
        return f"(Konnte Projekt nicht serialisieren: {exc})"


def _project_summary(project_obj: object) -> str:
    try:
        name = getattr(project_obj, "name", "") or "(ohne Name)"
        ver = getattr(project_obj, "version", "") or ""
        bpm = getattr(project_obj, "bpm", None)
        sr = getattr(project_obj, "sample_rate", None)
        ts = getattr(project_obj, "time_signature", None)
        snap = getattr(project_obj, "snap_division", None)

        tracks = list(getattr(project_obj, "tracks", []) or [])
        clips = list(getattr(project_obj, "clips", []) or [])
        media = list(getattr(project_obj, "media", []) or [])
        midi_notes = getattr(project_obj, "midi_notes", {}) or {}

        kind_counts = {}
        for t in tracks:
            k = str(getattr(t, "kind", "?"))
            kind_counts[k] = kind_counts.get(k, 0) + 1

        notes_total = 0
        if isinstance(midi_notes, dict):
            for _cid, nl in midi_notes.items():
                if isinstance(nl, list):
                    notes_total += len(nl)

        out = []
        out.append(f"Name: {name}")
        if ver:
            out.append(f"Version: {ver}")
        if bpm is not None:
            out.append(f"BPM: {bpm}")
        if sr is not None:
            out.append(f"Sample-Rate: {sr}")
        if ts:
            out.append(f"Taktart: {ts}")
        if snap:
            out.append(f"Snap: {snap}")

        out.append("")
        out.append(
            f"Tracks: {len(tracks)}  ("
            + ", ".join([f"{k}={v}" for k, v in sorted(kind_counts.items())])
            + ")"
        )
        out.append(f"Clips:  {len(clips)}")
        out.append(f"Media:  {len(media)}")
        out.append(f"MIDI Notes (total): {notes_total}")

        return "\n".join(out)
    except Exception as exc:
        return f"(Konnte Summary nicht erstellen: {exc})"


class ProjectCompareDialog(QDialog):
    """Compare two open project tabs (read-only)."""

    def __init__(self, tab_service: ProjectTabService, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Projekt vergleichen")
        self.setModal(False)
        self.resize(980, 680)

        self._tabs: list[_TabInfo] = []
        self._svc = tab_service

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # --- header / selection row
        row = QHBoxLayout()
        row.setSpacing(8)
        root.addLayout(row)

        row.addWidget(QLabel("Projekt A:"), 0)
        self.cmb_a = QComboBox()
        self.cmb_a.setMinimumWidth(260)
        row.addWidget(self.cmb_a, 1)

        row.addWidget(QLabel("Projekt B:"), 0)
        self.cmb_b = QComboBox()
        self.cmb_b.setMinimumWidth(260)
        row.addWidget(self.cmb_b, 1)

        self.btn_swap = QPushButton("↔")
        self.btn_swap.setToolTip("A/B tauschen")
        self.btn_swap.setFixedWidth(46)
        row.addWidget(self.btn_swap, 0)

        self.btn_refresh = QPushButton("Aktualisieren")
        self.btn_refresh.setToolTip("Diff/Summary neu berechnen")
        row.addWidget(self.btn_refresh, 0)

        # --- options row
        opt = QHBoxLayout()
        opt.setSpacing(12)
        root.addLayout(opt)

        self.chk_ignore_ts = QCheckBox("Zeitstempel ignorieren (created/modified)")
        self.chk_ignore_ts.setChecked(True)
        opt.addWidget(self.chk_ignore_ts, 0)
        opt.addStretch(1)

        hint = QLabel("Tipp: Shortcut im Menü: Ctrl+Alt+D")
        hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hint.setStyleSheet("color:#9E9E9E;")
        opt.addWidget(hint, 1)

        # --- content tabs
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.txt_summary = QTextEdit()
        self.txt_summary.setReadOnly(True)
        self._set_mono(self.txt_summary)

        self.txt_diff = QTextEdit()
        self.txt_diff.setReadOnly(True)
        self._set_mono(self.txt_diff)

        self.tabs.addTab(self.txt_summary, "Summary")
        self.tabs.addTab(self.txt_diff, "Diff")

        # --- footer
        foot = QHBoxLayout()
        root.addLayout(foot)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color:#9E9E9E;")
        foot.addWidget(self.lbl_status, 1)
        self.btn_close = QPushButton("Schließen")
        self.btn_close.clicked.connect(self.close)
        foot.addWidget(self.btn_close, 0)

        # wiring
        self.btn_swap.clicked.connect(self._swap)
        self.btn_refresh.clicked.connect(self.refresh)
        self.cmb_a.currentIndexChanged.connect(lambda _=0: self.refresh())
        self.cmb_b.currentIndexChanged.connect(lambda _=0: self.refresh())
        self.chk_ignore_ts.toggled.connect(lambda _=False: self.refresh())

        # Populate selections
        self._populate_tabs()
        self._set_defaults()
        self.refresh()

    def _set_mono(self, te: QTextEdit) -> None:
        try:
            f = QFont("Monospace")
            f.setStyleHint(QFont.StyleHint.Monospace)
            te.setFont(f)
        except Exception:
            pass

    def _populate_tabs(self) -> None:
        self._tabs = []
        self.cmb_a.blockSignals(True)
        self.cmb_b.blockSignals(True)
        self.cmb_a.clear()
        self.cmb_b.clear()

        try:
            tabs = list(getattr(self._svc, "tabs", []) or [])
        except Exception:
            tabs = []

        for i, t in enumerate(tabs):
            try:
                name = getattr(t, "display_name", None)
                if callable(name):
                    name = name()
                name = str(name or f"Tab {i+1}")
                dirty = bool(getattr(t, "dirty", False))
                marker = " *" if dirty else ""
                title = f"{i+1}: {name}{marker}"
            except Exception:
                title = f"{i+1}: (unbekannt)"
            self._tabs.append(_TabInfo(idx=i, title=title))
            self.cmb_a.addItem(title, i)
            self.cmb_b.addItem(title, i)

        self.cmb_a.blockSignals(False)
        self.cmb_b.blockSignals(False)

        if len(self._tabs) < 2:
            self.lbl_status.setText("Hinweis: Zum Vergleichen müssen mindestens 2 Projekt-Tabs geöffnet sein.")

    def _set_defaults(self) -> None:
        try:
            active = int(getattr(self._svc, "active_index", 0) or 0)
        except Exception:
            active = 0

        if self.cmb_a.count() == 0:
            return

        self.cmb_a.setCurrentIndex(max(0, min(active, self.cmb_a.count() - 1)))
        # Choose a different default for B
        b = 1 if self.cmb_b.count() > 1 else 0
        if b == self.cmb_a.currentIndex() and self.cmb_b.count() > 1:
            b = 0 if self.cmb_a.currentIndex() != 0 else 1
        self.cmb_b.setCurrentIndex(max(0, min(b, self.cmb_b.count() - 1)))

    def _swap(self) -> None:
        a = self.cmb_a.currentIndex()
        b = self.cmb_b.currentIndex()
        self.cmb_a.setCurrentIndex(b)
        self.cmb_b.setCurrentIndex(a)

    def _tab_obj(self, idx: int) -> Optional[ProjectTab]:
        try:
            return self._svc.tab_at(idx)
        except Exception:
            return None

    def _project_obj(self, idx: int) -> Optional[object]:
        try:
            tab = self._tab_obj(idx)
            if not tab:
                return None
            return getattr(tab, "project", None)
        except Exception:
            return None

    def refresh(self) -> None:
        try:
            if self.cmb_a.count() < 2:
                self.txt_summary.setPlainText(
                    "Öffne mindestens zwei Projekte (Tabs), um einen Vergleich zu sehen.\n\n"
                    "Tipp: Datei → Öffnen in neuem Tab… (Ctrl+Shift+O)"
                )
                self.txt_diff.setPlainText("")
                return

            ia = int(self.cmb_a.currentData()) if self.cmb_a.currentData() is not None else self.cmb_a.currentIndex()
            ib = int(self.cmb_b.currentData()) if self.cmb_b.currentData() is not None else self.cmb_b.currentIndex()

            if ia == ib:
                self.txt_summary.setPlainText("Bitte zwei verschiedene Tabs auswählen.")
                self.txt_diff.setPlainText("")
                return

            pa = self._project_obj(ia)
            pb = self._project_obj(ib)
            if pa is None or pb is None:
                self.txt_summary.setPlainText("(Fehler: Konnte eines der Projekte nicht auflösen.)")
                self.txt_diff.setPlainText("")
                return

            # Summary
            sa = _project_summary(pa)
            sb = _project_summary(pb)
            s = []
            s.append("=== Projekt A ===")
            s.append(sa)
            s.append("")
            s.append("=== Projekt B ===")
            s.append(sb)
            self.txt_summary.setPlainText("\n".join(s))

            # Diff
            ignore_ts = bool(self.chk_ignore_ts.isChecked())
            ja = _safe_json(pa, ignore_timestamps=ignore_ts)
            jb = _safe_json(pb, ignore_timestamps=ignore_ts)
            la = ja.splitlines(keepends=False)
            lb = jb.splitlines(keepends=False)

            diff = difflib.unified_diff(
                la,
                lb,
                fromfile=f"A:{self.cmb_a.currentText()}",
                tofile=f"B:{self.cmb_b.currentText()}",
                lineterm="",
                n=3,
            )
            diff_text = "\n".join(list(diff))
            if not diff_text.strip():
                diff_text = "(Keine Unterschiede gefunden – oder nur Zeitstempel unterscheiden sich.)"
            self.txt_diff.setPlainText(diff_text)

            self.lbl_status.setText("Bereit.")
        except Exception as exc:
            self.lbl_status.setText(f"Fehler: {exc}")
            try:
                self.txt_summary.setPlainText(f"(Fehler beim Vergleichen: {exc})")
                self.txt_diff.setPlainText("")
            except Exception:
                pass
