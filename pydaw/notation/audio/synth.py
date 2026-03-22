# ChronoScale – interner Software-Synth
# PipeWire Audio + ALSA MIDI (bewährt & stabil)

import subprocess
import shutil
import time

DEFAULT_SF2 = "/usr/share/sounds/sf2/FluidR3_GM.sf2"

class FluidSynthEngine:
    def __init__(self, soundfont=DEFAULT_SF2):
        self.soundfont = soundfont
        self.process = None

    def is_available(self):
        return shutil.which("fluidsynth") is not None

    def start(self):
        if not self.is_available():
            raise RuntimeError("FluidSynth ist nicht installiert")

        if self.process:
            return

        self.process = subprocess.Popen(
            [
                "fluidsynth",
                "-a", "pulseaudio",   # Audio → PipeWire
                "-m", "alsa_seq",     # MIDI → ALSA (wichtig!)
                "-g", "1.0",
                self.soundfont
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        time.sleep(0.7)

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process = None

SYNTH = FluidSynthEngine()
