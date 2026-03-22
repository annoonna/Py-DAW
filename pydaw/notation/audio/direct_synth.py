# ChronoScaleStudio – direkter Audio-Synth (FluidSynth via Python-Bindings)
# Fokus: stabile Wiedergabe + Lautstärkeregelung (CC7) für UI-Drehregler & Automation.

from __future__ import annotations

import time
import fluidsynth

SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2"


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


class DirectSynth:
    def __init__(self):
        self.fs = fluidsynth.Synth()
        self.fs.start(driver="pulseaudio")
        self.sfid = self.fs.sfload(SOUNDFONT)
        self.fs.program_select(0, self.sfid, 0, 0)

        self._volume_cc7 = 100  # 0..127
        self.set_channel_volume(self._volume_cc7)

    # ---------- Lautstärke ----------
    def set_channel_volume(self, value: int):
        """Setzt MIDI-Channel-Volume (CC7)."""
        value = _clamp(value, 0, 127)
        self._volume_cc7 = value
        # CC: 7 = Channel Volume
        try:
            self.fs.cc(0, 7, value)
        except Exception:
            # Fallback: wenn Binding keine cc-Methode bietet, bleibt nur Velocity-Scaling.
            pass

    def get_channel_volume(self) -> int:
        return int(self._volume_cc7)

    # ---------- Note I/O ----------
    def note_on(self, pitch: int, velocity: int = 90):
        self.fs.noteon(0, _clamp(pitch, 0, 127), _clamp(velocity, 1, 127))

    def note_off(self, pitch: int):
        self.fs.noteoff(0, _clamp(pitch, 0, 127))

    # ---------- Convenience ----------
    def play_scale(self, intervals_cent, root_midi=60, duration=0.35, on_note=None, velocity: int = 90):
        for index, cent in enumerate(intervals_cent):
            note = root_midi + round(cent / 100)

            if on_note:
                on_note(index)

            self.note_on(note, velocity=velocity)
            time.sleep(duration)
            self.note_off(note)

        if on_note:
            on_note(-1)


SYNTH = DirectSynth()
