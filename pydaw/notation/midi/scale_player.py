# ChronoScale – Skalen-Playback (direkter Synth)

from pydaw.notation.audio.direct_synth import SYNTH

def play_scale(intervals_cent, root_midi=60):
    SYNTH.play_scale(intervals_cent, root_midi=root_midi)
