
from __future__ import annotations

try:
    import mido
except ImportError:  # pragma: no cover
    mido = None

from typing import Dict, Tuple, List

from pydaw.notation.music.sequence import NoteSequence
from pydaw.notation.music.events import NoteEvent, RestEvent, BaseEvent


def export_midi(notes, filename):
    """Legacy: einfache Liste von MIDI-Noten (gleichlange Steps)."""
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    for note in notes:
        track.append(mido.Message('note_on', note=int(note), velocity=64, time=120))
        track.append(mido.Message('note_off', note=int(note), velocity=64, time=120))
    mid.save(filename)


def export_sequence(sequence: NoteSequence, filename: str, tempo_bpm: int = 120, ticks_per_beat: int = 480):
    if mido is None:
        raise RuntimeError("Python-Paket 'mido' ist nicht installiert. Bitte requirements.txt installieren.")
    """Exportiert ChronoScaleStudio-Sequenz als Multi-Track MIDI.

    - Jede Spur wird ein MIDI-Track.
    - Noten werden in note_on/note_off Events umgewandelt (polyphon pro Spur).
    """
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)

    # Tempo Track (0)
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(int(tempo_bpm)), time=0))

    for tr in sequence.tracks:
        t = mido.MidiTrack()
        mid.tracks.append(t)

        channel = int(tr.midi_channel) % 16

        # Note on/off timeline
        timeline = []
        for ev in sequence.events:
            if not isinstance(ev, NoteEvent):
                continue
            if int(getattr(ev, "track_id", 1)) != tr.id:
                continue
            st = int(round(float(ev.start) * ticks_per_beat))
            en = int(round(float(ev.end) * ticks_per_beat))
            note = int(ev.pitch)
            vel = max(1, min(127, int(ev.velocity)))
            # Off before On at same tick to avoid stuck notes for repeated note
            timeline.append((st, 1, note, vel))   # on
            timeline.append((en, 0, note, 0))     # off

        timeline.sort(key=lambda x: (x[0], x[1], x[2]))  # off (0) before on (1)

        current = 0
        for tick, typ, note, vel in timeline:
            delta = max(0, tick - current)
            if typ == 1:
                t.append(mido.Message("note_on", note=note, velocity=vel, time=delta, channel=channel))
            else:
                t.append(mido.Message("note_off", note=note, velocity=0, time=delta, channel=channel))
            current = tick

    mid.save(filename)


def import_midi(filename: str, quant_step: float = 0.25) -> tuple[NoteSequence, int]:
    if mido is None:
        raise RuntimeError("Python-Paket 'mido' ist nicht installiert. Bitte requirements.txt installieren.")
    """Importiert ein MIDI-File in eine ChronoScaleStudio-Sequenz.

    Rückgabe: (sequence, tempo_bpm)

    Heuristik:
    - Jeder MIDI-Track wird zu einer ChronoScaleStudio-Spur.
    - Clef: Track 1 = Treble, Track 2+ = Treble (später konfigurierbar).
    - Tempo: erstes set_tempo, sonst 120.
    - Noten werden aus note_on/note_off Paare rekonstruiert (pro channel+note).
    """
    mid = mido.MidiFile(filename)
    tpb = mid.ticks_per_beat or 480

    tempo_bpm = 120
    # Tempo aus erstem Meta setzen
    for tr in mid.tracks:
        for msg in tr:
            if msg.type == "set_tempo":
                tempo_bpm = int(round(mido.tempo2bpm(msg.tempo)))
                break
        if tempo_bpm != 120:
            break

    seq = NoteSequence()
    # reset default track; we'll rebuild from midi
    seq.events.clear()
    seq.tracks.clear()
    seq._next_id = 1
    seq._next_track_id = 1

    # Helper: quantize beat
    def q(b: float) -> float:
        step = max(0.03125, float(quant_step))
        return round(b / step) * step

    # Build tracks and events
    for ti, mtrack in enumerate(mid.tracks):
        # skip purely meta tracks with no note messages
        has_notes = any(getattr(m, "type", "") in ("note_on","note_off") for m in mtrack)
        if not has_notes:
            continue

        clef = "treble" if ti == 0 else "treble"
        track_obj = seq.add_track(clef=clef, name=f"MIDI Track {ti+1}")

        current_tick = 0
        # map (channel,note) -> start_tick, velocity
        active: Dict[Tuple[int,int], Tuple[int,int]] = {}

        for msg in mtrack:
            current_tick += msg.time if hasattr(msg, "time") else 0
            if msg.type == "note_on" and msg.velocity > 0:
                key = (int(getattr(msg, "channel", 0)), int(msg.note))
                active[key] = (current_tick, int(msg.velocity))
            elif (msg.type == "note_off") or (msg.type == "note_on" and msg.velocity == 0):
                key = (int(getattr(msg, "channel", 0)), int(msg.note))
                if key in active:
                    st_tick, vel = active.pop(key)
                    en_tick = current_tick
                    start_beat = q(st_tick / tpb)
                    dur_beat = max(float(quant_step), q((en_tick - st_tick) / tpb))
                    seq.add_note(
                        pitch=int(msg.note),
                        start=float(start_beat),
                        duration=float(dur_beat),
                        velocity=int(vel),
                        track_id=int(track_obj.id),
                    )

    # Ensure at least one track exists
    if not seq.tracks:
        seq.add_track("treble", "Spur 1")

    return seq, tempo_bpm
