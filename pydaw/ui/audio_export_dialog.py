"""Professional Audio Export Dialog (Studio-Style) for PyDAW.

Features:
- Format selection: WAVE, FLAC, OGG, MP3
- Quality/Bit-depth settings
- Track selection (multi-select)
- Time range: Arrangement / Loop-Region
- Sampling rate selection
- Options: Realtime, Dither, Pre-Fader, Open after export
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QGroupBox,
    QButtonGroup,
    QRadioButton,
    QFileDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class AudioExportDialog(QDialog):
    """Professional audio export dialog like a modern DAW."""
    
    def __init__(self, project_service: Any, parent=None):
        super().__init__(parent)
        self.project = project_service
        self.selected_format = "wav"
        self.selected_quality = "16bit"
        self.export_path: Optional[Path] = None
        
        self.setWindowTitle("Audio exportieren")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        
        self._build_ui()
    
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Title
        title = QLabel("Audio exportieren")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Format Selection Group
        format_group = QGroupBox("Format(e)")
        format_layout = QHBoxLayout(format_group)
        
        self.btn_group_format = QButtonGroup()
        
        self.btn_wav = QPushButton("WAVE")
        self.btn_wav.setCheckable(True)
        self.btn_wav.setChecked(True)
        self.btn_wav.setMinimumHeight(35)
        self.btn_wav.clicked.connect(lambda: self._on_format_changed("wav"))
        self.btn_group_format.addButton(self.btn_wav)
        format_layout.addWidget(self.btn_wav)
        
        self.btn_flac = QPushButton("FLAC")
        self.btn_flac.setCheckable(True)
        self.btn_flac.setMinimumHeight(35)
        self.btn_flac.clicked.connect(lambda: self._on_format_changed("flac"))
        self.btn_group_format.addButton(self.btn_flac)
        format_layout.addWidget(self.btn_flac)
        
        self.btn_ogg = QPushButton("OGG")
        self.btn_ogg.setCheckable(True)
        self.btn_ogg.setMinimumHeight(35)
        self.btn_ogg.clicked.connect(lambda: self._on_format_changed("ogg"))
        self.btn_group_format.addButton(self.btn_ogg)
        format_layout.addWidget(self.btn_ogg)
        
        self.btn_mp3 = QPushButton("MP3")
        self.btn_mp3.setCheckable(True)
        self.btn_mp3.setMinimumHeight(35)
        self.btn_mp3.setStyleSheet("QPushButton:checked { background-color: #ff8800; }")
        self.btn_mp3.clicked.connect(lambda: self._on_format_changed("mp3"))
        self.btn_group_format.addButton(self.btn_mp3)
        format_layout.addWidget(self.btn_mp3)
        
        layout.addWidget(format_group)
        
        # Quality Selection
        quality_layout = QHBoxLayout()
        
        self.cmb_quality = QComboBox()
        self.cmb_quality.addItem("16-bit", "16bit")
        self.cmb_quality.addItem("24-bit", "24bit")
        self.cmb_quality.addItem("32-bit", "32bit")
        self.cmb_quality.setMinimumHeight(30)
        quality_layout.addWidget(self.cmb_quality)
        
        quality_layout.addStretch(1)
        layout.addLayout(quality_layout)
        
        # Main content (Tracks + Time Range + Options)
        content_layout = QHBoxLayout()
        
        # LEFT: Tracks List
        tracks_group = QGroupBox("Spuren")
        tracks_layout = QVBoxLayout(tracks_group)
        
        self.tracks_list = QListWidget()
        self.tracks_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        
        # Add Project Master
        item = QListWidgetItem("🎚️ Project Master")
        item.setData(Qt.ItemDataRole.UserRole, "master")
        self.tracks_list.addItem(item)
        item.setSelected(True)  # Default: Master selected
        
        # Add all tracks from project
        for track in self.project.ctx.project.tracks:
            track_name = getattr(track, "name", "Track")
            track_kind = getattr(track, "kind", "audio")
            
            if track_kind == "audio":
                icon = "🔊"
            elif track_kind == "instrument":
                icon = "🎹"
            elif track_kind == "master":
                continue  # Already added as Project Master
            else:
                icon = "🎚️"
            
            item = QListWidgetItem(f"{icon} {track_name}")
            item.setData(Qt.ItemDataRole.UserRole, track.id)
            self.tracks_list.addItem(item)
            item.setSelected(True)  # Default: All selected
        
        tracks_layout.addWidget(self.tracks_list)
        content_layout.addWidget(tracks_group, 1)
        
        # RIGHT: Time Range + Options
        right_layout = QVBoxLayout()
        
        # Time Range
        time_group = QGroupBox("Zeitabschnitt")
        time_layout = QVBoxLayout(time_group)
        
        # From/To
        from_layout = QHBoxLayout()
        from_layout.addWidget(QLabel("Von"))
        self.lbl_from = QLabel("1.1.1.00")
        self.lbl_from.setStyleSheet("QLabel { color: #00aaff; font-size: 18px; font-weight: bold; }")
        from_layout.addWidget(self.lbl_from)
        from_layout.addStretch(1)
        time_layout.addLayout(from_layout)
        
        to_layout = QHBoxLayout()
        to_layout.addWidget(QLabel("Bis"))
        self.lbl_to = QLabel("49.1.1.00")
        self.lbl_to.setStyleSheet("QLabel { color: #00aaff; font-size: 18px; font-weight: bold; }")
        to_layout.addWidget(self.lbl_to)
        to_layout.addStretch(1)
        time_layout.addLayout(to_layout)
        
        # Arrangement / Loop-Region buttons
        range_buttons = QHBoxLayout()
        self.btn_arrangement = QPushButton("⚙️ Arrangement")
        self.btn_arrangement.setCheckable(True)
        self.btn_arrangement.setChecked(True)
        self.btn_arrangement.clicked.connect(self._on_arrangement_clicked)
        range_buttons.addWidget(self.btn_arrangement)
        
        self.btn_loop = QPushButton("🔁 Loop-Region")
        self.btn_loop.setCheckable(True)
        self.btn_loop.clicked.connect(self._on_loop_clicked)
        range_buttons.addWidget(self.btn_loop)
        
        time_layout.addLayout(range_buttons)
        right_layout.addWidget(time_group)
        
        # Sampling Rate
        sr_group = QGroupBox("Sampling-Rate")
        sr_layout = QVBoxLayout(sr_group)
        
        self.cmb_samplerate = QComboBox()
        self.cmb_samplerate.addItem("Aktuelle", "current")
        self.cmb_samplerate.addItem("44100 Hz", 44100)
        self.cmb_samplerate.addItem("48000 Hz", 48000)
        self.cmb_samplerate.addItem("88200 Hz", 88200)
        self.cmb_samplerate.addItem("96000 Hz", 96000)
        sr_layout.addWidget(self.cmb_samplerate)
        right_layout.addWidget(sr_group)
        
        # Options
        options_group = QGroupBox("Optionen")
        options_layout = QVBoxLayout(options_group)
        
        self.chk_realtime = QCheckBox("Echtzeit")
        self.chk_realtime.setChecked(True)
        options_layout.addWidget(self.chk_realtime)
        
        self.chk_dither = QCheckBox("Dither (TPDF)")
        self.chk_dither.setChecked(True)
        options_layout.addWidget(self.chk_dither)

        self.cmb_dither_type = QComboBox()
        self.cmb_dither_type.addItem("TPDF (Standard)", "tpdf")
        self.cmb_dither_type.addItem("POW-R Type 1", "pow_r")
        self.cmb_dither_type.addItem("Keines", "none")
        options_layout.addWidget(self.cmb_dither_type)

        self.cmb_normalize = QComboBox()
        self.cmb_normalize.addItem("Keine Normalisierung", "none")
        self.cmb_normalize.addItem("Peak -0.3 dBFS", "peak")
        self.cmb_normalize.addItem("LUFS -14 (Streaming)", "lufs")
        options_layout.addWidget(self.cmb_normalize)

        # v0.0.20.650: Pre-/Post-FX Export (AP10 Phase 10B Task 4)
        self.cmb_fx_mode = QComboBox()
        self.cmb_fx_mode.addItem("Post-FX (mit Effekten)", "post_fx")
        self.cmb_fx_mode.addItem("Pre-FX (Dry / ohne Effekte)", "pre_fx")
        self.cmb_fx_mode.addItem("Beides (Wet + Dry)", "both")
        options_layout.addWidget(self.cmb_fx_mode)

        self.chk_prefader = QCheckBox("Pre-Fader")
        options_layout.addWidget(self.chk_prefader)
        
        self.chk_open_after = QCheckBox("Nach Export Zielordner öffnen")
        self.chk_open_after.setChecked(True)
        options_layout.addWidget(self.chk_open_after)
        
        right_layout.addWidget(options_group)
        right_layout.addStretch(1)
        
        content_layout.addLayout(right_layout, 1)
        layout.addLayout(content_layout)
        
        # Bottom Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setMinimumWidth(100)
        self.btn_ok.setMinimumHeight(35)
        self.btn_ok.clicked.connect(self._on_ok)
        button_layout.addWidget(self.btn_ok)
        
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.setMinimumWidth(100)
        self.btn_cancel.setMinimumHeight(35)
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(button_layout)
        
        # Update time range from project
        self._update_time_range()
    
    def _on_format_changed(self, format_name: str) -> None:
        """Format button clicked."""
        self.selected_format = format_name
        
        # Update quality options based on format
        self.cmb_quality.clear()
        
        if format_name in ("wav", "flac"):
            # Lossless formats: bit depth
            self.cmb_quality.addItem("16-bit", "16bit")
            self.cmb_quality.addItem("24-bit", "24bit")
            self.cmb_quality.addItem("32-bit", "32bit")
        elif format_name == "mp3":
            # MP3: bitrate
            self.cmb_quality.addItem("128kbit/s", "128k")
            self.cmb_quality.addItem("192kbit/s", "192k")
            self.cmb_quality.addItem("256kbit/s", "256k")
            self.cmb_quality.addItem("320kbit/s (CBR)", "320k")
            self.cmb_quality.setCurrentIndex(3)  # 320k default
        elif format_name == "ogg":
            # OGG: quality
            self.cmb_quality.addItem("Quality 3 (~112kbit/s)", "q3")
            self.cmb_quality.addItem("Quality 5 (~160kbit/s)", "q5")
            self.cmb_quality.addItem("Quality 7 (~224kbit/s)", "q7")
            self.cmb_quality.addItem("Quality 10 (~500kbit/s)", "q10")
            self.cmb_quality.setCurrentIndex(2)  # q7 default
    
    def _on_arrangement_clicked(self) -> None:
        """Arrangement button clicked."""
        if self.btn_arrangement.isChecked():
            self.btn_loop.setChecked(False)
            self._update_time_range()
    
    def _on_loop_clicked(self) -> None:
        """Loop-Region button clicked."""
        if self.btn_loop.isChecked():
            self.btn_arrangement.setChecked(False)
            self._update_time_range_loop()
    
    def _update_time_range(self) -> None:
        """Update time range labels for full arrangement."""
        # Calculate project length
        max_beat = 0.0
        for clip in self.project.ctx.project.clips:
            clip_end = float(getattr(clip, "start_beats", 0.0)) + float(getattr(clip, "length_beats", 0.0))
            max_beat = max(max_beat, clip_end)
        
        # Convert to bars.beats.ticks format
        bpm = float(getattr(self.project.ctx.project, "bpm", 120.0))
        time_sig = getattr(self.project.ctx.project, "time_signature", "4/4")
        beats_per_bar = int(time_sig.split("/")[0])
        
        # From: Always 1.1.1.00
        self.lbl_from.setText("1.1.1.00")
        
        # To: Calculate from max_beat
        bars = int(max_beat / beats_per_bar) + 1
        beats = int(max_beat % beats_per_bar) + 1
        self.lbl_to.setText(f"{bars}.{beats}.1.00")
    
    def _update_time_range_loop(self) -> None:
        """Update time range labels for loop region."""
        # Get loop region from transport (if available)
        # For now, use placeholder
        self.lbl_from.setText("1.1.1.00")
        self.lbl_to.setText("5.1.1.00")
    
    def _on_ok(self) -> None:
        """OK button clicked - start export."""
        # Get selected tracks
        selected_tracks = []
        for i in range(self.tracks_list.count()):
            item = self.tracks_list.item(i)
            if item.isSelected():
                track_id = item.data(Qt.ItemDataRole.UserRole)
                selected_tracks.append(track_id)
        
        if not selected_tracks:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Keine Spuren", "Bitte mindestens eine Spur auswählen!")
            return
        
        # Ask for output directory
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Export Zielordner wählen",
            str(Path.home()),
        )
        
        if not output_dir:
            return  # User cancelled
        
        self.export_path = Path(output_dir)

        # Build export config
        try:
            from pydaw.services.audio_export_service import ExportConfig, export_audio

            format_ext = self.selected_format
            quality_data = self.cmb_quality.currentData()

            # Bit depth
            bit_depth = 24
            if quality_data in ("16bit",):
                bit_depth = 16
            elif quality_data in ("24bit",):
                bit_depth = 24
            elif quality_data in ("32bit",):
                bit_depth = 32

            # MP3 bitrate
            mp3_bitrate = 320
            for br in (128, 192, 256, 320):
                if quality_data == f"{br}k":
                    mp3_bitrate = br

            # OGG quality
            ogg_quality = 7
            for q in (3, 5, 7, 10):
                if quality_data == f"q{q}":
                    ogg_quality = q

            # Sample rate
            sr_data = self.cmb_samplerate.currentData()
            sample_rate = int(sr_data) if isinstance(sr_data, int) else 0

            # Dither
            dither = "none"
            if self.chk_dither.isChecked():
                dither = str(self.cmb_dither_type.currentData() or "tpdf")

            # Normalize
            normalize_mode = str(self.cmb_normalize.currentData() or "none")

            # Project info
            project = self.project.ctx.project
            project_name = str(getattr(project, "name", "Py_DAW") or "Py_DAW")
            bpm = float(getattr(project, "bpm", 120.0) or 120.0)

            # Time range
            start_beat = 0.0
            end_beat = -1.0  # auto-detect
            if self.btn_loop.isChecked():
                try:
                    transport = getattr(self.project, '_transport', None)
                    if transport:
                        start_beat = float(getattr(transport, 'loop_start_beat', 0.0))
                        end_beat = float(getattr(transport, 'loop_end_beat', -1.0))
                except Exception:
                    pass

            # v0.0.20.650: FX Mode (AP10 Phase 10B Task 4)
            fx_mode = str(self.cmb_fx_mode.currentData() or "post_fx")

            config = ExportConfig(
                output_dir=str(output_dir),
                filename_base=project_name,
                format=format_ext,
                bit_depth=bit_depth,
                mp3_bitrate=mp3_bitrate,
                ogg_quality=ogg_quality,
                sample_rate=sample_rate,
                normalize_mode=normalize_mode,
                normalize_target_db=-0.3,
                normalize_target_lufs=-14.0,
                dither=dither,
                start_beat=start_beat,
                end_beat=end_beat,
                track_ids=selected_tracks,
                stem_export=len(selected_tracks) > 1 and "master" not in selected_tracks,
                project_name=project_name,
                bpm=bpm,
                fx_mode=fx_mode,
            )

            # Create a render function from arrangement_renderer
            def _render_func(start_b, end_b, track_ids, sr, include_fx=True):
                try:
                    renderer = getattr(self.project, 'arrangement_renderer', None)
                    if renderer is None:
                        renderer = getattr(self.project, '_renderer', None)
                    if renderer and hasattr(renderer, 'render_offline'):
                        try:
                            return renderer.render_offline(start_b, end_b, track_ids, sr,
                                                           include_fx=include_fx)
                        except TypeError:
                            return renderer.render_offline(start_b, end_b, track_ids, sr)
                    elif renderer and hasattr(renderer, 'render_range'):
                        return renderer.render_range(start_b, end_b, sr)
                except Exception as e:
                    _log_export = logging.getLogger(__name__)
                    _log_export.error("Render function error: %s", e)
                return None

            # Progress dialog
            from PyQt6.QtWidgets import QProgressDialog, QMessageBox
            progress = QProgressDialog("Audio Export...", "Abbrechen", 0, 100, self)
            progress.setWindowTitle("Audio Export")
            progress.setMinimumDuration(0)
            progress.setValue(0)

            def _on_progress(pct, msg):
                try:
                    progress.setValue(int(pct * 100))
                    progress.setLabelText(msg)
                except Exception:
                    pass

            # Run export
            exported = export_audio(config, _render_func, _on_progress)

            progress.close()

            if exported:
                msg = f"Erfolgreich exportiert:\n\n"
                for f in exported:
                    msg += f"• {Path(f).name}\n"
                msg += f"\nZiel: {output_dir}"
                QMessageBox.information(self, "Export Fertig", msg)
            else:
                QMessageBox.warning(
                    self, "Export",
                    f"Export konfiguriert für {format_ext.upper()} "
                    f"({quality_data}).\n\n"
                    f"Renderer konnte keine Audiodaten erzeugen.\n"
                    f"(Render-Engine muss render_offline() unterstützen)"
                )

        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Export Fehler", f"Export fehlgeschlagen:\n{e}")
        
        self.accept()
