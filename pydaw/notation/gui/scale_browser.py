from pydaw.notation.qt_compat import (
    QWidget, QVBoxLayout, QLabel, QComboBox,
    QPushButton, QSlider, QCheckBox
)
from pydaw.notation.qt_compat import Qt
from pydaw.notation.scales.database import SCALE_DB
from pydaw.notation.audio.playback_worker import PlaybackWorker


class ScaleBrowser(QWidget):
    def __init__(self, score_view):
        super().__init__()
        self.score = score_view
        self.worker = None

        layout = QVBoxLayout(self)

        # Auswahl
        self.system_box = QComboBox()
        self.system_box.addItems(SCALE_DB.list_systems())

        self.scale_box = QComboBox()

        # Tempo
        self.tempo = QSlider(Qt.Horizontal)
        self.tempo.setRange(40, 240)
        self.tempo.setValue(120)

        # Loop
        self.loop = QCheckBox("Loop")

        # Transport
        self.play_scale = QPushButton("▶ Skala")
        self.play_seq = QPushButton("▶ Eigene Noten")
        self.stop_btn = QPushButton("⏹ Stop")

        # Clear
        self.clear_btn = QPushButton("🧹 Alles löschen")

        # Layout
        layout.addWidget(QLabel("System"))
        layout.addWidget(self.system_box)
        layout.addWidget(QLabel("Skala"))
        layout.addWidget(self.scale_box)
        layout.addWidget(QLabel("Tempo"))
        layout.addWidget(self.tempo)
        layout.addWidget(self.loop)

        layout.addWidget(self.play_scale)
        layout.addWidget(self.play_seq)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.clear_btn)

        # Signale
        self.system_box.currentTextChanged.connect(self.update_scales)
        self.play_scale.clicked.connect(self.play_scale_notes)
        self.play_seq.clicked.connect(self.play_sequence)
        self.stop_btn.clicked.connect(self.stop_all)
        self.clear_btn.clicked.connect(self.clear_all)

        self.update_scales(self.system_box.currentText())

    # ---------- Steuerung ----------
    def stop_all(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            self.worker = None
        self.score.highlight_note(-1)

    def clear_all(self):
        self.stop_all()
        self.score.clear_all()

    # ---------- Daten ----------
    def update_scales(self, system):
        self.scale_box.clear()
        self.scale_box.addItems(SCALE_DB.list_scales(system))

    # ---------- Playback ----------
    def play_scale_notes(self):
        self.stop_all()
        self.score.clear_all()

        scale = SCALE_DB.get_scale(
            self.system_box.currentText(),
            self.scale_box.currentText()
        )

        midi_notes = [60 + round(c / 100) for c in scale["intervals_cent"]]
        self.score.draw_notes(midi_notes)

        self.start_worker(lambda: midi_notes, use_automation=False)

    def play_sequence(self):
        self.stop_all()
        # Wiedergabe exakt nach Zeichnung (Start/Dauer/Pausen/Ties)
        self.start_worker(self.score.get_playback_events, use_automation=True)

    def start_worker(self, notes_provider, use_automation: bool = False):
        self.worker = PlaybackWorker(
            notes_provider=notes_provider,
            tempo_provider=lambda: self.tempo.value(),
            loop_provider=lambda: self.loop.isChecked(),
            volume_provider=self.score.get_master_volume,
            automation_provider=(lambda: self.score.get_volume_automation_lane()) if use_automation else (lambda: None),
            start_beat_provider=self.score.get_playhead_beat,
            loop_range_provider=self.score.get_loop_range,
        )
        self.worker.note_changed.connect(self.score.highlight_note)
        self.worker.start()
