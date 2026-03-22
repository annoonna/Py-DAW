#!/usr/bin/env python3
"""Fusion smoke test harness (offscreen-safe).

Covers the regression hotspots from v0.0.20.578-v0.0.20.581:
- queued MIDI-CC updates are flushed into persisted state snapshots
- Scrawl waveform state round-trips through track.instrument_state
- Wavetable file path survives save/load recall
- OSC/FLT/ENV rebuild path can be traversed without crashing

Run from project root:
    QT_QPA_PLATFORM=offscreen python3 pydaw/tools/fusion_smoke_test.py
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
import wave
from pathlib import Path

# Allow direct execution from repository root or from the tools folder.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication  # noqa: E402
except Exception as exc:  # pragma: no cover - environment dependent
    QApplication = None
    _PYQT_IMPORT_ERROR = exc
else:
    _PYQT_IMPORT_ERROR = None

from pydaw.model.project import Project, Track  # noqa: E402

FusionWidget = None
_OSC_TYPES = []
_FLT_TYPES = []
_ENV_TYPES = []


class _DummyCtx:
    def __init__(self, project: Project):
        self.project = project


class _DummyProjectService:
    def __init__(self, project: Project):
        self.ctx = _DummyCtx(project)
        self.updated_count = 0

    def _emit_updated(self) -> None:
        self.updated_count += 1


class SmokeFailure(RuntimeError):
    pass


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise SmokeFailure(msg)


def _set_combo_to_key(widget: FusionWidget, combo_name: str, key: str) -> None:
    combo = getattr(widget, combo_name)
    idx = next((i for i in range(combo.count()) if combo.itemData(i) == key), -1)
    _expect(idx >= 0, f"{combo_name}: key not found: {key}")
    combo.setCurrentIndex(idx)


def _build_widget(project_service: _DummyProjectService, track_id: str) -> FusionWidget:
    widget = FusionWidget(project_service=project_service, audio_engine=None, automation_manager=None)
    widget.set_track_context(track_id)
    QApplication.processEvents()
    return widget


def _write_temp_wav() -> str:
    fd, path = tempfile.mkstemp(prefix="fusion_smoke_", suffix=".wav")
    os.close(fd)
    frames = 2048
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        data = bytearray()
        for i in range(frames):
            sample = math.sin(2.0 * math.pi * (i / frames))
            val = max(-32767, min(32767, int(round(sample * 32767.0))))
            data += int(val).to_bytes(2, byteorder="little", signed=True)
        wf.writeframes(bytes(data))
    return path


def test_pending_midi_cc_snapshot(widget: FusionWidget) -> None:
    knob = widget._knobs["osc.pitch_st"]
    _expect(knob.value() == 0, "expected init pitch_st == 0")
    widget._queue_coalesced_midi_cc_update(knob, 127)
    state = widget._capture_state_snapshot()
    _expect(state["knobs"]["osc.pitch_st"] == knob.maximum(), "pending MIDI-CC was not flushed into snapshot")
    _expect(knob.value() == knob.maximum(), "knob value did not update after CC snapshot flush")


def test_scrawl_roundtrip(project_service: _DummyProjectService, track_id: str) -> None:
    widget = _build_widget(project_service, track_id)
    _set_combo_to_key(widget, "_cmb_osc", "scrawl")
    _set_combo_to_key(widget, "_cmb_flt", "comb")
    _set_combo_to_key(widget, "_cmb_env", "pluck")
    QApplication.processEvents()

    points = [
        (0.0, -0.2),
        (0.18, -0.05),
        (0.34, 0.42),
        (0.63, 0.11),
        (0.86, -0.73),
        (1.0, -0.2),
    ]
    widget._apply_scrawl_state(points, smooth=False, sync_editor=True)
    widget._knobs["osc.pitch_st"].setValue(3)
    widget._knobs["flt.cutoff"].setValue(79)
    widget._knobs["aeg.brightness"].setValue(61)
    widget._persist_instrument_state()
    QApplication.processEvents()
    widget.shutdown()

    restored = _build_widget(project_service, track_id)
    _expect(restored._current_osc == "scrawl", "scrawl osc type did not restore")
    _expect(restored._current_flt == "comb", "comb filter did not restore")
    _expect(restored._current_env == "pluck", "pluck env did not restore")
    _expect(restored._knobs["osc.pitch_st"].value() == 3, "pitch_st knob did not restore")
    _expect(restored._knobs["flt.cutoff"].value() == 79, "cutoff knob did not restore")
    _expect(restored._knobs["aeg.brightness"].value() == 61, "pluck brightness did not restore")
    _expect(getattr(restored.engine, "_scrawl_points", []) == points, "scrawl points did not round-trip")
    _expect(getattr(restored.engine, "_scrawl_smooth", True) is False, "scrawl smooth flag did not round-trip")
    restored.shutdown()


def test_wavetable_roundtrip(project_service: _DummyProjectService, track_id: str) -> None:
    widget = _build_widget(project_service, track_id)
    _set_combo_to_key(widget, "_cmb_osc", "wavetable")
    QApplication.processEvents()
    wt_path = _write_temp_wav()
    try:
        widget.engine._wt_file_path = wt_path
        if hasattr(widget, "_wt_name_label"):
            widget._wt_name_label.setText(Path(wt_path).name)
        widget._knobs["osc.index"].setValue(44)
        widget._knobs["osc.unison_mode"].setValue(2)
        widget._knobs["osc.unison_voices"].setValue(5)
        widget._knobs["osc.unison_spread"].setValue(77)
        widget._persist_instrument_state()
        QApplication.processEvents()
        widget.shutdown()

        restored = _build_widget(project_service, track_id)
        _expect(restored._current_osc == "wavetable", "wavetable osc type did not restore")
        _expect(getattr(restored.engine, "_wt_file_path", "") == wt_path, "wavetable path did not restore")
        _expect(restored._knobs["osc.index"].value() == 44, "wavetable index did not restore")
        _expect(restored._knobs["osc.unison_mode"].value() == 2, "wavetable unison mode did not restore")
        _expect(restored._knobs["osc.unison_voices"].value() == 5, "wavetable unison voices did not restore")
        _expect(restored._knobs["osc.unison_spread"].value() == 77, "wavetable unison spread did not restore")
        restored.shutdown()
    finally:
        try:
            os.unlink(wt_path)
        except OSError:
            pass


def test_module_switch_walk(widget: FusionWidget) -> None:
    for key, _label in _OSC_TYPES:
        _set_combo_to_key(widget, "_cmb_osc", key)
        QApplication.processEvents()
        _expect(widget._current_osc == key, f"osc switch failed: {key}")
    for key, _label in _FLT_TYPES:
        _set_combo_to_key(widget, "_cmb_flt", key)
        QApplication.processEvents()
        _expect(widget._current_flt == key, f"filter switch failed: {key}")
    for key, _label in _ENV_TYPES:
        _set_combo_to_key(widget, "_cmb_env", key)
        QApplication.processEvents()
        _expect(widget._current_env == key, f"env switch failed: {key}")


def main() -> int:
    if QApplication is None:
        print(f"[SKIP] PyQt6 fehlt in dieser Umgebung: {_PYQT_IMPORT_ERROR}", file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication([])

    global FusionWidget, _OSC_TYPES, _FLT_TYPES, _ENV_TYPES
    from pydaw.plugins.fusion.fusion_widget import (
        FusionWidget as _FusionWidget,
        _OSC_TYPES as __OSC_TYPES,
        _FLT_TYPES as __FLT_TYPES,
        _ENV_TYPES as __ENV_TYPES,
    )
    FusionWidget = _FusionWidget
    _OSC_TYPES = __OSC_TYPES
    _FLT_TYPES = __FLT_TYPES
    _ENV_TYPES = __ENV_TYPES

    project = Project(name="Fusion Smoke")
    track = Track(kind="instrument", name="Fusion Smoke Track", plugin_type="chrono.fusion")
    project.tracks.append(track)
    project_service = _DummyProjectService(project)

    widget = _build_widget(project_service, track.id)
    try:
        test_pending_midi_cc_snapshot(widget)
        test_module_switch_walk(widget)
    finally:
        widget.shutdown()

    test_scrawl_roundtrip(project_service, track.id)
    test_wavetable_roundtrip(project_service, track.id)

    print("[OK] Fusion smoke test passed")
    print(f"[OK] project_service._emit_updated calls: {project_service.updated_count}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
