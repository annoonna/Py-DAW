
# ChronoScaleStudio – Sequenz (Noten + Pausen + Haltebögen + Automationen + Spuren)
from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional, Dict, Iterable, Any

from pydaw.notation.music.events import NoteEvent, RestEvent, BaseEvent
from pydaw.notation.music.automation import AutomationLane
from pydaw.notation.music.tracks import Track, Clef


class NoteSequence:
    def __init__(self):
        self._next_id = 1
        self._next_track_id = 1

        self.events: List[BaseEvent] = []
        self.tracks: List[Track] = []

        # Default: eine Treble-Spur
        self.add_track(clef="treble", name="Spur 1")

        # Automations-Lanes (global; später pro Track möglich)
        self.automation: Dict[str, AutomationLane] = {
            "volume": AutomationLane("volume", default=1.0),  # 0..1
        }

    # ---------- IDs ----------
    def _new_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def _new_track_id(self) -> int:
        i = self._next_track_id
        self._next_track_id += 1
        return i

    # ---------- Tracks ----------
    def add_track(self, clef: Clef = "treble", name: str | None = None) -> Track:
        tid = self._new_track_id()
        if name is None:
            name = f"Spur {tid}"
        channel = (tid - 1) % 16
        tr = Track(id=tid, name=name, clef=clef, midi_channel=channel, mute=False, solo=False)
        self.tracks.append(tr)
        return tr

    def get_track(self, track_id: int) -> Optional[Track]:
        for t in self.tracks:
            if t.id == track_id:
                return t
        return None

    def set_track_mute(self, track_id: int, mute: bool):
        t = self.get_track(track_id)
        if t:
            t.mute = bool(mute)

    def set_track_solo(self, track_id: int, solo: bool):
        t = self.get_track(track_id)
        if t:
            t.solo = bool(solo)

    def any_solo(self) -> bool:
        return any(t.solo for t in self.tracks)

    def active_track_ids_for_playback(self) -> set[int]:
        if self.any_solo():
            return {t.id for t in self.tracks if t.solo}
        return {t.id for t in self.tracks if not t.mute}

    # ---------- Events hinzufügen ----------
    def add_note(self, pitch: int, start: float, duration: float, velocity: int = 90, track_id: int = 1) -> NoteEvent:
        ev = NoteEvent(
            id=self._new_id(),
            pitch=int(pitch),
            start=float(start),
            duration=float(duration),
            velocity=int(velocity),
            tie_to_next=False,
            track_id=int(track_id),
        )
        self.events.append(ev)
        return ev

    def add_rest(self, start: float, duration: float, track_id: int = 1) -> RestEvent:
        ev = RestEvent(id=self._new_id(), start=float(start), duration=float(duration), track_id=int(track_id))
        self.events.append(ev)
        return ev

    # ---------- Bearbeiten ----------
    def get_event(self, event_id: int) -> Optional[BaseEvent]:
        for ev in self.events:
            if ev.id == event_id:
                return ev
        return None

    def remove_event(self, event_id: int) -> bool:
        before = len(self.events)
        self.events = [e for e in self.events if e.id != event_id]
        return len(self.events) != before

    def remove_events(self, event_ids: Iterable[int]) -> bool:
        ids = set(event_ids)
        before = len(self.events)
        self.events = [e for e in self.events if e.id not in ids]
        return len(self.events) != before

    def clear(self):
        self.events.clear()
        # Tracks bleiben erhalten

    def sorted_events(self) -> List[BaseEvent]:
        return sorted(self.events, key=lambda e: (e.start, e.duration, getattr(e, "pitch", -1)))

    def sorted_events_for_track(self, track_id: int) -> List[BaseEvent]:
        return sorted([e for e in self.events if int(getattr(e, "track_id", 1)) == int(track_id)], key=lambda e: (e.start, e.duration, getattr(e, "pitch", -1)))

    # Legacy (für Skalen/MIDI-Quick-Export)
    def get_notes(self) -> List[int]:
        return [e.pitch for e in self.sorted_events() if isinstance(e, NoteEvent)]

    def clone_event(self, event_id: int) -> Optional[BaseEvent]:
        """Dupliziert ein Event (Note oder Pause) als neues Event mit neuer ID."""
        ev = self.get_event(event_id)
        if ev is None:
            return None

        if isinstance(ev, NoteEvent):
            clone = NoteEvent(
                id=self._new_id(),
                pitch=int(ev.pitch),
                start=float(ev.start),
                duration=float(ev.duration),
                velocity=int(ev.velocity),
                tie_to_next=bool(ev.tie_to_next),
                track_id=int(getattr(ev, "track_id", 1)),
            )
            self.events.append(clone)
            return clone

        if isinstance(ev, RestEvent):
            clone = RestEvent(
                id=self._new_id(),
                start=float(ev.start),
                duration=float(ev.duration),
                track_id=int(getattr(ev, "track_id", 1)),
            )
            self.events.append(clone)
            return clone

        return None

    # ---------- Serialize (für Projekt Save/Open) ----------
    def to_dict(self) -> dict:
        return {
            "tracks": [asdict(t) for t in self.tracks],
            "events": [self._event_to_dict(e) for e in self.events],
            "automation": {k: v.to_dict() for k, v in self.automation.items()},
            "meta": {
                "next_id": self._next_id,
                "next_track_id": self._next_track_id,
            },
        }

    def _event_to_dict(self, e: BaseEvent) -> dict:
        d = {
            "id": int(e.id),
            "start": float(e.start),
            "duration": float(e.duration),
            "track_id": int(getattr(e, "track_id", 1)),
            "type": "rest" if isinstance(e, RestEvent) else "note",
        }
        if isinstance(e, NoteEvent):
            d.update({
                "pitch": int(e.pitch),
                "velocity": int(e.velocity),
                "tie_to_next": bool(e.tie_to_next),
            })
        return d

    @staticmethod
    def from_dict(data: dict) -> "NoteSequence":
        seq = NoteSequence()
        # Reset default
        seq.events.clear()
        seq.tracks.clear()
        seq._next_id = 1
        seq._next_track_id = 1

        # Tracks
        for t in data.get("tracks", []) or []:
            tr = Track(
                id=int(t.get("id", seq._new_track_id())),
                name=str(t.get("name", f"Spur {t.get('id', 1)}")),
                clef=str(t.get("clef", "treble")) if str(t.get("clef", "treble")) in ("treble","bass") else "treble",
                midi_channel=int(t.get("midi_channel", 0)) % 16,
                mute=bool(t.get("mute", False)),
                solo=bool(t.get("solo", False)),
            )
            seq.tracks.append(tr)
            seq._next_track_id = max(seq._next_track_id, tr.id + 1)

        if not seq.tracks:
            seq.add_track("treble", "Spur 1")

        # Events
        for e in data.get("events", []) or []:
            et = e.get("type", "note")
            if et == "rest":
                ev = RestEvent(
                    id=int(e["id"]),
                    start=float(e["start"]),
                    duration=float(e["duration"]),
                    track_id=int(e.get("track_id", 1)),
                )
            else:
                ev = NoteEvent(
                    id=int(e["id"]),
                    start=float(e["start"]),
                    duration=float(e["duration"]),
                    track_id=int(e.get("track_id", 1)),
                    pitch=int(e.get("pitch", 60)),
                    velocity=int(e.get("velocity", 90)),
                    tie_to_next=bool(e.get("tie_to_next", False)),
                )
            seq.events.append(ev)
            seq._next_id = max(seq._next_id, ev.id + 1)

        # Automation
        auto = data.get("automation", {}) or {}
        seq.automation = {}
        for k, v in auto.items():
            try:
                seq.automation[k] = AutomationLane.from_dict(v)
            except Exception:
                pass
        if "volume" not in seq.automation:
            seq.automation["volume"] = AutomationLane("volume", default=1.0)

        # Meta
        meta = data.get("meta", {}) or {}
        seq._next_id = max(seq._next_id, int(meta.get("next_id", seq._next_id)))
        seq._next_track_id = max(seq._next_track_id, int(meta.get("next_track_id", seq._next_track_id)))
        return seq
