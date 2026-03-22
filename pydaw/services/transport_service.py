"""TransportService (v0.0.12).

GUI-safe timing service for playhead + loop region (placeholder, not audio-synced).

v0.0.12 adds:
- Time signature (string, e.g. "4/4", "3/4", "6/8")
- Metronome ticks (signal) on beat boundaries
- Count-in (bars) placeholder before starting playback

Notes:
- Beat unit is a quarter-note beat. Bar length:
    beats_per_bar = numerator * (4 / denominator)
"""

from __future__ import annotations

import math
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class TransportService(QObject):
    playhead_changed = pyqtSignal(float)  # current beat
    playing_changed = pyqtSignal(bool)
    bpm_changed = pyqtSignal(float)
    reset_requested = pyqtSignal()  # request sample-accurate restart (engine)
    loop_changed = pyqtSignal(bool, float, float)  # enabled, start, end
    loop_boundary_reached = pyqtSignal()  # v0.0.20.639: fired when playhead wraps at loop end

    punch_changed = pyqtSignal(bool, float, float)  # enabled, in_beat, out_beat
    punch_triggered = pyqtSignal(str)  # "in" or "out" — fired when playhead crosses boundary

    time_signature_changed = pyqtSignal(str)
    metronome_tick = pyqtSignal(int, int, bool)  # bar_index, beat_in_bar (1..n), is_countin

    def __init__(self, bpm: float = 120.0, time_signature: str = "4/4"):
        super().__init__()
        self.bpm = float(bpm)
        self.time_signature = str(time_signature or "4/4")

        self.playing = False
        self.current_beat = 0.0

        self.loop_enabled = False
        self.loop_start = 0.0
        self.loop_end = 16.0

        # metronome / count-in
        self.metronome_enabled = False
        self.count_in_bars = 0
        self._counting_in = False
        self._countin_remaining_beats = 0
        self._countin_progress = 0.0

        # v0.0.20.637: Punch In/Out (AP2 Phase 2C)
        self.punch_enabled = False
        self.punch_in_beat = 4.0    # default: bar 2
        self.punch_out_beat = 16.0  # default: bar 5
        self.pre_roll_bars = 0      # bars before punch_in to start playback
        self.post_roll_bars = 0     # bars after punch_out to keep playing
        self._punch_in_fired = False   # debounce: only fire once per play
        self._punch_out_fired = False

        self._last_int_beat = -1  # for beat boundary detection

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # v0.0.20.584: 30fps (was 60fps — playhead is smooth enough at 30)
        self._timer.timeout.connect(self._tick)

        # Optional: Externe Clock (Audio-Engine). Wenn gesetzt, wird die
        # Playhead-Position samplegenau aus (playhead_samples, sample_rate)
        # abgeleitet. Das verhindert Drift zwischen GUI-Transport und Audio.
        self._external_playhead_samples: int | None = None
        self._external_sample_rate: float = 44100.0

    # --- compatibility helpers (UI/API)

    @property
    def beat(self) -> float:
        """Kompatibilitäts-Property (ältere UI erwartet transport.beat)."""
        return float(self.current_beat)

    def get_beat(self) -> float:
        """Kompatibilitäts-Methode (ältere UI erwartet transport.get_beat())."""
        return float(self.current_beat)

    # --- external clock (audio-engine)

    def _set_external_playhead_samples(self, playhead_samples: int, sample_rate: float) -> None:
        """Wird von der Audio-Engine aus dem Audio-Thread aufgerufen.

        Keine Qt-Signale, nur atomare Python-Zuweisungen (GIL), damit es
        callback-sicher bleibt.
        """
        self._external_playhead_samples = int(max(0, playhead_samples))
        self._external_sample_rate = float(sample_rate or 44100.0)

    def _clear_external_clock(self) -> None:
        self._external_playhead_samples = None

    # --- time signature helpers

    def beats_per_bar(self) -> float:
        ts = str(self.time_signature or "4/4")
        try:
            num_s, den_s = ts.split("/", 1)
            num = max(1, int(num_s.strip()))
            den = max(1, int(den_s.strip()))
            return float(num) * (4.0 / float(den))
        except Exception:
            return 4.0

    def set_time_signature(self, ts: str) -> None:
        ts = str(ts or "4/4").strip()
        if not ts:
            ts = "4/4"
        self.time_signature = ts
        self.time_signature_changed.emit(ts)

    # --- settings

    def set_metronome(self, enabled: bool) -> None:
        self.metronome_enabled = bool(enabled)

    def set_count_in_bars(self, bars: int) -> None:
        self.count_in_bars = max(0, int(bars))

    # --- punch in/out (v0.0.20.637, AP2 Phase 2C)

    def set_punch(self, enabled: bool) -> None:
        """Enable/disable punch in/out mode."""
        self.punch_enabled = bool(enabled)
        self._punch_in_fired = False
        self._punch_out_fired = False
        self.punch_changed.emit(self.punch_enabled, self.punch_in_beat, self.punch_out_beat)

    def set_punch_region(self, in_beat: float, out_beat: float) -> None:
        """Set punch in/out positions in beats."""
        in_beat = max(0.0, float(in_beat))
        out_beat = max(in_beat + 0.25, float(out_beat))
        self.punch_in_beat = in_beat
        self.punch_out_beat = out_beat
        self._punch_in_fired = False
        self._punch_out_fired = False
        self.punch_changed.emit(self.punch_enabled, self.punch_in_beat, self.punch_out_beat)

    def set_pre_roll_bars(self, bars: int) -> None:
        """Set number of bars to play before punch-in."""
        self.pre_roll_bars = max(0, min(8, int(bars)))

    def set_post_roll_bars(self, bars: int) -> None:
        """Set number of bars to continue playing after punch-out."""
        self.post_roll_bars = max(0, min(8, int(bars)))

    def get_punch_play_start_beat(self) -> float:
        """Get the beat position where play should start with pre-roll.

        Returns punch_in_beat minus pre_roll_bars worth of beats.
        """
        if not self.punch_enabled or self.pre_roll_bars <= 0:
            return self.punch_in_beat
        bpb = self.beats_per_bar()
        pre_beats = float(self.pre_roll_bars) * bpb
        return max(0.0, self.punch_in_beat - pre_beats)

    def get_punch_post_stop_beat(self) -> float:
        """Get the beat position where play should stop after punch-out.

        Returns punch_out_beat plus post_roll_bars worth of beats.
        """
        if not self.punch_enabled or self.post_roll_bars <= 0:
            return self.punch_out_beat
        bpb = self.beats_per_bar()
        post_beats = float(self.post_roll_bars) * bpb
        return self.punch_out_beat + post_beats

    # --- transport controls

    def set_bpm(self, bpm: float) -> None:
        nb = max(10.0, float(bpm))
        try:
            if abs(float(nb) - float(self.bpm)) < 1e-9:
                return
        except Exception:
            pass
        self.bpm = float(nb)
        try:
            self.bpm_changed.emit(self.bpm)
        except Exception:
            pass

    def set_playing(self, playing: bool) -> None:
        playing = bool(playing)
        if self.playing == playing:
            return

        if playing:
            # handle count-in (only if at start)
            if self.count_in_bars > 0 and self.current_beat <= 0.0:
                self._start_count_in()
            else:
                self._counting_in = False
                self._countin_remaining_beats = 0
                self._countin_progress = 0.0
            # v0.0.20.637: Reset punch debounce flags
            self._punch_in_fired = False
            self._punch_out_fired = False
            self._timer.start()
        else:
            self._timer.stop()
            self._counting_in = False
            self._countin_remaining_beats = 0
            self._countin_progress = 0.0

        self.playing = playing
        self.playing_changed.emit(self.playing)

    def toggle_play(self) -> None:
        self.set_playing(not self.playing)

    def stop(self) -> None:
        self.set_playing(False)

    def reset(self) -> None:
        self.current_beat = 0.0
        self._last_int_beat = -1
        # Immediate UI update; engine will perform sample-accurate restart on reset_requested.
        try:
            self._external_playhead_samples = 0
        except Exception:
            pass
        self.playhead_changed.emit(self.current_beat)
        try:
            self.reset_requested.emit()
        except Exception:
            pass

    def rewind(self) -> None:
        self.current_beat = max(0.0, self.current_beat - 4.0)
        self._last_int_beat = int(self.current_beat) - 1
        self.playhead_changed.emit(self.current_beat)

    def fast_forward(self) -> None:
        self.current_beat = self.current_beat + 4.0
        self._last_int_beat = int(self.current_beat) - 1
        self.playhead_changed.emit(self.current_beat)

    def seek(self, beat: float) -> None:
        """Seek the global transport to an absolute beat position.

        Used by rulers/editors to place the playhead without starting playback.
        """
        try:
            self.current_beat = max(0.0, float(beat))
            self._last_int_beat = int(self.current_beat) - 1
            self.playhead_changed.emit(float(self.current_beat))
        except Exception:
            return

    # --- loop

    def set_loop(self, enabled: bool) -> None:
        self.loop_enabled = bool(enabled)
        self.loop_changed.emit(self.loop_enabled, self.loop_start, self.loop_end)

    def set_loop_region(self, start: float, end: float) -> None:
        s = max(0.0, float(start))
        e = max(s + 0.25, float(end))
        self.loop_start = s
        self.loop_end = e
        self.loop_changed.emit(self.loop_enabled, self.loop_start, self.loop_end)

    def ensure_loop_covers(self, end_beat: float, *, snap_to_bar: bool = True) -> None:
        """Auto-extend the loop end so newly created/edited notes are audible.

        This is a DAW-style convenience feature: when looping and the user pastes
        or draws notes beyond the current loop end, the loop region expands to
        include the new material.

        The loop start is preserved. The end is optionally snapped to the next
        bar boundary.
        """
        try:
            if not self.loop_enabled:
                return
            end_beat = float(end_beat)
            if end_beat <= float(self.loop_end) + 1e-6:
                return

            new_end = end_beat
            if snap_to_bar:
                bpb = float(self.beats_per_bar() or 4.0)
                if bpb <= 0:
                    bpb = 4.0
                new_end = math.ceil(end_beat / bpb) * bpb

            # keep sane minimum
            new_end = max(float(self.loop_start) + 0.25, float(new_end))
            self.loop_end = float(new_end)
            self.loop_changed.emit(self.loop_enabled, self.loop_start, self.loop_end)
        except Exception:
            return

    # --- compatibility / external clock glue

    @property
    def beat(self) -> float:
        """Kompatibilität: ältere UI/Handler erwarten transport.beat."""
        return float(self.current_beat)

    def get_beat(self) -> float:
        """Kompatibilität: ältere UI/Handler erwarten transport.get_beat()."""
        return float(self.current_beat)

    def _set_external_playhead_samples(self, playhead_samples: int, sample_rate: float) -> None:
        """Audio-Engine kann den Playhead sample-genau melden.

        Hinweis: Diese Methode wird aus dem Audio-Thread aufgerufen und
        darf keine Qt-Signals auslösen.
        """
        self._external_playhead_samples = int(playhead_samples)
        self._external_sample_rate = float(sample_rate)

    def _clear_external_playhead(self) -> None:
        """Deaktiviert die externe Clock."""
        self._external_playhead_samples = None

    # --- internal count-in/metronome

    def _start_count_in(self) -> None:
        bpb = self.beats_per_bar()
        total = int(max(1, round(self.count_in_bars * bpb)))
        self._counting_in = True
        self._countin_remaining_beats = total
        self._countin_progress = 0.0
        self._last_int_beat = -1  # so the first beat tick fires

    def _emit_metronome_if_boundary(self, beat_value: float, is_countin: bool) -> None:
        # emit on each integer beat boundary
        ib = int(math.floor(beat_value + 1e-6))
        if ib == self._last_int_beat:
            return
        self._last_int_beat = ib

        if not self.metronome_enabled and not is_countin:
            return

        bpb = self.beats_per_bar()
        if bpb <= 0:
            bpb = 4.0

        bar_index = int(math.floor(ib / bpb)) + 1
        beat_in_bar = int(ib - math.floor(ib / bpb) * bpb) + 1
        # beat_in_bar might exceed numerator for exotic cases; keep it sane.
        beat_in_bar = max(1, beat_in_bar)
        self.metronome_tick.emit(bar_index, beat_in_bar, bool(is_countin))

    def _tick(self) -> None:
        if not self.playing:
            return

        bps = self.bpm / 60.0
        dt = self._timer.interval() / 1000.0
        dbeats = bps * dt

        # count-in: do not advance playhead; only count beats
        if self._counting_in:
            self._countin_progress += dbeats
            self._emit_metronome_if_boundary(self._countin_progress, is_countin=True)

            if self._countin_progress >= float(self._countin_remaining_beats):
                # start playback
                self._counting_in = False
                self._countin_remaining_beats = 0
                self._countin_progress = 0.0
                self.current_beat = 0.0
                self._last_int_beat = -1
                self.playhead_changed.emit(self.current_beat)
            return

        # normal play (GUI clock) OR external clock (audio-engine)
        if self._external_playhead_samples is not None:
            # Sample->Beat: seconds = samples / sr, beats = seconds * (bpm/60)
            sr = max(1.0, float(self._external_sample_rate))
            self.current_beat = (float(self._external_playhead_samples) / sr) * (self.bpm / 60.0)
        else:
            self.current_beat += dbeats

            # GUI-seitiges Looping (nur wenn Audio-Clock nicht aktiv ist)
            if self.loop_enabled and self.current_beat >= self.loop_end:
                self.current_beat = self.loop_start
                self._last_int_beat = int(self.current_beat) - 1
                # v0.0.20.639: Notify loop-recording of boundary
                try:
                    self.loop_boundary_reached.emit()
                except Exception:
                    pass

        self._emit_metronome_if_boundary(self.current_beat, is_countin=False)
        self.playhead_changed.emit(self.current_beat)

        # v0.0.20.637: Punch boundary detection
        if self.punch_enabled:
            try:
                cb = float(self.current_beat)
                # Punch In: playhead reached punch_in_beat
                if not self._punch_in_fired and cb >= self.punch_in_beat:
                    self._punch_in_fired = True
                    self.punch_triggered.emit("in")
                # Punch Out: playhead reached punch_out_beat
                if not self._punch_out_fired and cb >= self.punch_out_beat:
                    self._punch_out_fired = True
                    self.punch_triggered.emit("out")
                # Auto-stop after post-roll
                if self._punch_out_fired and self.post_roll_bars >= 0:
                    stop_beat = self.get_punch_post_stop_beat()
                    if cb >= stop_beat:
                        self.set_playing(False)
            except Exception:
                pass
