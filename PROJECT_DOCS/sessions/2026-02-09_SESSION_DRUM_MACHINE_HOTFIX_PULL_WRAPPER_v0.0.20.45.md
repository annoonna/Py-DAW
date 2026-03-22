# SESSION — Pro Drum Machine Hotfix: Pull Wrapper (v0.0.20.45)

**Date:** 2026-02-09  
**Developer:** GPT-5.2 Thinking  
**Duration:** ~10 min  

## Problem (User Report)

Beim Einfügen von **Pro Drum Machine** erschien im Device Panel ein Fehler-Overlay:

- `'method' object has no attribute '_pydaw_track_id' and no __dict__ for setting new attributes`

## Root Cause

`DrumMachineWidget` hatte `self._pull_fn = self.engine.pull` gesetzt.
`self.engine.pull` ist ein **bound method** (Method-Objekt) und kann keine freien Attribute tragen.

Die DAW-Engine (AudioEngine/DSP) liest jedoch optional:
- `callable._pydaw_track_id` (dynamic getter)

…damit Track-Fader/VU-Meter pro Pull-Source korrekt angewendet werden.

## Fix

Wie im Sampler-Device wird nun ein Wrapper-Callable erzeugt:

- `def _pull(frames, sr, _eng=self.engine): return _eng.pull(frames, sr)`
- `_pull._pydaw_track_id = lambda: (self.track_id or "")`
- `self._pull_fn = _pull`

Damit ist `_pydaw_track_id` wieder setzbar und das Device lädt ohne Fehler.

## Files Changed

- `pydaw/plugins/drum_machine/drum_widget.py`
- `VERSION`
- `pydaw/version.py`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`
- `PROJECT_DOCS/sessions/LATEST.md`

## Next

Wenn der User bestätigt, dass das Device jetzt sauber lädt:

- Slot-State Persistenz (Samplepfade + Parameter)
- Waveform-Editor pro Slot (Start/End/Loop/Fades)
- Style-Mixer (mehrere Styles blendbar) + Humanize/Swing
- Auto-Clip-Create falls kein aktiver MIDI-Clip existiert
