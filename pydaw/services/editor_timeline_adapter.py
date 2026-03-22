"""Editor Timeline Adapter — Entkopplung der Editor-Zeitquelle.

Phase C (Vorbau): Der Adapter berechnet den aktuell gültigen Editor-Playhead
aus dem globalen Transport und dem EditorFocusContext. Editoren hören auf
diesen Adapter statt direkt auf ``TransportService.playhead_changed``.

FEATURE-FLAG: ``editor_dual_clock_enabled`` (Default: False).
Wenn deaktiviert, gibt der Adapter einfach den globalen Beat 1:1 weiter.

Umrechnungsregeln (aus dem Design-Dokument §6):

    Arranger-Fokus:
        local = max(0.0, global_beat - clip.start_beats)

    Launcher-Fokus, Slot spielt:
        span = loop_end - loop_start
        local = loop_start + max(0.0, global_beat - voice_start_beat) % span

    Launcher-Fokus, Slot spielt nicht:
        Editor bleibt auf letzter Edit-Position (kein Playhead-Zwang).

v0.0.20.612 — 2026-03-19 — Phase C Vorbau
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from pydaw.services.editor_focus import EditorFocusContext, LauncherSlotRuntimeState

if TYPE_CHECKING:
    from pydaw.services.transport_service import TransportService
    from pydaw.services.cliplauncher_playback import ClipLauncherPlaybackService


class EditorTimelineAdapter(QObject):
    """Berechnet den aktuell gültigen Editor-Playhead.

    Signals:
        playhead_changed(float): Lokaler Beat für den aktuell fokussierten Editor.
        focus_changed(EditorFocusContext): Neuer Fokuskontext wurde gesetzt.
    """

    playhead_changed = Signal(float)
    focus_changed = Signal(object)  # EditorFocusContext

    def __init__(
        self,
        transport: TransportService,
        launcher_playback: Optional[ClipLauncherPlaybackService] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._transport = transport
        self._launcher_playback = launcher_playback
        self._focus: Optional[EditorFocusContext] = None
        self._last_local_beat: float = 0.0

        # Feature-Flag: Wenn False, wird global_beat 1:1 durchgereicht
        # v0.0.20.613: Aktiviert — Arranger-Modus ist Passthrough (identisch),
        # Launcher-Modus berechnet lokale Slot-Zeit
        self.editor_dual_clock_enabled: bool = True

        # Verbinde mit dem globalen Transport
        self._transport.playhead_changed.connect(self._on_global_playhead)

        # Optionaler Polling-Timer für Launcher-Snapshot-Refresh (30 Hz)
        self._snapshot_timer = QTimer(self)
        self._snapshot_timer.setInterval(33)
        self._snapshot_timer.timeout.connect(self._poll_launcher_snapshot)
        self._cached_snapshot: Optional[LauncherSlotRuntimeState] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_focus(self, ctx: Optional[EditorFocusContext]) -> None:
        """Setze den aktuellen Editor-Fokuskontext.

        Startet/Stoppt den Snapshot-Polling-Timer je nach Fokus-Quelle.

        Args:
            ctx: Neuer EditorFocusContext oder None zum Zurücksetzen.
        """
        self._focus = ctx
        self._cached_snapshot = None

        # Polling nur bei Launcher-Fokus + Feature-Flag aktiv
        if ctx is not None and ctx.is_launcher and self.editor_dual_clock_enabled:
            if not self._snapshot_timer.isActive():
                self._snapshot_timer.start()
        else:
            if self._snapshot_timer.isActive():
                self._snapshot_timer.stop()

        if ctx is not None:
            self.focus_changed.emit(ctx)

    def get_focus(self) -> Optional[EditorFocusContext]:
        """Aktuellen Fokuskontext abrufen."""
        return self._focus

    def get_last_local_beat(self) -> float:
        """Letzter berechneter lokaler Beat."""
        return self._last_local_beat

    def get_cached_snapshot(self) -> Optional[LauncherSlotRuntimeState]:
        """Letzter gecachter Launcher-Snapshot."""
        return self._cached_snapshot

    # ------------------------------------------------------------------
    # Internal: Playhead-Umrechnung
    # ------------------------------------------------------------------

    def _on_global_playhead(self, global_beat: float) -> None:
        """Empfängt globalen Transport-Beat und rechnet um."""
        global_beat = float(global_beat)

        if not self.editor_dual_clock_enabled or self._focus is None:
            # Passthrough: 1:1 wie bisher
            self._last_local_beat = global_beat
            self.playhead_changed.emit(global_beat)
            return

        local = self._compute_local_beat(global_beat)
        self._last_local_beat = local
        self.playhead_changed.emit(local)

    def _compute_local_beat(self, global_beat: float) -> float:
        """Berechne den Beat-Wert den die Editoren empfangen sollen.

        WICHTIG: Die Editoren (PianoRoll, Notation, AudioEditor) subtrahieren
        intern bereits ``clip_start_beats``. Deshalb:

        - Arranger-Fokus: Passthrough (global_beat) — Editoren rechnen selbst
        - Launcher-Fokus: Lokaler Beat — Editoren subtrahieren 0 (launcher clips
          haben ``start_beats=0``), Ergebnis korrekt

        Returns:
            Beat-Wert für die Editor-Playhead-Darstellung.
        """
        ctx = self._focus
        if ctx is None:
            return global_beat

        if ctx.is_arranger:
            # Arranger-Fokus: Passthrough — die Editoren subtrahieren
            # clip_start_beats intern selbst (PianoRollCanvas Zeile 959,
            # AudioEditor._local_playhead_beats, etc.)
            return global_beat

        # Launcher-Fokus
        snap = self._cached_snapshot

        if snap is not None and snap.is_playing and snap.voice_start_beat is not None:
            # Slot spielt: verwende voice_start_beat als Referenz
            return snap.compute_local_beat(global_beat)

        # Slot spielt nicht: letzte bekannte Position beibehalten
        return self._last_local_beat

    # ------------------------------------------------------------------
    # Internal: Launcher-Snapshot-Polling
    # ------------------------------------------------------------------

    def _poll_launcher_snapshot(self) -> None:
        """Pollt den Launcher-Playback-Service für aktuellen Slot-State."""
        if self._launcher_playback is None or self._focus is None:
            return
        if not self._focus.is_launcher or not self._focus.slot_key:
            return
        try:
            snap = self._launcher_playback.get_runtime_snapshot(self._focus.slot_key)
            self._cached_snapshot = snap
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Sauberes Aufräumen."""
        try:
            self._snapshot_timer.stop()
        except Exception:
            pass
        try:
            self._transport.playhead_changed.disconnect(self._on_global_playhead)
        except Exception:
            pass
