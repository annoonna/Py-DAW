# ChronoScaleStudio – Live-Playback Worker
# Unterstützt:
# - Legacy: List[int] (Skalen / Quick-Sequenz) → gleichmäßige Viertelnoten
# - Score: List[BaseEvent] (Noten + Pausen + Haltebögen) → Timing gemäß Zeichnung

from __future__ import annotations

from pydaw.notation.qt_compat import QThread, Signal
import time
from typing import Callable, Any, List

from pydaw.notation.audio.direct_synth import SYNTH
from pydaw.notation.music.events import BaseEvent, NoteEvent, RestEvent
from pydaw.notation.music.automation import AutomationLane


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


class PlaybackWorker(QThread):
    """Einfacher, stabiler Monophonie-Player.

    note_changed: Index des aktuell gespielten Events im sortierten Display-Order.
    """
    note_changed = Signal(int)

    def __init__(
        self,
        notes_provider: Callable[[], Any],
        tempo_provider: Callable[[], int],
        loop_provider: Callable[[], bool],
        volume_provider: Callable[[], int] | None = None,
        automation_provider: Callable[[], AutomationLane | None] | None = None,
        start_beat_provider: Callable[[], float] | None = None,
        loop_range_provider: Callable[[], tuple[float, float] | None] | None = None,
    ):
        super().__init__()
        self.notes_provider = notes_provider
        self.tempo_provider = tempo_provider
        self.loop_provider = loop_provider
        self.volume_provider = volume_provider or (lambda: 127)
        self.automation_provider = automation_provider or (lambda: None)
        self.start_beat_provider = start_beat_provider or (lambda: 0.0)
        self.loop_range_provider = loop_range_provider or (lambda: None)

        self._running = True

    def stop(self):
        self._running = False

    # ---------- Legacy ----------
    def _run_int_notes(self, notes: List[int]):
        for i, midi in enumerate(notes):
            if not self._running:
                return

            self.note_changed.emit(i)

            bpm = _clamp_int(self.tempo_provider(), 20, 400)
            duration = 60.0 / bpm

            master = _clamp_int(self.volume_provider(), 0, 127)
            SYNTH.set_channel_volume(master)

            SYNTH.note_on(int(midi), velocity=90)
            time.sleep(duration)
            SYNTH.note_off(int(midi))

        self.note_changed.emit(-1)

    # ---------- Score ----------
    def _merge_ties(self, events: List[BaseEvent]) -> List[BaseEvent]:
        """Fasst Haltebögen zu längeren Noten zusammen (nur gleiche Tonhöhe, direkt anschließend)."""
        merged: List[BaseEvent] = []
        evs = sorted(events, key=lambda e: (e.start, e.duration, getattr(e, "pitch", -1)))
        i = 0
        eps = 1e-6

        while i < len(evs):
            ev = evs[i]
            if isinstance(ev, NoteEvent) and ev.tie_to_next:
                total_dur = ev.duration
                j = i
                while j + 1 < len(evs):
                    nxt = evs[j + 1]
                    if (
                        isinstance(nxt, NoteEvent)
                        and nxt.pitch == ev.pitch
                        and abs(nxt.start - (ev.start + total_dur)) <= 0.01
                    ):
                        total_dur += nxt.duration
                        if not nxt.tie_to_next:
                            j += 1
                            break
                        j += 1
                    else:
                        break

                merged_note = NoteEvent(
                    id=ev.id, pitch=ev.pitch, start=ev.start, duration=total_dur, velocity=ev.velocity, tie_to_next=False
                )
                merged.append(merged_note)
                i = j + 1
                continue

            merged.append(ev)
            i += 1

        return sorted(merged, key=lambda e: (e.start, e.duration))

    def _run_score_events(self, events: List[BaseEvent]):
        bpm = _clamp_int(self.tempo_provider(), 20, 400)
        beat_sec = 60.0 / bpm

        lane = self.automation_provider()
        master = _clamp_int(self.volume_provider(), 0, 127)

        # Für Highlighting: nach Start sortieren (so wie Darstellung)
        ordered = sorted(events, key=lambda e: (e.start, e.duration, getattr(e, "pitch", -1)))

        # Ties für Wiedergabe zusammenfassen
        play_events = self._merge_ties(ordered)

        start_beat = 0.0
        try:
            start_beat = max(0.0, float(self.start_beat_provider()))
        except Exception:
            start_beat = 0.0

        # Optionaler Loop-Bereich (A/B) – nur wenn Loop aktiviert ist
        loop_range = None
        try:
            loop_range = self.loop_range_provider()
        except Exception:
            loop_range = None

        def emit_highlight_for_start(pe_start: float, pe_obj: BaseEvent):
            hi = 0
            tol = 1e-3
            for idx, ev in enumerate(ordered):
                if abs(ev.start - pe_start) <= tol:
                    if isinstance(pe_obj, NoteEvent) and isinstance(ev, NoteEvent) and ev.pitch == pe_obj.pitch:
                        hi = idx
                        break
                    if isinstance(pe_obj, RestEvent) and isinstance(ev, RestEvent):
                        hi = idx
                        break
            self.note_changed.emit(hi)

        def play_pass(pass_events: List[BaseEvent], base_beat: float):
            t0 = time.perf_counter()
            for pe in pass_events:
                if not self._running:
                    return False

                emit_highlight_for_start(pe.start, pe)

                now = time.perf_counter()
                target = t0 + max(0.0, (pe.start - base_beat)) * beat_sec
                if target > now:
                    time.sleep(target - now)

                auto = 1.0
                if lane is not None:
                    try:
                        auto = float(lane.value_at(pe.start))
                    except Exception:
                        auto = 1.0

                cc7 = _clamp_int(round(master * max(0.0, min(1.0, auto))), 0, 127)
                SYNTH.set_channel_volume(cc7)

                if isinstance(pe, RestEvent):
                    time.sleep(max(0.0, pe.duration) * beat_sec)
                    continue

                if isinstance(pe, NoteEvent):
                    vel = _clamp_int(pe.velocity, 1, 127)
                    SYNTH.note_on(pe.pitch, velocity=vel)
                    time.sleep(max(0.0, pe.duration) * beat_sec)
                    SYNTH.note_off(pe.pitch)

            return True

        # Loop-A/B falls gesetzt
        if self.loop_provider() and loop_range and isinstance(loop_range, tuple) and len(loop_range) == 2:
            a = float(loop_range[0])
            b = float(loop_range[1])
            if b > a + 1e-6:
                loop_events = [pe for pe in play_events if (pe.start >= a - 1e-9 and pe.start < b - 1e-9)]
                if not loop_events:
                    self.note_changed.emit(-1)
                    return
                while self._running and self.loop_provider():
                    ok = play_pass(loop_events, base_beat=a)
                    if not ok:
                        return
                self.note_changed.emit(-1)
                return

        # Default: Start ab Playhead
        pass_events = [pe for pe in play_events if pe.start >= start_beat - 1e-9]
        if not pass_events:
            self.note_changed.emit(-1)
            return

        play_pass(pass_events, base_beat=start_beat)
        self.note_changed.emit(-1)


    def run(self):
        while self._running:
            notes = self.notes_provider() or []

            # Legacy (Skala / alte Sequenzen)
            if notes and isinstance(notes[0], int):
                self._run_int_notes(list(notes))
            else:
                self._run_score_events(list(notes))

            if not self.loop_provider():
                break
