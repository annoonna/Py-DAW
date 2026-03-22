"""Audio settings dialog.

Goals
-----
- Let the user choose the *engine* backend (sounddevice / jack / none).
- Let the user optionally enable a *JACK client* for port visibility & routing in qpwgraph.
  This is independent from the engine backend, because many workflows want:
    - Playback via sounddevice (PortAudio)
    - Routing/recording visibility via JACK/PipeWire-JACK ports

Hard rules
----------
- Never force-switch the engine backend just because the JACK client is enabled.
- Never overwrite sounddevice device ids with empty values when backend=jack.
- Keep the dialog startable even when JACK isn't reachable.
"""

from __future__ import annotations

import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pydaw.audio.audio_engine import AudioEngine, Backend
from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import get_value, set_value
from pydaw.services.jack_client_service import JackClientService


class AudioSettingsDialog(QDialog):
    def __init__(self, engine: AudioEngine, jack: JackClientService | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Audio-Einstellungen")
        self.setModal(True)

        # Wird vom MainWindow ausgewertet: nach "OK" die App automatisch neu starten
        self.restart_requested: bool = False
        self.restart_via_pw_jack: bool = False

        self.engine = engine
        self.jack = jack
        self.keys = SettingsKeys()

        self._build_ui()
        self._load()

        # Snapshot für Restart-Entscheidung
        self._orig_backend = self.cmb_backend.currentData()
        self._orig_jack_enable = bool(self.chk_jack_enable.isChecked())
        self._orig_in_pairs = int(self.spin_jack_in.value())
        self._orig_out_pairs = int(self.spin_jack_out.value())
        self._orig_monitor = bool(self.chk_jack_monitor.isChecked())

        self._refresh_lists()

        # Engine feedback -> UI
        try:
            self.engine.status.connect(self._set_status)
            self.engine.error.connect(self._on_error)
        except Exception:
            pass

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.lbl_status = QLabel("Erkennung läuft…")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        box = QGroupBox("Backend & Routing")
        form = QFormLayout(box)

        self.cmb_backend = QComboBox()
        self.cmb_backend.addItem("JACK (PipeWire bevorzugt)", "jack")
        self.cmb_backend.addItem("sounddevice (PortAudio)", "sounddevice")
        self.cmb_backend.addItem("Keins", "none")
        self.cmb_backend.currentIndexChanged.connect(self._on_backend_changed)

        self.cmb_input = QComboBox()
        self.cmb_output = QComboBox()

        form.addRow("Backend", self.cmb_backend)
        form.addRow("Input", self.cmb_input)
        form.addRow("Output", self.cmb_output)

        layout.addWidget(box)

        jack_box = QGroupBox("JACK / PipeWire-JACK (Ports)")
        jack_form = QFormLayout(jack_box)

        self.chk_jack_enable = QCheckBox("JACK Client aktivieren (PyDAW in qpwgraph sichtbar)")

        self.spin_jack_in = QSpinBox()
        self.spin_jack_in.setRange(1, 32)  # Stereo pairs
        self.spin_jack_in.setValue(1)

        self.spin_jack_out = QSpinBox()
        self.spin_jack_out.setRange(1, 32)
        self.spin_jack_out.setValue(1)

        self.chk_jack_monitor = QCheckBox("Input Monitoring (Inputs → Outputs)")

        jack_form.addRow(self.chk_jack_enable)
        jack_form.addRow("Stereo-Inputs (Paare)", self.spin_jack_in)
        jack_form.addRow("Stereo-Outputs (Paare)", self.spin_jack_out)
        jack_form.addRow(self.chk_jack_monitor)

        layout.addWidget(jack_box)

        perf = QGroupBox("Audio-Parameter (Platzhalter)")
        perf_form = QFormLayout(perf)

        # v0.0.20.68: Provide common sample-rate presets (44100/48000/…)
        # Users can still type any custom value into the spin box.
        self._sr_updating = False
        self.cmb_sr_preset = QComboBox()
        for _sr in (44100, 48000, 88200, 96000, 192000):
            self.cmb_sr_preset.addItem(f"{_sr} Hz", int(_sr))
        self.cmb_sr_preset.addItem("Custom", "custom")

        self.spin_sr = QSpinBox()
        self.spin_sr.setRange(8000, 384000)
        self.spin_sr.setSingleStep(1000)

        # v0.0.20.636: Buffer size ComboBox with standard DAW sizes (AP2 Phase 2B)
        self.cmb_buf = QComboBox()
        for bs in (64, 128, 256, 512, 1024, 2048, 4096):
            latency_ms = (bs / 48000.0) * 1000.0
            self.cmb_buf.addItem(f"{bs} ({latency_ms:.1f} ms @ 48kHz)", bs)

        sr_row = QWidget()
        sr_row_l = QHBoxLayout(sr_row)
        sr_row_l.setContentsMargins(0, 0, 0, 0)
        sr_row_l.addWidget(self.cmb_sr_preset)
        sr_row_l.addWidget(self.spin_sr)
        perf_form.addRow("Samplerate", sr_row)
        perf_form.addRow("Buffer Size", self.cmb_buf)

        try:
            self.cmb_sr_preset.currentIndexChanged.connect(self._on_sr_preset_changed)
            self.spin_sr.valueChanged.connect(self._on_sr_spin_changed)
        except Exception:
            pass

        layout.addWidget(perf)

        # --------------------------------------------------------------
        # Performance: MIDI Pre-Render options
        # --------------------------------------------------------------
        pr = QGroupBox("Performance: MIDI Pre-Render")
        pr_form = QFormLayout(pr)

        self.chk_pr_autoload = QCheckBox("Automatisch nach Projekt/Stand laden pre-rendern")
        self.chk_pr_autoload.setToolTip(
            "Rendert MIDI-Clips im Hintergrund, damit Playback nicht stottert."
        )

        self.chk_pr_show_load = QCheckBox("Fortschritt beim Auto-Pre-Render anzeigen")
        self.chk_pr_show_load.setToolTip("Zeigt einen kleinen Fortschrittsdialog beim Laden.")

        self.chk_pr_wait_play = QCheckBox("Vor Play warten, bis Pre-Render fertig ist")
        self.chk_pr_wait_play.setToolTip(
            "Wenn aktiv, startet Play erst wenn alle relevanten MIDI-Clips gerendert wurden."
        )

        self.chk_pr_show_play = QCheckBox("Fortschritt vor Play anzeigen")
        self.chk_pr_show_play.setToolTip("Zeigt einen Fortschrittsdialog, während vorgerendert wird.")

        pr_form.addRow(self.chk_pr_autoload)
        pr_form.addRow(self.chk_pr_show_load)
        pr_form.addRow(self.chk_pr_wait_play)
        pr_form.addRow(self.chk_pr_show_play)
        layout.addWidget(pr)

        # v0.0.20.704: Plugin Sandbox section (P1C + P6C)
        sbx = QGroupBox("🛡️ Plugin Sandbox (Crash-Schutz)")
        sbx_form = QFormLayout(sbx)

        self.chk_sandbox_enabled = QCheckBox(
            "Plugin Sandbox aktivieren (jedes Plugin in eigenem Prozess)")
        self.chk_sandbox_enabled.setToolTip(
            "Wenn aktiv, laufen externe Plugins (VST3/VST2/LV2/LADSPA/CLAP) "
            "in separaten Subprozessen.\n"
            "Crasht ein Plugin → nur der Worker-Prozess stirbt, "
            "die DAW läuft weiter.\n"
            "Bitwig-Style Crash-Recovery mit Auto-Restart."
        )
        sbx_form.addRow(self.chk_sandbox_enabled)

        layout.addWidget(sbx)

        row = QHBoxLayout()
        self.btn_start = QPushButton("Test: Start (Silence)")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(True)

        self.btn_start.clicked.connect(self._start_audio)
        self.btn_stop.clicked.connect(self.engine.stop)

        row.addWidget(self.btn_start)
        row.addWidget(self.btn_stop)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._buttons = buttons
        self._btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(buttons)

    def _on_sr_preset_changed(self) -> None:
        if getattr(self, "_sr_updating", False):
            return
        try:
            data = self.cmb_sr_preset.currentData()
            if isinstance(data, int):
                self._sr_updating = True
                self.spin_sr.setValue(int(data))
        finally:
            self._sr_updating = False

    def _on_sr_spin_changed(self) -> None:
        if getattr(self, "_sr_updating", False):
            return
        try:
            sr = int(self.spin_sr.value())
            # Select matching preset, otherwise fall back to "Custom".
            idx_custom = self.cmb_sr_preset.findData("custom")
            idx_match = self.cmb_sr_preset.findData(sr)
            self._sr_updating = True
            if idx_match >= 0:
                self.cmb_sr_preset.setCurrentIndex(idx_match)
            elif idx_custom >= 0:
                self.cmb_sr_preset.setCurrentIndex(idx_custom)
        finally:
            self._sr_updating = False

    def _set_status(self, msg: str) -> None:
        try:
            self.lbl_status.setText(str(msg))
        except Exception:
            pass

    def _on_error(self, msg: str) -> None:
        try:
            QMessageBox.warning(self, "Audio-Fehler", str(msg))
        except Exception:
            pass

    # ---------------- Logic ----------------
    def _on_backend_changed(self) -> None:
        """Backend dropdown changed.

        UX:
        - JACK port controls remain usable independent of the engine backend.
        - We do not force backend changes.
        """
        backend: Backend = self.cmb_backend.currentData()

        # JACK controls always usable (for routing/recording visibility)
        for w in (self.chk_jack_enable, self.spin_jack_in, self.spin_jack_out, self.chk_jack_monitor):
            try:
                w.setEnabled(True)
            except Exception:
                pass

        if backend == "sounddevice":
            self._set_status(
                "sounddevice aktiv. JACK/PipeWire-JACK Ports sind optional (Recording/Routing) "
                "und ändern das Backend NICHT."
            )
        elif backend == "jack":
            if not JackClientService.probe_available():
                self._set_status(
                    "JACK nicht erreichbar. Start ggf. mit 'pw-jack python3 main.py' "
                    "oder stelle sicher, dass PipeWire-JACK/JACK läuft."
                )
        else:
            self._set_status("Kein Backend ausgewählt.")

        self._refresh_lists()

    def _refresh_lists(self) -> None:
        backend: Backend = self.cmb_backend.currentData()

        jack_ok = True
        if backend == "jack":
            jack_ok = JackClientService.probe_available()

        self.cmb_input.clear()
        self.cmb_output.clear()

        # JACK: routing via ports; device ids are not meaningful.
        if backend == "jack" and not jack_ok:
            self.cmb_input.addItem("(JACK Ports: über qpwgraph routen)", "")
            self.cmb_output.addItem("(JACK Ports: über qpwgraph routen)", "")
            self.cmb_input.setEnabled(False)
            self.cmb_output.setEnabled(False)
            return

        self.cmb_input.setEnabled(True)
        self.cmb_output.setEnabled(True)

        inputs = self.engine.list_inputs(backend)
        outputs = self.engine.list_outputs(backend)

        for ep in inputs:
            self.cmb_input.addItem(ep.label, ep.id)
        for ep in outputs:
            self.cmb_output.addItem(ep.label, ep.id)

        if self.cmb_input.count() == 0:
            self.cmb_input.addItem("(keine Inputs gefunden)", "")
        if self.cmb_output.count() == 0:
            self.cmb_output.addItem("(keine Outputs gefunden)", "")

        # Restore selection only for sounddevice.
        if backend == "sounddevice":
            saved_in = str(get_value(self.keys.audio_input, ""))
            saved_out = str(get_value(self.keys.audio_output, ""))
            self._select_if_present(self.cmb_input, saved_in)
            self._select_if_present(self.cmb_output, saved_out)

    @staticmethod
    def _select_if_present(cmb: QComboBox, data: str) -> None:
        if not data:
            return
        for i in range(cmb.count()):
            if str(cmb.itemData(i)) == str(data):
                cmb.setCurrentIndex(i)
                return

    def _load(self) -> None:
        saved_backend = str(get_value(self.keys.audio_backend, getattr(self.engine, "backend", "sounddevice")))
        self._select_if_present(self.cmb_backend, saved_backend)

        # JACK client preferences
        en = str(get_value(self.keys.jack_enable, "0"))
        self.chk_jack_enable.setChecked(en.lower() in ("1", "true", "yes", "on"))

        in_ch = int(get_value(self.keys.jack_in_ports, 2))
        out_ch = int(get_value(self.keys.jack_out_ports, 2))
        self.spin_jack_in.setValue(max(1, (in_ch + 1) // 2))
        self.spin_jack_out.setValue(max(1, (out_ch + 1) // 2))

        mon = str(get_value(self.keys.jack_input_monitor, "0"))
        self.chk_jack_monitor.setChecked(mon.lower() in ("1", "true", "yes", "on"))

        sr = int(get_value(self.keys.sample_rate, 48000))
        buf = int(get_value(self.keys.buffer_size, 256))
        self.spin_sr.setValue(sr)
        # v0.0.20.636: Buffer size ComboBox
        for i in range(self.cmb_buf.count()):
            if self.cmb_buf.itemData(i) == buf:
                self.cmb_buf.setCurrentIndex(i)
                break

        # Pre-render defaults: enabled (autoload + wait + progress) for smoother UX
        def _b(key: str, default: bool) -> bool:
            v = str(get_value(key, "1" if default else "0")).strip().lower()
            return v in ("1", "true", "yes", "on")

        self.chk_pr_autoload.setChecked(_b(self.keys.prerender_auto_on_load, True))
        self.chk_pr_show_load.setChecked(_b(self.keys.prerender_show_progress_on_load, False))
        self.chk_pr_wait_play.setChecked(_b(self.keys.prerender_wait_before_play, False))  # FIXED: Default FALSE!
        self.chk_pr_show_play.setChecked(_b(self.keys.prerender_show_progress_on_play, True))

        # v0.0.20.704: Plugin Sandbox (P1C)
        self.chk_sandbox_enabled.setChecked(
            _b(self.keys.audio_plugin_sandbox_enabled, False))

    # ---------------- Actions ----------------
    def accept(self) -> None:
        backend: Backend = self.cmb_backend.currentData()

        # Persist sounddevice device ids only when relevant.
        if backend == "sounddevice":
            set_value(self.keys.audio_input, self.cmb_input.currentData())
            set_value(self.keys.audio_output, self.cmb_output.currentData())

        set_value(self.keys.sample_rate, int(self.spin_sr.value()))
        set_value(self.keys.buffer_size, int(self.cmb_buf.currentData() or 256))
        set_value(self.keys.audio_backend, backend)

        # MIDI Pre-Render preferences
        set_value(self.keys.prerender_auto_on_load, "1" if self.chk_pr_autoload.isChecked() else "0")
        set_value(self.keys.prerender_show_progress_on_load, "1" if self.chk_pr_show_load.isChecked() else "0")
        set_value(self.keys.prerender_wait_before_play, "1" if self.chk_pr_wait_play.isChecked() else "0")
        set_value(self.keys.prerender_show_progress_on_play, "1" if self.chk_pr_show_play.isChecked() else "0")

        # JACK client preferences (independent of backend)
        jack_enabled = bool(self.chk_jack_enable.isChecked())
        jack_in_pairs = int(self.spin_jack_in.value())
        jack_out_pairs = int(self.spin_jack_out.value())
        jack_in = jack_in_pairs * 2
        jack_out = jack_out_pairs * 2
        jack_monitor = bool(self.chk_jack_monitor.isChecked())

        set_value(self.keys.jack_enable, "1" if jack_enabled else "0")
        set_value(self.keys.jack_in_ports, jack_in)
        set_value(self.keys.jack_out_ports, jack_out)
        set_value(self.keys.jack_input_monitor, "1" if jack_monitor else "0")

        # v0.0.20.704: Plugin Sandbox (P1C)
        set_value(self.keys.audio_plugin_sandbox_enabled,
                  "1" if self.chk_sandbox_enabled.isChecked() else "0")

        # For services created in this process
        try:
            os.environ["PYDAW_ENABLE_JACK"] = "1" if jack_enabled else "0"
            os.environ["PYDAW_JACK_IN"] = str(jack_in)
            os.environ["PYDAW_JACK_OUT"] = str(jack_out)
            os.environ["PYDAW_JACK_MONITOR"] = "1" if jack_monitor else "0"
            # Do NOT touch PYDAW_AUDIO_BACKEND here.
        except Exception:
            pass

        # Apply JACK client config in-process when possible
        if self.jack is not None:
            try:
                self.jack.apply_config(enabled=jack_enabled, in_ch=jack_in, out_ch=jack_out, monitor=jack_monitor)
            except Exception:
                pass

        backend_changed = (backend != self._orig_backend)
        jack_changed = (
            (jack_enabled != self._orig_jack_enable)
            or (jack_in_pairs != self._orig_in_pairs)
            or (jack_out_pairs != self._orig_out_pairs)
            or (jack_monitor != self._orig_monitor)
        )

        # Backend change -> restart recommended
        if backend_changed:
            self.restart_requested = True

        # v0.0.20.721: Notify Rust Engine of new audio settings (live reconfigure)
        try:
            from pydaw.services.rust_engine_bridge import RustEngineBridge
            if RustEngineBridge.is_enabled():
                bridge = RustEngineBridge.instance()
                if bridge.is_connected:
                    new_sr = int(self.spin_sr.value())
                    new_buf = int(self.cmb_buf.currentData() or 1024)
                    bridge.send_command({
                        "cmd": "Configure",
                        "sample_rate": new_sr,
                        "buffer_size": new_buf,
                        "device": "",
                    })
        except Exception:
            pass  # Rust not available — no problem

        # If JACK enabled changed and JACK isn't reachable: offer pw-jack relaunch
        if jack_changed and jack_enabled and (not JackClientService.probe_available()):
            if shutil.which("pw-jack") and os.environ.get("PYDAW_PWJACK", "0") != "1":
                self.restart_via_pw_jack = True
                self.restart_requested = True

        super().accept()

    def _start_audio(self) -> None:
        backend: Backend = self.cmb_backend.currentData()
        cfg = {
            "sample_rate": int(self.spin_sr.value()),
            "buffer_size": int(self.cmb_buf.currentData() or 256),
            "input_device": self.cmb_input.currentData(),
            "output_device": self.cmb_output.currentData(),
        }
        try:
            self.engine.set_backend(backend)
        except Exception:
            pass
        self.engine.start(backend=backend, config=cfg)
