"""Clip Launcher Overlay (Drag & Drop Import).

Shown above the Arranger viewport while dragging an audio file from the Browser.
Only the overlay accepts drops while active.

The overlay emits a request so MainWindow can import via ProjectService safely.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QEvent, QPoint, QPropertyAnimation
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGraphicsOpacityEffect,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


AUDIO_EXTS = {".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".mp4"}


@dataclass
class SlotMeta:
    slot_key: str
    track_id: str
    scene: int


def _is_audio_path(p: str) -> bool:
    try:
        return Path(p).suffix.lower() in AUDIO_EXTS
    except Exception:
        return False


class ClipLauncherOverlay(QFrame):
    """Full-viewport overlay that shows a clip-launcher grid and accepts drops."""

    # file_path, track_id, start_beats, slot_key
    request_import_audio = Signal(str, str, float, str)

    def __init__(self, project_service, transport=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._project = project_service
        self._transport = transport
        self._active = False
        self._hover: QWidget | None = None
        self._slot_meta: dict[QWidget, SlotMeta] = {}
        self._drag_label = ""

        self.setObjectName("clipLauncherOverlay")
        self.setAcceptDrops(False)
        self.setVisible(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Opacity / fade
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(140)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addStretch(1)

        self._panel = QFrame(self)
        self._panel.setObjectName("clipLauncherOverlayPanel")
        self._grid = QGridLayout(self._panel)
        self._grid.setContentsMargins(18, 18, 18, 18)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        root.addWidget(self._panel, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)

        self.setStyleSheet(
            """
            QFrame#clipLauncherOverlay { background-color: rgba(10,10,10,200); }
            QFrame#clipLauncherOverlayPanel { background-color: rgba(28,28,28,230); border: 1px solid rgba(255,255,255,25); border-radius: 12px; }
            QFrame#overlaySlot { background-color: rgba(255,255,255,10); border: 1px solid rgba(255,255,255,28); border-radius: 8px; }
            QFrame#overlaySlot[hover="true"] { background-color: rgba(0,200,255,55); border: 2px solid #00C8FF; }
            QLabel#overlaySlotLabel { color: rgba(255,255,255,190); font-size: 10px; }
            QLabel#overlayHint { color: rgba(255,255,255,160); font-size: 12px; }
            """
        )

        self._hint = QLabel("Drop Sample → Slot", self._panel)
        self._hint.setObjectName("overlayHint")
        self._grid.addWidget(self._hint, 0, 0, 1, 1)

    def set_transport(self, transport) -> None:
        self._transport = transport

    def activate(self, drag_label: str = "") -> None:
        self._drag_label = str(drag_label or "")
        self._active = True
        self._rebuild_grid()
        self._set_hover(None)
        self.setAcceptDrops(True)
        self.setVisible(True)
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(float(self._fx.opacity()))
        self._anim.setEndValue(1.0)
        self._anim.start()

    def deactivate(self) -> None:
        if not self.isVisible():
            return
        self._active = False
        self.setAcceptDrops(False)
        self._set_hover(None)
        self._anim.stop()
        self._anim.setStartValue(float(self._fx.opacity()))
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._on_fade_out_done)
        self._anim.start()

    def _on_fade_out_done(self) -> None:
        try:
            self._anim.finished.disconnect(self._on_fade_out_done)
        except Exception:
            pass
        if not self._active:
            self.setVisible(False)


    def _rebuild_grid(self) -> None:
        # Clear old grid (keep hint at 0,0)
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._slot_meta.clear()

        hint_txt = "Drop Sample → Slot"
        if self._drag_label:
            hint_txt = f"Drop: {self._drag_label}"
        self._hint = QLabel(hint_txt, self._panel)
        self._hint.setObjectName("overlayHint")
        self._grid.addWidget(self._hint, 0, 0, 1, 1)

        # Build: 8 scenes x N tracks (excluding master)
        tracks = []
        try:
            tracks = [t for t in (self._project.ctx.project.tracks or []) if getattr(t, "kind", "") != "master"]
        except Exception:
            tracks = []

        # If there are no tracks yet, we still want the Clip-Launcher to be usable.
        # Create a default Audio Track so dropping a sample can immediately create a slot.
        if not tracks:
            try:
                self._project.ensure_audio_track()
                tracks = [t for t in (self._project.ctx.project.tracks or []) if getattr(t, "kind", "") != "master"]
            except Exception:
                pass

        scenes = 8
        for col, t in enumerate(tracks):
            # track title
            lbl = QLabel(str(getattr(t, "name", "Track")), self._panel)
            lbl.setObjectName("overlaySlotLabel")
            self._grid.addWidget(lbl, 1, col + 1)

            for scene in range(scenes):
                r = scene + 2
                scene_idx = scene + 1
                slot_key = f"scene:{scene_idx}:track:{t.id}"
                slot = QFrame(self._panel)
                slot.setObjectName("overlaySlot")
                slot.setProperty("hover", False)

                inner = QVBoxLayout(slot)
                inner.setContentsMargins(6, 6, 6, 6)
                name = "Empty"
                try:
                    cid = self._project.ctx.project.clip_launcher.get(slot_key, "")
                    if cid:
                        cobj = next((c for c in self._project.ctx.project.clips if str(c.id) == str(cid)), None)
                        if cobj:
                            name = str(getattr(cobj, "label", "Clip"))
                except Exception:
                    pass

                lab = QLabel(name, slot)
                lab.setObjectName("overlaySlotLabel")
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                inner.addWidget(lab, 1)

                self._grid.addWidget(slot, r, col + 1)
                self._slot_meta[slot] = SlotMeta(slot_key=slot_key, track_id=str(t.id), scene=int(scene_idx))

        # panel width adapts to content
        self._panel.adjustSize()

    def _set_hover(self, w: QWidget | None) -> None:
        if self._hover is w:
            return
        if self._hover is not None:
            self._hover.setProperty("hover", False)
            self._hover.style().unpolish(self._hover)
            self._hover.style().polish(self._hover)
            self._hover.update()
        self._hover = w
        if self._hover is not None:
            self._hover.setProperty("hover", True)
            self._hover.style().unpolish(self._hover)
            self._hover.style().polish(self._hover)
            self._hover.update()

    # ---- drag & drop

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if not self._active:
            e.ignore()
            return
        md = e.mimeData()
        if md and md.hasUrls():
            u = md.urls()[0]
            path = u.toLocalFile() if u.isLocalFile() else ""
            if path and _is_audio_path(path):
                e.acceptProposedAction()
                return
        e.ignore()

    def dragMoveEvent(self, e: QDragMoveEvent) -> None:
        if not self._active:
            e.ignore()
            return
        md = e.mimeData()
        if not (md and md.hasUrls()):
            e.ignore()
            return
        u = md.urls()[0]
        path = u.toLocalFile() if u.isLocalFile() else ""
        if not (path and _is_audio_path(path)):
            e.ignore()
            return

        pos = e.position().toPoint()
        w = self.childAt(pos)
        # childAt may return label inside the slot; climb to the slot widget
        while w is not None and w not in self._slot_meta and w is not self:
            w = w.parentWidget()
        if w in self._slot_meta:
            self._set_hover(w)
        else:
            self._set_hover(None)

        # IMPORTANT: always accept drag move for audio while overlay is active.
        # This prevents the Arranger canvas from receiving the drag / drop.
        e.acceptProposedAction()

    def dragLeaveEvent(self, e) -> None:
        self._set_hover(None)
        super().dragLeaveEvent(e)

    def dropEvent(self, e: QDropEvent) -> None:
        # IMPORTANT: Never let exceptions escape from Qt virtual overrides.
        # PyQt6 + SIP can turn this into a Qt fatal (SIGABRT).
        try:
            md = e.mimeData()
            if not (md and md.hasUrls()):
                e.ignore(); return
            u = md.urls()[0]
            path = u.toLocalFile() if u.isLocalFile() else ""
            if not (path and _is_audio_path(path)):
                e.ignore(); return

            pos = e.position().toPoint()
            w = self.childAt(pos)
            while w is not None and w not in self._slot_meta and w is not self:
                w = w.parentWidget()
            if w not in self._slot_meta:
                # Drop happened on the overlay but not on a slot.
                # Still accept to block the Arranger from importing the file.
                e.acceptProposedAction()
                return

            meta = self._slot_meta[w]
            # place at playhead, snapped to nearest bar
            beat = 0.0
            bpb = 4.0
            try:
                if self._transport is not None:
                    beat = float(getattr(self._transport, "beat", 0.0))
                    bpb = float(getattr(self._transport, "beats_per_bar")())
            except Exception:
                pass
            if bpb <= 0:
                bpb = 4.0
            snapped = max(0.0, (math.floor((beat + (bpb * 0.5)) / bpb) * bpb))
            self.request_import_audio.emit(str(path), str(meta.track_id), float(snapped), str(meta.slot_key))

            e.acceptProposedAction()
        except Exception:
            try:
                e.ignore()
            except Exception:
                pass
        finally:
            # Always fade out after drop
            try:
                self.deactivate()
            except Exception:
                pass

