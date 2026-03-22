"""AI Orchestrator dialog.

Adds a project tool that can create multiple instrument tracks and MIDI clips
in one operation (ensemble/orchestration). This is intentionally additive and
does not change existing editors.

v0.0.20.195
"""

from __future__ import annotations

from dataclasses import asdict
import traceback
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from pydaw.core.threading import Worker


def _grid_to_beats(label: str) -> float:
    # quarter note beat units (1 beat == 1/4)
    m = {
        "1/4": 1.0,
        "1/8": 0.5,
        "1/16": 0.25,
        "1/32": 0.125,
    }
    return float(m.get(str(label), 0.25))


class OrchestratorDialog(QDialog):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._ps = getattr(services, "project", None)
        self.setWindowTitle("AI Orchestrator – Ensemble erzeugen")
        self.setModal(True)
        self.resize(980, 620)

        # --- data sources
        try:
            from pydaw.music.ai_composer import GENRES, CONTEXTS, FORMS
        except Exception:
            GENRES = ("Barock (Bach/Fuge)", "Electro")
            CONTEXTS = ("Neutral",)
            FORMS = ("Mini-Fuge (Subject/Answer)",)
        try:
            from pydaw.music.ai_orchestrator import available_ensembles
            ensembles = list(available_ensembles())
        except Exception:
            ensembles = ["Kammermusik"]

        # --- layout
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Left: controls
        left = QVBoxLayout()
        left.setSpacing(8)

        gb = QGroupBox("Ensemble & Stil")
        form = QFormLayout(gb)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.cmb_ensemble = QComboBox()
        self.cmb_ensemble.addItems(ensembles)
        self.cmb_ensemble.setCurrentText("Kammermusik" if "Kammermusik" in ensembles else ensembles[0])

        self.cmb_context = QComboBox()
        self.cmb_context.addItems(list(CONTEXTS))
        self.cmb_context.setCurrentText("Neutral" if "Neutral" in CONTEXTS else CONTEXTS[0])

        self.cmb_genre_a = QComboBox()
        self.cmb_genre_a.setEditable(True)
        self.cmb_genre_a.addItems(list(GENRES))
        self.cmb_genre_a.setCurrentText("Barock (Bach/Fuge)" if "Barock (Bach/Fuge)" in GENRES else GENRES[0])

        self.cmb_genre_b = QComboBox()
        self.cmb_genre_b.setEditable(True)
        self.cmb_genre_b.addItems(list(GENRES))
        self.cmb_genre_b.setCurrentText("Electro" if "Electro" in GENRES else GENRES[min(1, len(GENRES)-1)])

        self.cmb_form = QComboBox()
        self.cmb_form.addItems(list(FORMS))
        self.cmb_form.setCurrentText("Mini-Fuge (Subject/Answer)" if "Mini-Fuge (Subject/Answer)" in FORMS else FORMS[0])

        self.spn_bars = QSpinBox()
        self.spn_bars.setRange(1, 64)
        self.spn_bars.setValue(8)

        self.cmb_grid = QComboBox()
        self.cmb_grid.addItems(["1/4", "1/8", "1/16", "1/32"])
        self.cmb_grid.setCurrentText("1/16")

        self.edt_swing = QLineEdit("0.00")
        self.edt_density = QLineEdit("0.65")
        self.edt_hybrid = QLineEdit("0.55")
        self.spn_seed = QSpinBox()
        self.spn_seed.setRange(1, 9999999)
        self.spn_seed.setValue(1)

        self.chk_start_playhead = QCheckBox("Start bei Playhead (auf Bar gesnappt)")
        self.chk_start_playhead.setChecked(True)

        self.edt_prefix = QLineEdit("AI")
        self.edt_prefix.setPlaceholderText("Prefix für Track-Namen (optional)")

        form.addRow("Ensemble:", self.cmb_ensemble)
        form.addRow("Kontext:", self.cmb_context)
        form.addRow("Genre A (Struktur):", self.cmb_genre_a)
        form.addRow("Genre B (Rhythm):", self.cmb_genre_b)
        form.addRow("Form:", self.cmb_form)
        form.addRow("Länge (Bars):", self.spn_bars)
        form.addRow("Grid:", self.cmb_grid)
        form.addRow("Swing (0..1):", self.edt_swing)
        form.addRow("Density (0..1):", self.edt_density)
        form.addRow("Hybrid (0..1):", self.edt_hybrid)
        form.addRow("Seed:", self.spn_seed)
        form.addRow("Start:", self.chk_start_playhead)
        form.addRow("Track-Prefix:", self.edt_prefix)

        left.addWidget(gb)

        self.txt_help = QTextEdit()
        self.txt_help.setReadOnly(True)
        self.txt_help.setMinimumHeight(120)
        self.txt_help.setPlaceholderText("Hinweise…")
        left.addWidget(self.txt_help)

        btn_row = QHBoxLayout()
        self.btn_preview = QPushButton("Preview Parts")
        self.btn_generate = QPushButton("Spuren + Clips erzeugen")
        self.btn_generate.setDefault(True)
        btn_row.addWidget(self.btn_preview)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_generate)
        left.addLayout(btn_row)

        # Buttons bottom
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        left.addWidget(bb)

        # Right: parts table
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(QLabel("Instrument-Spuren (wähle aus, was erzeugt werden soll):"))

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["Aktiv", "Spur", "Rolle", "Range"])
        try:
            self.tbl.horizontalHeader().setStretchLastSection(True)
            self.tbl.horizontalHeader().setDefaultSectionSize(160)
        except Exception:
            pass
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        right.addWidget(self.tbl, 1)

        root.addLayout(left, 0)
        root.addLayout(right, 1)

        # signals
        self.cmb_ensemble.currentTextChanged.connect(self._refresh_parts)
        self.cmb_context.currentTextChanged.connect(self._refresh_help)
        self.cmb_genre_a.currentTextChanged.connect(self._refresh_help)
        self.cmb_genre_b.currentTextChanged.connect(self._refresh_help)
        self.btn_preview.clicked.connect(self._preview)
        self.btn_generate.clicked.connect(self._generate)

        self._refresh_parts()
        self._refresh_help()

    # ----------------- UI helpers -----------------

    def _refresh_help(self) -> None:
        ens = self.cmb_ensemble.currentText().strip()
        ctx = self.cmb_context.currentText().strip()
        ga = self.cmb_genre_a.currentText().strip()
        gb = self.cmb_genre_b.currentText().strip()
        bars = self.spn_bars.value()
        self.txt_help.setPlainText(
            "Dieser Assistent erzeugt mehrere Instrument-Spuren + MIDI-Clips in einem Schritt.\n"
            "Du weist danach die echten Instrumente zu (SF2/Sampler/Orgel/etc.).\n\n"
            f"Ensemble: {ens}\nKontext: {ctx}\nStil: {ga} × {gb}\nBars: {bars}\n\n"
            "Tipp: Genre-Felder sind editierbar – du kannst jeden Stil eintippen.\n"
            "Die Parts sind deterministisch über den Seed reproduzierbar."
        )

    def _refresh_parts(self) -> None:
        try:
            from pydaw.music.ai_orchestrator import ENSEMBLES
            specs = ENSEMBLES.get(self.cmb_ensemble.currentText().strip(), ())
        except Exception:
            specs = ()

        self.tbl.setRowCount(0)
        for spec in specs:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            chk = QTableWidgetItem("✔")
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked)
            self.tbl.setItem(r, 0, chk)

            self.tbl.setItem(r, 1, QTableWidgetItem(str(spec.name)))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(spec.role)))
            self.tbl.setItem(r, 3, QTableWidgetItem(f"{spec.low}..{spec.high}"))

        try:
            self.tbl.resizeColumnsToContents()
        except Exception:
            pass

        self._refresh_help()

    def _selected_part_names(self) -> List[str]:
        out: List[str] = []
        for r in range(self.tbl.rowCount()):
            it = self.tbl.item(r, 0)
            nm = self.tbl.item(r, 1)
            if not it or not nm:
                continue
            if it.checkState() == Qt.CheckState.Checked:
                out.append(str(nm.text()))
        return out

    # ----------------- Actions -----------------

    def _build_params(self):
        from pydaw.music.ai_composer import ComposerParams
        # Genre fields are editable. We keep "Custom" plumbing out of the dialog:
        # we simply put strings into genre_a/genre_b directly.
        try:
            swing = float(self.edt_swing.text().strip() or "0")
        except Exception:
            swing = 0.0
        try:
            density = float(self.edt_density.text().strip() or "0.65")
        except Exception:
            density = 0.65
        try:
            hybrid = float(self.edt_hybrid.text().strip() or "0.55")
        except Exception:
            hybrid = 0.55

        return ComposerParams(
            genre_a=str(self.cmb_genre_a.currentText().strip() or "Barock (Bach/Fuge)"),
            genre_b=str(self.cmb_genre_b.currentText().strip() or "Electro"),
            custom_genre_a="",
            custom_genre_b="",
            context=str(self.cmb_context.currentText().strip() or "Neutral"),
            form=str(self.cmb_form.currentText().strip() or "Mini-Fuge (Subject/Answer)"),
            instrument_setup="Volles Orchester",
            bars=int(self.spn_bars.value()),
            grid=float(_grid_to_beats(self.cmb_grid.currentText())),
            swing=float(max(0.0, min(1.0, swing))),
            density=float(max(0.0, min(1.0, density))),
            hybrid=float(max(0.0, min(1.0, hybrid))),
            seed=int(self.spn_seed.value()),
        )

    def _preview(self) -> None:
        # A light preview: just show part list summary
        parts = self._selected_part_names()
        if not parts:
            QMessageBox.information(self, "AI Orchestrator", "Keine Parts ausgewählt.")
            return
        QMessageBox.information(self, "AI Orchestrator", "Erzeugt werden:\n\n" + "\n".join(parts))

    def _generate(self) -> None:
        if self._ps is None:
            QMessageBox.warning(self, "AI Orchestrator", "ProjectService nicht verfügbar.")
            return

        parts = self._selected_part_names()
        if not parts:
            QMessageBox.information(self, "AI Orchestrator", "Keine Parts ausgewählt.")
            return

        # Determine start beat
        start = 0.0
        try:
            transport = getattr(self._services, "transport", None)
            start = float(getattr(transport, "current_beat", 0.0) if transport is not None else 0.0)
        except Exception:
            start = 0.0

        try:
            ts = str(getattr(self._ps.ctx.project, "time_signature", "4/4") or "4/4")
        except Exception:
            ts = "4/4"

        if self.chk_start_playhead.isChecked():
            try:
                from pydaw.music.ai_composer import beats_per_bar
                bpb = float(beats_per_bar(ts))
                if bpb > 0:
                    start = float(int(start // bpb) * bpb)
            except Exception:
                pass
        else:
            start = 0.0

        params = self._build_params()
        ensemble = self.cmb_ensemble.currentText().strip()
        prefix = self.edt_prefix.text().strip()
        prefix = prefix + " " if prefix else ""

        # --- background generation (fast, but keep UI responsive)
        def fn():
            from pydaw.music.ai_orchestrator import build_parts
            parts_notes = build_parts(time_signature=ts, params=params, ensemble=ensemble, selected_parts=parts)
            # serialize minimal
            out: Dict[str, List[dict]] = {}
            for name, notes in parts_notes.items():
                out[name] = [
                    {
                        "pitch": int(n.pitch),
                        "start_beats": float(n.start_beats),
                        "length_beats": float(n.length_beats),
                        "velocity": int(n.velocity),
                    }
                    for n in (notes or [])
                ]
            return out

        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Erzeuge…")

        w = Worker(fn)

        def ok(res):
            try:
                self._apply_to_project(res, ts, params, ensemble, start, prefix)
                QMessageBox.information(self, "AI Orchestrator", "Ensemble erzeugt. Du kannst jetzt die Instrumente pro Spur zuweisen.")
            except Exception as e:
                traceback.print_exc()
                QMessageBox.warning(self, "AI Orchestrator", f"Fehler beim Anwenden: {e}")
            finally:
                self.btn_generate.setEnabled(True)
                self.btn_generate.setText("Spuren + Clips erzeugen")

        def err(msg: str):
            try:
                QMessageBox.warning(self, "AI Orchestrator", f"Generierung fehlgeschlagen: {msg}")
            except Exception:
                pass
            self.btn_generate.setEnabled(True)
            self.btn_generate.setText("Spuren + Clips erzeugen")

        w.signals.result.connect(ok)
        w.signals.error.connect(err)
        try:
            self._ps.threadpool.submit(w)
        except Exception:
            # fallback: run in UI thread (should still be fast)
            try:
                ok(fn())
            except Exception as exc:
                err(str(exc))

    def _apply_to_project(self, res: Dict[str, List[dict]], ts: str, params, ensemble: str, start_beats: float, prefix: str) -> None:
        """Apply generated notes to the project: create tracks + clips."""
        ps = self._ps
        if ps is None:
            return

        # compute clip length
        try:
            from pydaw.music.ai_composer import beats_per_bar
            bpb = float(beats_per_bar(ts))
        except Exception:
            bpb = 4.0
        length_beats = float(max(1, int(getattr(params, "bars", 8) or 8))) * float(bpb)

        # create tracks and clips in declared order
        existing_ids = set(t.id for t in ps.ctx.project.tracks)

        for part_name, notes_dicts in res.items():
            # add track
            ps.add_track("instrument")
            # find new track id
            new_track_id = ""
            for t in ps.ctx.project.tracks:
                if t.id not in existing_ids and t.kind != "master":
                    new_track_id = t.id
                    break
            if not new_track_id:
                # fallback: last non-master
                non_master = [t for t in ps.ctx.project.tracks if t.kind != "master"]
                new_track_id = non_master[-1].id if non_master else ""
            existing_ids.add(new_track_id)

            # rename + store hint
            track_label = f"{prefix}{part_name}".strip()
            try:
                ps.rename_track(str(new_track_id), track_label)
            except Exception:
                pass
            try:
                trk = next((t for t in ps.ctx.project.tracks if t.id == str(new_track_id)), None)
                if trk is not None:
                    trk.instrument_state.setdefault("ai_orchestrator", {})
                    trk.instrument_state["ai_orchestrator"].update(
                        {
                            "ensemble": str(ensemble),
                            "suggested_instrument": str(part_name),
                            "params": asdict(params),
                        }
                    )
            except Exception:
                pass

            # add clip
            clip_id = ps.add_midi_clip_at(str(new_track_id), start_beats=float(start_beats), length_beats=float(length_beats), label=f"{part_name} Clip")

            # apply notes with undo step
            before = ps.snapshot_midi_notes(str(clip_id))
            from pydaw.model.midi import MidiNote
            notes = []
            for d in (notes_dicts or []):
                try:
                    notes.append(
                        MidiNote(
                            pitch=int(d.get("pitch", 60)),
                            start_beats=float(d.get("start_beats", 0.0)),
                            length_beats=float(d.get("length_beats", 1.0)),
                            velocity=int(d.get("velocity", 100)),
                        ).clamp()
                    )
                except Exception:
                    continue

            ps.set_midi_notes(str(clip_id), notes)
            ps.commit_midi_notes_edit(str(clip_id), before, label=f"AI Orchestrator: {ensemble}")
