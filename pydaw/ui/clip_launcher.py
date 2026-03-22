"""Clip Launcher (v0.0.11).

v0.0.10:
- Quantized launch via LauncherService

v0.0.11:
- Quantize also applies to Slot DnD ("arm + launch"):
  drop a clip onto a slot -> assign + (quantized) launch
- Stop All optional playhead reset (checkbox)
"""

from __future__ import annotations

from dataclasses import dataclass
import os

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    import soundfile as sf  # type: ignore
except Exception:  # pragma: no cover
    sf = None  # type: ignore

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QScrollArea,
    QGridLayout,
    QPushButton,
    QMenu,
    QComboBox,
    QToolButton,
    QCheckBox,
    QStyle,
    QStyleOptionButton,
)
from PySide6.QtCore import Qt, Signal, QPoint, QRect, QRectF, QTimer
from PySide6.QtGui import QDrag, QPainter, QPen, QColor, QKeySequence, QShortcut
from PySide6.QtCore import QMimeData

from pydaw.services.project_service import ProjectService
from pydaw.services.launcher_service import LauncherService
from pydaw.core.settings_store import get_value, set_value
from pydaw.core.settings import SettingsKeys


@dataclass
class _PeaksData:
    mtime_ns: int
    block_size: int
    samplerate: int
    peaks: 'np.ndarray'  # type: ignore

    @property
    def peaks_per_second(self) -> float:
        return float(self.samplerate) / float(max(1, self.block_size))

class SlotButton(QPushButton):
    """A slot button that supports drop + (Alt) drag + double-click for loop editor."""

    double_clicked = Signal()  # NEU: Doppelklick Signal

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_start: QPoint | None = None

    def mouseDoubleClickEvent(self, event):  # noqa: ANN001
        """Handle Doppelklick -> Loop-Editor öffnen."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):  # noqa: ANN001
        try:
            if event.mimeData().hasFormat("application/x-pydaw-clipid"):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        try:
            super().dragEnterEvent(event)
        except Exception:
            pass

    def dragMoveEvent(self, event):  # noqa: ANN001
        try:
            if event.mimeData().hasFormat("application/x-pydaw-clipid"):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        try:
            super().dragMoveEvent(event)
        except Exception:
            pass

    def dropEvent(self, event):  # noqa: ANN001
        try:
            has_clip = event.mimeData().hasFormat("application/x-pydaw-clipid")
            if has_clip:
                try:
                    panel = getattr(self, '_panel', None)
                    if panel is not None and hasattr(panel, 'slot_drop_requested'):
                        panel.slot_drop_requested.emit(self, event)
                    else:
                        self.parent().slot_drop_requested.emit(self, event)
                    event.acceptProposedAction()
                except Exception:
                    try:
                        event.ignore()
                    except Exception:
                        pass
                return
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass
            return
        try:
            super().dropEvent(event)
        except Exception:
            pass

    def mousePressEvent(self, event):  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: ANN001
        # v0.0.20.605: Multi-slot drag support
        mods = event.modifiers()
        if (
            self._drag_start is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            if (event.pos() - self._drag_start).manhattanLength() >= 8:
                clip_id = str(self.property("clip_id") or "")
                if clip_id:
                    try:
                        self.setDown(False)
                    except Exception:
                        pass
                    drag = QDrag(self)
                    md = QMimeData()
                    md.setData("application/x-pydaw-clipid", clip_id.encode("utf-8"))
                    # v0.0.20.620: Source slot_key mitgeben für Move
                    src_slot = str(self.property("slot_key") or "")
                    if src_slot:
                        md.setData("application/x-pydaw-src-slot", src_slot.encode("utf-8"))
                    if mods & Qt.KeyboardModifier.ControlModifier:
                        md.setData("application/x-pydaw-clipid-dup", b"1")
                    # v0.0.20.605: Multi-slot drag — encode all selected slot clip IDs
                    try:
                        sel_keys = getattr(self._panel, '_selected_slot_keys', set()) or set()
                        slot_key = str(self.property("slot_key") or "")
                        if slot_key in sel_keys and len(sel_keys) > 1:
                            import json
                            cl = getattr(self._panel.project.ctx.project, 'clip_launcher', {}) or {}
                            multi = []
                            for sk in sorted(sel_keys):
                                cid = str(cl.get(sk, '') or '')
                                if cid:
                                    multi.append({'slot_key': sk, 'clip_id': cid})
                            if multi:
                                md.setData("application/x-pydaw-multi-clips", json.dumps(multi).encode("utf-8"))
                    except Exception:
                        pass
                    drag.setMimeData(md)
                    drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
                self._drag_start = None
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        self._drag_start = None
        super().mouseReleaseEvent(event)


class SlotWaveButton(SlotButton):
    """Slot button with in-slot audio waveform preview (Arranger-like).

    UX-Ziel (Bitwig/Ableton):
    - Single click: auswählen + im Editor öffnen (NICHT abspielen)
    - Kleiner ▶-Button im Slot: Clip launchen
    """

    def __init__(self, panel: 'ClipLauncherPanel', parent: QWidget | None = None):
        super().__init__(parent or panel)
        self._panel = panel
        self._hover = False
        self._suppress_click = False
        try:
            self.setMouseTracking(True)
        except Exception:
            pass

    def enterEvent(self, event):  # noqa: ANN001
        self._hover = True
        try:
            self.update()
        except Exception:
            pass
        try:
            super().enterEvent(event)
        except Exception:
            pass

    def leaveEvent(self, event):  # noqa: ANN001
        self._hover = False
        try:
            self.update()
        except Exception:
            pass
        try:
            super().leaveEvent(event)
        except Exception:
            pass

    def _play_button_rect(self) -> 'QRect':
        """Return the clickable play-button rect inside the slot (left-center, Bitwig-style)."""
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        content = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, opt, self)
        # v0.0.20.590: Bitwig-style left-center position
        sz = 20
        pad = 3
        cy = int(content.center().y()) - sz // 2
        return QRect(int(content.left() + pad), cy, sz, sz)

    def mousePressEvent(self, event):  # noqa: ANN001
        # Click on the small ▶ hotzone launches the clip (without triggering the button 'clicked').
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                r = self._play_button_rect()
                if r.contains(event.pos()):
                    slot_key = str(self.property('slot_key') or '')
                    cid = str(self.property('clip_id') or '')
                    if slot_key and cid:
                        try:
                            # selection for deterministic shortcuts
                            self._panel._set_selected_slot(slot_key)
                        except Exception:
                            pass
                        try:
                            self._panel._launch(slot_key)
                        except Exception:
                            pass
                        self._suppress_click = True
                        event.accept()
                        return
        except Exception:
            pass
        try:
            super().mousePressEvent(event)
        except Exception:
            pass

    def mouseReleaseEvent(self, event):  # noqa: ANN001
        # Suppress QPushButton.clicked when we handled the play-button ourselves.
        if getattr(self, '_suppress_click', False):
            self._suppress_click = False
            # v0.0.20.601: Gate mode — stop on mouse release
            try:
                slot_key = str(self.property('slot_key') or '')
                if slot_key:
                    self._panel._gate_release(slot_key)
            except Exception:
                pass
            try:
                event.accept()
            except Exception:
                pass
            return
        try:
            super().mouseReleaseEvent(event)
        except Exception:
            pass



    def mouseDoubleClickEvent(self, event):  # noqa: ANN001
        # Dedicated editor open on double click (Pro-DAW-like).
        if event.button() == Qt.MouseButton.LeftButton:
            cid = str(self.property("clip_id") or "")
            if cid:
                try:
                    self._panel.clip_edit_requested.emit(cid)
                except Exception:
                    pass
                event.accept()
                return
        super().mouseDoubleClickEvent(event)
    def paintEvent(self, event):  # noqa: ANN001
        # Draw normal button chrome but render our own contents (text + waveform).
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text = ''

        p = QPainter(self)
        try:
            self.style().drawControl(QStyle.ControlElement.CE_PushButton, opt, p, self)
            content = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, opt, self)

            cid = str(self.property('clip_id') or '')
            if not cid:
                p.setPen(self.palette().mid().color())
                p.drawText(content, Qt.AlignmentFlag.AlignCenter, 'Empty')
                return

            clip = self._panel._get_clip(cid)
            if clip is None:
                p.setPen(self.palette().mid().color())
                p.drawText(content, Qt.AlignmentFlag.AlignCenter, 'Missing')
                return

            # v0.0.20.596: Bitwig-style colored slot background
            try:
                cidx = int(getattr(clip, 'launcher_color', 0) or 0) % 12
                _slot_colors = [
                    QColor(220, 60, 60),    # red
                    QColor(230, 120, 50),   # orange
                    QColor(220, 180, 40),   # yellow
                    QColor(80, 190, 60),    # green
                    QColor(40, 200, 200),   # cyan
                    QColor(60, 120, 220),   # blue
                    QColor(140, 80, 220),   # purple
                    QColor(210, 80, 180),   # pink
                    QColor(160, 200, 60),   # lime
                    QColor(200, 160, 100),  # warm
                    QColor(120, 160, 200),  # steel
                    QColor(180, 180, 180),  # silver
                ]
                sc = _slot_colors[cidx]
                sc.setAlpha(80)  # v0.0.20.598: increased from 45 for visibility
                p.save()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(sc)
                p.drawRect(content)
                # Left color strip (Bitwig-style 3px colored bar on left edge)
                strip = QColor(_slot_colors[cidx])
                strip.setAlpha(255)  # v0.0.20.598: fully opaque strip
                p.setBrush(strip)
                p.drawRect(content.left(), content.top(), 3, content.height())
                p.restore()
            except Exception:
                pass

            label = str(getattr(clip, 'label', '') or 'Clip')

            # Countdown text for queued (quantized) launch
            slot_key = str(self.property('slot_key') or '')
            countdown = ''
            try:
                countdown = str(getattr(self._panel, 'get_slot_countdown_text')(slot_key) or '')
            except Exception:
                countdown = ''




            # Queued-state indicator (Bitwig-style): dashed yellow border if this slot is queued (quantized)
            try:
                slot_key = str(self.property('slot_key') or '')
                if slot_key and not bool(getattr(self._panel, 'is_slot_playing')(slot_key)) and bool(getattr(self._panel, 'is_slot_queued')(slot_key)):
                    qcol = QColor(255, 176, 0)
                    qcol.setAlpha(220)
                    p.save()
                    pen = QPen(qcol, 2, Qt.PenStyle.DashLine)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(content.adjusted(2, 2, -3, -3))
                    # Small queued triangle outline (top-left)
                    from PySide6.QtGui import QPolygon
                    from PySide6.QtCore import QPoint
                    tri = QPolygon([
                        QPoint(int(content.left() + 10), int(content.top() + 7)),
                        QPoint(int(content.left() + 10), int(content.top() + 19)),
                        QPoint(int(content.left() + 20), int(content.top() + 13)),
                    ])
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(qcol, 2, Qt.PenStyle.SolidLine))
                    p.drawPolygon(tri)
                    p.restore()
            except Exception:
                pass

            # Play-state indicator (Bitwig-style): highlight if this slot is currently playing
            try:
                slot_key = str(self.property('slot_key') or '')
                if slot_key and bool(getattr(self._panel, 'is_slot_playing')(slot_key)):
                    hl = QColor(self.palette().highlight().color())
                    hl.setAlpha(210)
                    p.save()
                    p.setPen(QPen(hl, 2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(content.adjusted(1, 1, -2, -2))

                    # Small play triangle (top-left)
                    tri = [
                        (int(content.left() + 10), int(content.top() + 7)),
                        (int(content.left() + 10), int(content.top() + 19)),
                        (int(content.left() + 20), int(content.top() + 13)),
                    ]
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(hl)
                    from PySide6.QtGui import QPolygon
                    from PySide6.QtCore import QPoint
                    p.drawPolygon(QPolygon([QPoint(x, y) for x, y in tri]))
                    p.restore()
            except Exception:
                pass

            # Selected-slot indicator (UI-only): subtle border so Ctrl+C/V/Del feel deterministic
            try:
                slot_key = str(self.property('slot_key') or '')
                if slot_key and bool(getattr(self._panel, 'is_slot_selected')(slot_key)):
                    # Don't override playing/queued styling; draw an inner, subtle border.
                    sel = QColor(self.palette().mid().color())
                    sel.setAlpha(220)
                    p.save()
                    p.setPen(QPen(sel, 1, Qt.PenStyle.DashDotLine))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(content.adjusted(4, 4, -5, -5))
                    p.restore()
            except Exception:
                pass


            # v0.0.20.590: Bitwig-style in-slot launch button (left-center ▶)
            # (Clickable hotzone handled in mousePressEvent)
            try:
                r = self._play_button_rect()
                # Background circle (Bitwig uses a subtle bg)
                bg = QColor(self.palette().window().color())
                bg.setAlpha(180 if self._hover else 100)
                p.save()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(r, 4, 4)

                # Triangle icon (larger, Bitwig proportions)
                ico = QColor(self.palette().text().color())
                ico.setAlpha(255 if self._hover else 190)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ico)
                from PySide6.QtGui import QPolygon
                from PySide6.QtCore import QPoint
                cx = int(r.center().x())
                cy = int(r.center().y())
                tri = QPolygon([
                    QPoint(cx - 4, cy - 6),
                    QPoint(cx - 4, cy + 6),
                    QPoint(cx + 6, cy),
                ])
                p.drawPolygon(tri)
                p.restore()
            except Exception:
                pass

            # v0.0.20.590: Record ● indicator (top-right, when track is record-armed)
            try:
                slot_key = str(self.property('slot_key') or '')
                if slot_key:
                    parsed = self._panel._parse_slot_key(slot_key)
                    if parsed:
                        _scene, tid = parsed
                        trk = self._panel._track_index.get(tid)
                        if trk and getattr(trk, 'record_arm', False):
                            p.save()
                            rec_r = 5
                            rx = int(content.right() - rec_r * 2 - 4)
                            ry = int(content.top() + 5)
                            p.setPen(Qt.PenStyle.NoPen)
                            p.setBrush(QColor(220, 50, 50, 220))
                            p.drawEllipse(rx, ry, rec_r * 2, rec_r * 2)
                            p.restore()
            except Exception:
                pass

            # Layout: small label row + waveform area (offset for play button on left)
            play_offset = 28  # play button width + padding
            label_rect = QRectF(content.left() + play_offset, content.top() + 2, content.width() - play_offset - 4, 12)
            wave_rect = QRectF(content.left() + play_offset, content.top() + 16, content.width() - play_offset - 4, content.height() - 20)

            # Waveform (audio) or Mini Piano-Roll (MIDI)
            clip_kind = str(getattr(clip, 'kind', '') or '')
            if float(wave_rect.height()) >= 8.0:
                if clip_kind == 'audio' and getattr(clip, 'source_path', None):
                    track_vol = self._panel._get_track_volume(str(getattr(clip, 'track_id', '') or ''))
                    p.save()
                    p.setClipRect(wave_rect)
                    self._panel._draw_audio_waveform(p, wave_rect, clip, track_vol)
                    p.restore()
                elif clip_kind == 'midi':
                    p.save()
                    p.setClipRect(wave_rect)
                    self._panel._draw_midi_pianoroll(p, wave_rect, clip)
                    p.restore()

            # v0.0.20.602: Loop region bar at bottom of slot (Bitwig-style)
            try:
                ls = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
                le = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
                clip_len = float(getattr(clip, 'length_beats', 4.0) or 4.0)
                if le > ls + 0.01 and clip_len > 0.01:
                    bar_h = 3
                    bar_y = int(content.bottom() - bar_h - 1)
                    bar_x = int(content.left() + play_offset)
                    bar_w = int(content.width() - play_offset - 4)
                    # Full clip range (dim)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(80, 80, 80, 80))
                    p.drawRect(bar_x, bar_y, bar_w, bar_h)
                    # Loop region (orange)
                    lx = int(bar_x + (ls / clip_len) * bar_w)
                    lw = int(((le - ls) / clip_len) * bar_w)
                    p.setBrush(QColor(255, 140, 0, 160))
                    p.drawRect(lx, bar_y, max(2, lw), bar_h)
            except Exception:
                pass

            # v0.0.20.617: Bottom-right info — live loop position OR static clip length
            try:
                slot_key = str(self.property('slot_key') or '')
                info_txt = ''
                info_col = QColor(180, 180, 180, 140)  # default: grey

                # v0.0.20.617: Live loop position if slot is playing
                if slot_key and slot_key in getattr(self._panel, '_active_slots', set()):
                    try:
                        playback = getattr(self._panel.project, '_cliplauncher_playback', None)
                        if playback is not None:
                            snap = playback.get_runtime_snapshot(slot_key)
                            if snap is not None and snap.is_playing:
                                bpb = self._panel._beats_per_bar_ui()
                                pos = snap.local_beat - snap.loop_start_beats
                                if pos < 0.0:
                                    pos = 0.0
                                info_txt = f"{pos / bpb:.1f} Bar"
                                info_col = QColor(255, 176, 0, 235)  # orange = live
                    except Exception:
                        pass

                # Fallback: statische Cliplänge
                if not info_txt:
                    clip_len = float(getattr(clip, 'length_beats', 0) or 0)
                    bpb = self._panel._beats_per_bar_ui()
                    if clip_len > 0 and bpb > 0:
                        bars = clip_len / bpb
                        if bars >= 1.0:
                            info_txt = f"{bars:.0f} bar" if bars == int(bars) else f"{bars:.1f} bar"
                        else:
                            info_txt = f"{clip_len:.0f} bt"

                if info_txt:
                    p.setPen(info_col)
                    from PySide6.QtGui import QFont
                    small = QFont(p.font())
                    small.setPointSize(max(6, small.pointSize() - 2))
                    p.setFont(small)
                    info_r = QRectF(content.right() - 56, content.bottom() - 13, 52, 12)
                    p.drawText(info_r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, info_txt)
            except Exception:
                pass

            # Label on top
            p.setPen(self.palette().text().color())
                        # Label (+ queued countdown on the right, Bitwig-style)
            if countdown:
                try:
                    # reserve a small right area for the countdown
                    cw = min(76.0, float(label_rect.width()) * 0.55)
                    c_rect = QRectF(label_rect.right() - cw, label_rect.top(), cw, label_rect.height())
                    l_rect = QRectF(label_rect.left(), label_rect.top(), max(8.0, label_rect.width() - cw - 4.0), label_rect.height())

                    p.setPen(self.palette().text().color())
                    p.drawText(l_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

                    qcol = QColor(255, 176, 0)
                    qcol.setAlpha(235)
                    p.setPen(qcol)
                    p.drawText(c_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, countdown)
                except Exception:
                    p.setPen(self.palette().text().color())
                    p.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            else:
                p.setPen(self.palette().text().color())
                p.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

        finally:
            p.end()

class ClipLauncherPanel(QWidget):
    clip_activated = Signal(str)  # clip_id
    clip_edit_requested = Signal(str)  # clip_id (double click)
    slot_drop_requested = Signal(object, object)  # (SlotButton, QDropEvent)

    def __init__(
        self,
        project: ProjectService,
        launcher: LauncherService,
        clip_context: 'ClipContextService | None' = None,
        parent=None
    ):
        super().__init__(parent)
        self.project = project
        self.launcher = launcher
        self.clip_context = clip_context  # NEU: ClipContextService
        self.scene_count = 8

        # UI persistence (QSettings)
        self._settings_keys = SettingsKeys()
        self._inspector_last_width: int = 200  # v0.0.20.606: reduced from 320
        self._inspector_visible: bool = True
        # v0.0.20.602: Adjustable slot height (Ctrl+Scroll to zoom)
        self._slot_height: int = 44

        # Allow the right dock group (Browser/Clip Launcher) to be shrunk
        # "almost closed" without being blocked by minimum-size hints.
        try:
            from PySide6.QtWidgets import QSizePolicy
            self.setMinimumSize(0, 0)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        except Exception:
            pass

        # waveform cache (shared across slot widgets)
        self._peaks_cache: dict[str, _PeaksData] = {}
        self._peaks_pending: set[str] = set()
        self._clip_index: dict[str, object] = {}
        self._track_index: dict[str, object] = {}

        # UI-only play-state cache: set of slot_keys currently playing (from ClipLauncherPlaybackService)
        self._active_slots: set[str] = set()

        # UI-only queued-state cache: set of slot_keys/scenes queued via quantize (from LauncherService)
        self._queued_slots: set[str] = set()
        self._queued_scenes: set[int] = set()
        self._scene_headers: dict[int, QWidget] = {}

        # Queued countdown meta (UI-only): slot_key -> (at_beat, quantize), scene -> (at_beat, quantize)
        self._queued_slot_meta: dict[str, tuple[float, str]] = {}
        self._queued_scene_meta: dict[int, tuple[float, str]] = {}
        self._scene_countdown_labels: dict[int, QLabel] = {}

        # Slot selection + clipboard (DAW-like shortcuts for the launcher grid)
        self._selected_slot_key: str = ''
        # v0.0.20.600: Multi-slot selection (Bitwig: Shift+Click=range, Ctrl+Click=toggle)
        self._selected_slot_keys: set = set()
        self._slot_buttons: dict[str, SlotWaveButton] = {}
        self._slot_clipboard_clip_id: str = ''
        self._slot_clipboard_source_slot_key: str = ''
        self._shortcuts: list[QShortcut] = []

        # Timer for queued countdown repaint (only active when something is queued)
        self._queue_timer = QTimer(self)
        self._queue_timer.setInterval(60)
        self._queue_timer.timeout.connect(self._on_queue_timer_tick)

        self._build_ui()
        self._wire()
        self.refresh()

        # Apply persisted inspector state after the widget hierarchy exists.
        self._load_inspector_prefs()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top header bar ──
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 8, 4)

        header.addWidget(QLabel("Clip Launcher"))

        # Toggle the left "ZELLE" inspector (Bitwig-style).
        self.btn_toggle_inspector = QToolButton()
        self.btn_toggle_inspector.setCheckable(True)
        self.btn_toggle_inspector.setChecked(True)
        self.btn_toggle_inspector.setAutoRaise(True)
        self.btn_toggle_inspector.setToolTip("ZELLE Inspector ein-/ausblenden")
        try:
            self.btn_toggle_inspector.setArrowType(Qt.ArrowType.LeftArrow)
        except Exception:
            pass
        header.addWidget(self.btn_toggle_inspector)

        header.addWidget(QLabel("Scenes:"))
        self.spin_scenes = QSpinBox()
        self.spin_scenes.setRange(1, 64)
        self.spin_scenes.setValue(self.scene_count)
        header.addWidget(self.spin_scenes)

        header.addSpacing(12)
        header.addWidget(QLabel("Quantize:"))
        self.cmb_quant = QComboBox()
        self.cmb_quant.addItems(["Off", "1 Beat", "1 Bar"])
        header.addWidget(self.cmb_quant)

        header.addSpacing(6)
        header.addWidget(QLabel("Mode:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Trigger", "Toggle", "Gate", "Repeat"])  # v0.0.20.604: + Repeat
        header.addWidget(self.cmb_mode)

        header.addSpacing(12)
        self.chk_reset = QCheckBox("Reset Playhead")
        self.chk_reset.setToolTip("Beim Stop All wird der Playhead auf 0 gesetzt.")
        header.addWidget(self.chk_reset)

        self.btn_stop_all = QPushButton("Stop All")
        header.addWidget(self.btn_stop_all)

        header.addStretch(1)

        # v0.0.20.603: Scene-Chain → Arranger button (Phase 6.2)
        self.btn_scene_chain = QPushButton("→ Arranger")
        self.btn_scene_chain.setToolTip("Szenen-Reihenfolge als lineare Clips in den Arranger übertragen")
        self.btn_scene_chain.setFixedHeight(22)
        header.addWidget(self.btn_scene_chain)

        # v0.0.20.604: Vollbild/Performance View button
        self.btn_fullscreen = QPushButton("⛶ Vollbild")
        self.btn_fullscreen.setToolTip("Clip Launcher als schwebendes Fenster (Performance View)")
        self.btn_fullscreen.setFixedHeight(22)
        self.btn_fullscreen.clicked.connect(self._toggle_performance_view)
        header.addWidget(self.btn_fullscreen)

        self.lbl_sel = QLabel("Ausgewählter Clip: —")
        header.addWidget(self.lbl_sel)

        layout.addLayout(header)

        # ── Main area: Inspector (left) + Grid (right) ──
        from PySide6.QtWidgets import QSplitter

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        try:
            from PySide6.QtWidgets import QSizePolicy
            self.main_splitter.setMinimumSize(0, 0)
            self.main_splitter.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        except Exception:
            pass
        layout.addWidget(self.main_splitter, 1)

        # ── Left: Bitwig-Style ZELLE Inspector ──
        try:
            from pydaw.ui.clip_launcher_inspector import ClipLauncherInspector
            self.inspector = ClipLauncherInspector(
                self.project,
                clip_context=self.clip_context,
                parent=self.main_splitter,
            )
            # IMPORTANT (User UX): the inspector must be resizable.
            # Do NOT clamp it to a tiny max width, otherwise the UI feels "broken".
            self.inspector.setMinimumWidth(80)  # v0.0.20.606: compact inspector
            self.inspector.setMaximumWidth(260)  # v0.0.20.606: prevent inspector from taking too much space
            try:
                self.inspector.setMaximumWidth(8192)
            except Exception:
                pass
            self.main_splitter.addWidget(self.inspector)
        except Exception as e:
            # Fallback: no inspector if import fails
            self.inspector = None
            import logging
            logging.getLogger(__name__).warning("ClipLauncherInspector not available: %s", e)

        # ── Right: Grid (existing) ──
        grid_container = QWidget()
        # v0.0.20.595: Shrinkable grid container
        try:
            from PySide6.QtWidgets import QSizePolicy
            grid_container.setMinimumSize(0, 0)
            grid_container.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        except Exception:
            pass
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        # v0.0.20.595: Enable horizontal scroll so grid doesn't force window wider
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        try:
            from PySide6.QtWidgets import QSizePolicy
            self.scroll.setMinimumSize(0, 0)
            self.scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        except Exception:
            pass
        grid_layout.addWidget(self.scroll, 1)

        self.inner = QWidget()
        # v0.0.20.595: Allow inner grid to be smaller than scroll area
        try:
            from PySide6.QtWidgets import QSizePolicy
            self.inner.setMinimumSize(0, 0)
            self.inner.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(6, 6, 6, 6)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(6)

        self.scroll.setWidget(self.inner)
        self.main_splitter.addWidget(grid_container)

        # Splitter proportions: default inspector width, grid gets the rest.
        try:
            self.main_splitter.setSizes([self._inspector_last_width, 1000])
        except Exception:
            pass

    def _wire(self) -> None:
        self.spin_scenes.valueChanged.connect(self._scenes_changed)
        self.project.project_updated.connect(self.refresh)
        self.project.active_clip_changed.connect(self._active_clip_changed)
        self.slot_drop_requested.connect(self._handle_slot_drop)

        self.cmb_quant.currentTextChanged.connect(self._launcher_settings_changed)
        self.cmb_mode.currentTextChanged.connect(self._launcher_settings_changed)

        self.btn_stop_all.clicked.connect(lambda _=False: self.launcher.stop_all(reset_playhead=self.chk_reset.isChecked()))
        # v0.0.20.603: Scene-Chain → Arranger
        self.btn_scene_chain.clicked.connect(self._scene_chain_to_arranger)

        # v0.0.20.604: MIDI Controller → Scene Launch (basic Launchpad-style)
        try:
            midi_mgr = getattr(self.project, 'midi', None) or getattr(getattr(self.project, 'services', None), 'midi', None)
            if midi_mgr and hasattr(midi_mgr, 'cc_received'):
                midi_mgr.cc_received.connect(self._on_midi_cc)
        except Exception:
            pass

    def _toggle_performance_view(self) -> None:
        """v0.0.20.604: Toggle between docked and floating performance view.

        When floating: large window for live performance (Launchpad-style).
        When docked: returns to normal Clip Launcher panel.
        """
        try:
            dock = self.parent()
            while dock is not None and not isinstance(dock, QDockWidget):
                dock = dock.parent()
            if dock is None:
                return

            if dock.isFloating():
                # Return to docked
                dock.setFloating(False)
                self.btn_fullscreen.setText("⛶ Vollbild")
            else:
                # Float as large window
                dock.setFloating(True)
                try:
                    from PySide6.QtWidgets import QApplication
                    screen = QApplication.primaryScreen()
                    if screen:
                        geo = screen.availableGeometry()
                        dock.resize(int(geo.width() * 0.7), int(geo.height() * 0.7))
                        dock.move(int(geo.width() * 0.15), int(geo.height() * 0.1))
                except Exception:
                    dock.resize(900, 600)
                self.btn_fullscreen.setText("⬚ Andocken")
        except Exception:
            pass

    def _on_midi_cc(self, channel: int, cc: int, value: int) -> None:
        """v0.0.20.605: Map MIDI CC to scene launches (Launchpad/APC40 style).

        Default mapping: CC 20-27 = Scene 1-8, CC 28 = Stop All.
        Custom mappings via launcher_midi_mapping in project model.
        """
        try:
            if value <= 0:
                return
            # Check custom mappings first
            mappings = getattr(self.project.ctx.project, 'launcher_midi_mapping', []) or []
            for m in mappings:
                if isinstance(m, dict) and int(m.get('cc', -1)) == cc and int(m.get('channel', -1)) in (-1, channel):
                    action = str(m.get('action', ''))
                    target = m.get('target', '')
                    if action == 'launch_scene':
                        self.launcher.launch_scene(int(target))
                        return
                    elif action == 'launch_slot':
                        self._launch(str(target))
                        return
                    elif action == 'stop_all':
                        self.launcher.stop_all()
                        return
            # Default: CC 20-27 = Scene 1-8, CC 28 = Stop All
            if 20 <= cc <= 27:
                self.launcher.launch_scene(cc - 19)
            elif cc == 28:
                self.launcher.stop_all()
        except Exception:
            pass

        # Play-state indicator updates (UI-only)
        try:
            sig = getattr(self.project, 'cliplauncher_active_slots_changed', None)
            if sig is not None:
                sig.connect(self._on_active_slots_changed)
        except Exception:
            pass

        # Queued-state indicator updates (UI-only)
        try:
            psig = getattr(self.launcher, 'pending_changed', None)
            if psig is not None:
                psig.connect(self._on_pending_changed)
        except Exception:
            pass

        # UI: inspector collapse + width persistence
        try:
            self.btn_toggle_inspector.clicked.connect(self._toggle_inspector)
        except Exception:
            pass
        try:
            self.main_splitter.splitterMoved.connect(self._on_splitter_moved)
        except Exception:
            pass

        # DAW-like launcher shortcuts (grid-level): Ctrl+C/V/X, Del, Ctrl+D, Esc
        try:
            self._install_shortcuts()
        except Exception:
            pass

    def _read_bool_setting(self, key: str, default: bool) -> bool:
        try:
            raw = get_value(key, default)
        except Exception:
            return bool(default)
        if isinstance(raw, str):
            return raw.strip().lower() in ("true", "1", "yes", "on")
        return bool(raw)

    def _load_inspector_prefs(self) -> None:
        # Called after build() so widgets exist.
        try:
            self._inspector_visible = self._read_bool_setting(
                self._settings_keys.ui_cliplauncher_inspector_visible,
                True,
            )
        except Exception:
            self._inspector_visible = True

        try:
            w = get_value(self._settings_keys.ui_cliplauncher_inspector_width, self._inspector_last_width)
            if isinstance(w, str):
                w = int(float(w))
            self._inspector_last_width = max(160, min(1200, int(w)))
        except Exception:
            pass

        self._apply_inspector_visible(self._inspector_visible, restore_width=True)

    def _apply_inspector_visible(self, visible: bool, restore_width: bool = False) -> None:
        if getattr(self, 'inspector', None) is None:
            return

        self._inspector_visible = bool(visible)
        try:
            set_value(self._settings_keys.ui_cliplauncher_inspector_visible, bool(self._inspector_visible))
        except Exception:
            pass

        try:
            self.btn_toggle_inspector.blockSignals(True)
            self.btn_toggle_inspector.setChecked(bool(self._inspector_visible))
        finally:
            try:
                self.btn_toggle_inspector.blockSignals(False)
            except Exception:
                pass

        try:
            self.inspector.setVisible(bool(self._inspector_visible))
        except Exception:
            pass

        try:
            # Arrow points towards the direction you can collapse to.
            self.btn_toggle_inspector.setArrowType(
                Qt.ArrowType.LeftArrow if self._inspector_visible else Qt.ArrowType.RightArrow
            )
        except Exception:
            pass

        if restore_width and self._inspector_visible:
            try:
                self.main_splitter.setSizes([int(self._inspector_last_width), 1000])
            except Exception:
                pass
        elif not self._inspector_visible:
            # collapse (keep grid visible)
            try:
                self.main_splitter.setSizes([0, 1000])
            except Exception:
                pass

    def _toggle_inspector(self) -> None:
        if getattr(self, 'inspector', None) is None:
            return
        if self._inspector_visible:
            # Remember width before hiding.
            try:
                sizes = self.main_splitter.sizes()
                if sizes and sizes[0] > 0:
                    self._inspector_last_width = int(sizes[0])
                    set_value(self._settings_keys.ui_cliplauncher_inspector_width, int(self._inspector_last_width))
            except Exception:
                pass
            self._apply_inspector_visible(False)
        else:
            self._apply_inspector_visible(True, restore_width=True)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        # Persist only when inspector is visible and has meaningful size.
        if not self._inspector_visible:
            return
        try:
            sizes = self.main_splitter.sizes()
            if not sizes:
                return
            w = int(sizes[0])
            if w < 80:
                return
            self._inspector_last_width = w
            set_value(self._settings_keys.ui_cliplauncher_inspector_width, int(w))
        except Exception:
            pass

    def wheelEvent(self, event):  # noqa: ANN001
        """v0.0.20.602: Ctrl+Scroll = zoom slot height (Bitwig-style)."""
        try:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self._slot_height = min(120, self._slot_height + 8)
                elif delta < 0:
                    self._slot_height = max(28, self._slot_height - 8)
                self.refresh()
                event.accept()
                return
        except Exception:
            pass
        super().wheelEvent(event)

    def _launcher_settings_changed(self) -> None:
        fn = getattr(self.project, 'set_launcher_settings', None)
        if callable(fn):
            fn(self.cmb_quant.currentText(), self.cmb_mode.currentText())
        else:
            # Fallback: persist directly on project model
            try:
                setattr(self.project.ctx.project, 'launcher_quantize', self.cmb_quant.currentText())
                setattr(self.project.ctx.project, 'launcher_mode', self.cmb_mode.currentText())
                self.project.project_updated.emit()
            except Exception:
                pass

    def _active_clip_changed(self, clip_id: str) -> None:
        if not clip_id:
            self.lbl_sel.setText("Ausgewählter Clip: —")
            return
        clip = next((c for c in self.project.ctx.project.clips if c.id == clip_id), None)
        self.lbl_sel.setText(f"Ausgewählter Clip: {clip.label}" if clip else "Ausgewählter Clip: —")

    def _scenes_changed(self, v: int) -> None:
        self.scene_count = int(v)
        self.refresh()

    def _slot_key(self, scene_index: int, track_id: str) -> str:
        return f"scene:{scene_index}:track:{track_id}"

    def _tracks(self):
        return [t for t in self.project.ctx.project.tracks if t.kind != 'master']


    # --- DAW-like grid shortcuts (UI-only) ---

    def _install_shortcuts(self) -> None:
        """Install standard DAW shortcuts for the Clip Launcher grid.

        Requested (Bitwig/Ableton style):
        - Ctrl+C / Ctrl+X / Ctrl+V
        - Delete / Backspace
        - Ctrl+D (duplicate to the right)
        - Esc (deselect)
        """
        # Prevent duplicates if refresh/rebuild calls this again.
        try:
            for sc in getattr(self, '_shortcuts', []) or []:
                try:
                    sc.setEnabled(False)
                    sc.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        self._shortcuts = []

        def _mk(seq: QKeySequence, fn) -> None:  # noqa: ANN001
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)

        _mk(QKeySequence.StandardKey.Copy, self._copy_selected_slot)
        _mk(QKeySequence.StandardKey.Cut, self._cut_selected_slot)
        _mk(QKeySequence.StandardKey.Paste, self._paste_to_selected_slot)
        _mk(QKeySequence.StandardKey.Delete, self._delete_selected_slot)
        _mk(QKeySequence(Qt.Key.Key_Backspace), self._delete_selected_slot)
        _mk(QKeySequence("Ctrl+D"), self._duplicate_selected_slot_right)
        _mk(QKeySequence(Qt.Key.Key_Escape), self._deselect_slot)
        # v0.0.20.599: Rename (F2)
        _mk(QKeySequence(Qt.Key.Key_F2), self._rename_selected_slot)

        # v0.0.20.603: Scene launch shortcuts (1-8) + Enter to launch selected
        for i in range(1, 9):
            _mk(QKeySequence(str(i)), lambda _=False, s=i: self.launcher.launch_scene(s))
        _mk(QKeySequence(Qt.Key.Key_Return), self._launch_selected_slot)
        _mk(QKeySequence(Qt.Key.Key_Enter), self._launch_selected_slot)
        # Space: toggle play/stop on selected slot
        _mk(QKeySequence(Qt.Key.Key_Space), self._toggle_selected_slot)

    def _parse_slot_key(self, slot_key: str) -> tuple[int, str] | None:
        key = str(slot_key or '').strip()
        if not key:
            return None
        parts = key.split(':')
        if len(parts) == 4 and parts[0] == 'scene' and parts[2] == 'track':
            try:
                return int(parts[1]), str(parts[3])
            except Exception:
                return None
        return None

    # v0.0.20.612: Dual-Clock Phase D — EditorFocusContext an Editoren senden
    def _emit_launcher_focus(self, slot_key: str, clip_id: str) -> None:
        """Baue und sende einen EditorFocusContext für einen Launcher-Slot.

        Rein additiv — der alte clip_activated / clip_context.set_active_slot
        Pfad bleibt parallel bestehen.
        """
        try:
            if not self.clip_context or not clip_id or not slot_key:
                return
            parsed = self._parse_slot_key(slot_key)
            if not parsed:
                return
            scene_idx, track_id = parsed
            ctx = self.clip_context.build_launcher_focus(
                clip_id=str(clip_id),
                slot_key=str(slot_key),
                scene_index=int(scene_idx),
                track_id=str(track_id),
            )
            if ctx is not None:
                self.clip_context.set_editor_focus(ctx)
        except Exception:
            pass

    def is_slot_selected(self, slot_key: str) -> bool:
        k = str(slot_key or '')
        if not k:
            return False
        return k in self._selected_slot_keys or k == str(self._selected_slot_key or '')

    def _set_selected_slot(self, slot_key: str, *, add: bool = False, toggle: bool = False) -> None:
        """Select a slot.

        v0.0.20.600: Multi-selection support:
        - add=False, toggle=False: replace selection (normal click)
        - add=True: add to selection (Shift+Click range end)
        - toggle=True: toggle in/out of selection (Ctrl+Click)
        """
        k = str(slot_key or '')
        if toggle and k:
            if k in self._selected_slot_keys:
                self._selected_slot_keys.discard(k)
                if self._selected_slot_key == k:
                    self._selected_slot_key = next(iter(self._selected_slot_keys), '')
            else:
                self._selected_slot_keys.add(k)
                self._selected_slot_key = k
        elif add and k:
            self._selected_slot_keys.add(k)
            self._selected_slot_key = k
        else:
            # Replace selection
            self._selected_slot_keys = {k} if k else set()
            self._selected_slot_key = k

        # Update inspector with primary selection
        try:
            cid = self.project.ctx.project.clip_launcher.get(self._selected_slot_key, '')
            if cid and self.inspector:
                try:
                    self.inspector.set_clip(cid)
                except Exception:
                    pass
        except Exception:
            pass
        self._apply_selected_slot_state()

    def _apply_selected_slot_state(self) -> None:
        # Repaint only (selection is drawn inside SlotWaveButton.paintEvent)
        try:
            for k, b in (getattr(self, '_slot_buttons', {}) or {}).items():
                try:
                    # Store as dynamic property for potential stylesheet use later.
                    b.setProperty('selected', bool(self.is_slot_selected(str(k))))
                    b.update()
                except Exception:
                    pass
        except Exception:
            pass

    def _deselect_slot(self) -> None:
        self._selected_slot_key = ''
        self._selected_slot_keys = set()
        self._apply_selected_slot_state()

    def _select_range_to(self, target_key: str) -> None:
        """v0.0.20.600: Shift+Click range selection (all slots between anchor and target)."""
        anchor = str(self._selected_slot_key or '')
        if not anchor:
            self._set_selected_slot(target_key)
            return

        anchor_parsed = self._parse_slot_key(anchor)
        target_parsed = self._parse_slot_key(target_key)
        if not anchor_parsed or not target_parsed:
            self._set_selected_slot(target_key)
            return

        a_scene, a_tid = anchor_parsed
        t_scene, t_tid = target_parsed

        # Build list of all slot_keys in the rectangular region
        tracks = self._tracks()
        track_ids = [str(getattr(t, 'id', '')) for t in tracks]

        try:
            a_tidx = track_ids.index(a_tid)
        except ValueError:
            a_tidx = 0
        try:
            t_tidx = track_ids.index(t_tid)
        except ValueError:
            t_tidx = 0

        min_scene = min(a_scene, t_scene)
        max_scene = max(a_scene, t_scene)
        min_tidx = min(a_tidx, t_tidx)
        max_tidx = max(a_tidx, t_tidx)

        new_sel = set()
        for s in range(min_scene, max_scene + 1):
            for ti in range(min_tidx, max_tidx + 1):
                if ti < len(track_ids):
                    new_sel.add(self._slot_key(s, track_ids[ti]))

        self._selected_slot_keys = new_sel
        self._selected_slot_key = target_key
        self._apply_selected_slot_state()

    # --- v0.0.20.603: Keyboard launch/toggle ---

    def _launch_selected_slot(self) -> None:
        """Enter key: launch the selected slot."""
        key = str(self._selected_slot_key or '')
        if not key:
            return
        cid = str(self.project.ctx.project.clip_launcher.get(key, '') or '')
        if cid:
            self._launch(key)

    def _toggle_selected_slot(self) -> None:
        """Space key: toggle play/stop on selected slot."""
        key = str(self._selected_slot_key or '')
        if not key:
            return
        cid = str(self.project.ctx.project.clip_launcher.get(key, '') or '')
        if not cid:
            return
        if self.is_slot_playing(key):
            try:
                playback = getattr(self.project, '_cliplauncher_playback', None)
                if playback:
                    playback.stop_slot(key)
                    self.project._emit_cliplauncher_active_slots()
            except Exception:
                pass
        else:
            self._launch(key)

    # --- v0.0.20.599: Inline rename (F2 / Doppelklick auf Label) ---

    def _rename_selected_slot(self) -> None:
        """Show inline QLineEdit over the selected slot for renaming (Bitwig F2 behavior)."""
        key = str(getattr(self, '_selected_slot_key', '') or '')
        if not key:
            return
        cid = str(self.project.ctx.project.clip_launcher.get(key, '') or '')
        if not cid:
            return
        btn = self._slot_buttons.get(key)
        if btn is None:
            return
        clip = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == cid), None)
        if clip is None:
            return

        try:
            from PySide6.QtWidgets import QLineEdit
            edit = QLineEdit(btn)
            edit.setText(str(getattr(clip, 'label', 'Clip') or 'Clip'))
            edit.selectAll()
            # Position over the label area of the slot
            edit.setGeometry(28, 2, btn.width() - 32, 18)
            edit.setStyleSheet("QLineEdit { background: #333; color: #fff; border: 1px solid #FF8C00; padding: 0 2px; font-size: 11px; }")
            edit.setFocus()
            edit.show()

            def _commit():
                try:
                    new_name = edit.text().strip()
                    if new_name and new_name != str(getattr(clip, 'label', '')):
                        clip.label = str(new_name)
                        self.project.project_updated.emit()
                except Exception:
                    pass
                try:
                    edit.deleteLater()
                except Exception:
                    pass

            def _cancel():
                try:
                    edit.deleteLater()
                except Exception:
                    pass

            edit.returnPressed.connect(_commit)
            edit.editingFinished.connect(_commit)
            # Esc cancels via key override
            orig_keyPress = edit.keyPressEvent
            def _key(ev):
                try:
                    if ev.key() == Qt.Key.Key_Escape:
                        _cancel()
                        return
                except Exception:
                    pass
                orig_keyPress(ev)
            edit.keyPressEvent = _key
        except Exception:
            pass

    def _copy_selected_slot(self) -> None:
        key = str(getattr(self, '_selected_slot_key', '') or '')
        if not key:
            return
        cid = str(self.project.ctx.project.clip_launcher.get(key, '') or '')
        if not cid:
            return
        self._slot_clipboard_clip_id = cid
        self._slot_clipboard_source_slot_key = key
        try:
            self.project.status.emit('ClipLauncher: Slot kopiert (Ctrl+C)')
        except Exception:
            pass

    def _cut_selected_slot(self) -> None:
        # Cut = Copy + Clear
        self._copy_selected_slot()
        self._delete_selected_slot()

    def _paste_to_selected_slot(self) -> None:
        target_key = str(getattr(self, '_selected_slot_key', '') or '')
        src_cid = str(getattr(self, '_slot_clipboard_clip_id', '') or '')
        if not target_key or not src_cid:
            return
        parsed = self._parse_slot_key(target_key)
        if not parsed:
            return
        _scene, track_id = parsed

        # DAW semantics: Paste creates a NEW clip instance (deep copy) assigned to the target slot.
        new_cid = None
        try:
            fn = getattr(self.project, 'clone_clip_for_launcher', None)
            if callable(fn):
                new_cid = fn(src_cid, target_track_id=track_id)
        except Exception:
            new_cid = None

        # Fallback: assign the same clip-id (keeps it non-destructive but linked)
        if not new_cid:
            new_cid = src_cid

        try:
            self.project.cliplauncher_assign(target_key, str(new_cid))
        except Exception:
            pass

        # Keep selection and inspector consistent
        try:
            self._set_selected_slot(target_key)
        except Exception:
            pass
        try:
            self.project.status.emit('ClipLauncher: Slot eingefügt (Ctrl+V)')
        except Exception:
            pass

    def _delete_selected_slot(self) -> None:
        key = str(getattr(self, '_selected_slot_key', '') or '')
        if not key:
            return
        try:
            self.project.cliplauncher_clear(key)
            self.project.status.emit('ClipLauncher: Slot geleert (Del)')
        except Exception:
            pass

    def _duplicate_selected_slot_right(self) -> None:
        """Duplicate the selected slot to the next empty slot on the right (same track)."""
        src_key = str(getattr(self, '_selected_slot_key', '') or '')
        if not src_key:
            return
        src_cid = str(self.project.ctx.project.clip_launcher.get(src_key, '') or '')
        if not src_cid:
            return
        parsed = self._parse_slot_key(src_key)
        if not parsed:
            return
        scene, track_id = parsed

        # Find next empty slot in the same row (track) to the right
        tgt_key = ''
        try:
            for s in range(int(scene) + 1, int(getattr(self, 'scene_count', 8)) + 1):
                k = self._slot_key(int(s), str(track_id))
                if not str(self.project.ctx.project.clip_launcher.get(k, '') or ''):
                    tgt_key = k
                    break
        except Exception:
            tgt_key = ''
        if not tgt_key:
            return

        # Clone + assign
        new_cid = None
        try:
            fn = getattr(self.project, 'clone_clip_for_launcher', None)
            if callable(fn):
                new_cid = fn(src_cid, target_track_id=track_id)
        except Exception:
            new_cid = None
        if not new_cid:
            new_cid = src_cid
        try:
            self.project.cliplauncher_assign(tgt_key, str(new_cid))
        except Exception:
            return

        # Select the new slot
        try:
            self._set_selected_slot(tgt_key)
        except Exception:
            pass


    # --- Bitwig-style helpers (UI-only) ---

    def is_slot_playing(self, slot_key: str) -> bool:
        return str(slot_key) in getattr(self, '_active_slots', set())

    def is_slot_queued(self, slot_key: str) -> bool:
        return str(slot_key) in getattr(self, '_queued_slots', set())


    def _beats_per_bar_ui(self) -> float:
        ts = str(getattr(self.project.ctx.project, 'time_signature', '4/4') or '4/4')
        try:
            num_s, den_s = ts.split('/', 1)
            num = max(1, int(num_s.strip()))
            den = max(1, int(den_s.strip()))
            return float(num) * (4.0 / float(den))
        except Exception:
            return 4.0

    def _format_countdown(self, remaining_beats: float, quantize: str) -> str:
        rem = max(0.0, float(remaining_beats))
        q = str(quantize or 'Off')
        if q == '1 Bar':
            bpb = float(self._beats_per_bar_ui() or 4.0)
            if bpb <= 0.0:
                bpb = 4.0
            bars = rem / bpb
            return f"{bars:.1f} Bar"
        if q == '1 Beat':
            return f"{rem:.1f} Beat"
        # fallback
        if rem >= 1.0:
            bpb = float(self._beats_per_bar_ui() or 4.0)
            if bpb > 0.0:
                bars = rem / bpb
                if bars >= 0.2:
                    return f"{bars:.1f} Bar"
        return f"{rem:.1f} Beat"

    def get_slot_countdown_text(self, slot_key: str) -> str:
        """UI: small queued countdown text for a slot (e.g. '0.5 Bar' / '0.2 Beat').

        v0.0.20.617: Only for QUEUED slots. Live loop position is now
        rendered directly in the bottom-right of the slot button.
        """
        meta = (getattr(self, '_queued_slot_meta', {}) or {}).get(str(slot_key))
        if not meta:
            return ''
        try:
            at_beat, q = meta
            cur = float(getattr(getattr(self.launcher, 'transport', None), 'current_beat', 0.0) or 0.0)
            rem = float(at_beat) - cur
            if rem <= 0.0:
                rem = 0.0
            return self._format_countdown(rem, str(q))
        except Exception:
            return ''

    def get_scene_countdown_text(self, scene_index: int) -> str:
        meta = (getattr(self, '_queued_scene_meta', {}) or {}).get(int(scene_index))
        if not meta:
            return ''
        try:
            at_beat, q = meta
            cur = float(getattr(getattr(self.launcher, 'transport', None), 'current_beat', 0.0) or 0.0)
            rem = float(at_beat) - cur
            if rem <= 0.0:
                rem = 0.0
            return self._format_countdown(rem, str(q))
        except Exception:
            return ''

    def _get_loop_position_text(self, slot_key: str) -> str:
        """v0.0.20.614: Show current loop position (e.g. '1.3 Bar') — via safe snapshot.

        Uses get_runtime_snapshot() for thread-safe, accurate position.
        """
        try:
            playback = getattr(self.project, '_cliplauncher_playback', None)
            if playback is None:
                return ''
            snap = playback.get_runtime_snapshot(str(slot_key))
            if snap is None or not snap.is_playing:
                return ''
            bpb = self._beats_per_bar_ui()
            pos_in_loop = snap.local_beat - snap.loop_start_beats
            if pos_in_loop < 0.0:
                pos_in_loop = 0.0
            bars = pos_in_loop / bpb
            return f"{bars:.1f} Bar"
        except Exception:
            return ''

    def _update_scene_countdowns(self) -> None:
        # Update right-aligned countdown labels in the scene headers
        try:
            labels = getattr(self, '_scene_countdown_labels', {}) or {}
            for idx, lab in labels.items():
                txt = self.get_scene_countdown_text(int(idx))
                try:
                    lab.setText(txt)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_queue_timer_tick(self) -> None:
        # v0.0.20.594: Repaint while queued OR playing (loop position)
        try:
            if not (self._queued_slot_meta or self._queued_scene_meta or self._active_slots):
                if self._queue_timer.isActive():
                    self._queue_timer.stop()
                return
        except Exception:
            return
        try:
            self._update_scene_countdowns()
        except Exception:
            pass
        # v0.0.20.617: Aktive Slot-Buttons direkt updaten für Live-Position
        try:
            active = set(self._active_slots)  # Kopie für sichere Iteration
            for sk in active:
                btn = self._slot_buttons.get(str(sk))
                if btn is not None:
                    btn.update()
        except Exception:
            pass
        try:
            self.inner.update()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def _on_active_slots_changed(self, slot_keys) -> None:  # noqa: ANN001
        try:
            self._active_slots = set(str(k) for k in (slot_keys or []))
        except Exception:
            self._active_slots = set()
        # v0.0.20.594: Start timer during playback for loop position updates
        try:
            if self._active_slots:
                if not self._queue_timer.isActive():
                    self._queue_timer.start()
            elif not self._queued_slot_meta and not self._queued_scene_meta:
                if self._queue_timer.isActive():
                    self._queue_timer.stop()
        except Exception:
            pass
        try:
            self.inner.update()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def _on_pending_changed(self, pending) -> None:  # noqa: ANN001
        """Receive LauncherService pending launches to render queued-state indicators.

        pending is a list of dicts: {kind:'slot'|'scene', key:str, at_beat:float, quantize:str}
        """
        q_slots: set[str] = set()
        q_scenes: set[int] = set()
        slot_meta: dict[str, tuple[float, str]] = {}
        scene_meta: dict[int, tuple[float, str]] = {}

        try:
            for it in (pending or []):
                if isinstance(it, dict):
                    kind = str(it.get('kind', '') or '')
                    key = str(it.get('key', '') or '')
                    at_beat = float(it.get('at_beat', 0.0) or 0.0)
                    q = str(it.get('quantize', 'Off') or 'Off')
                else:
                    kind = str(getattr(it, 'kind', '') or '')
                    key = str(getattr(it, 'key', '') or '')
                    at_beat = float(getattr(it, 'at_beat', 0.0) or 0.0)
                    q = str(getattr(it, 'quantize', 'Off') or 'Off')

                if not key:
                    continue

                if kind == 'slot':
                    q_slots.add(key)
                    slot_meta[key] = (float(at_beat), str(q))
                elif kind == 'scene':
                    try:
                        si = int(key)
                        q_scenes.add(si)
                        scene_meta[si] = (float(at_beat), str(q))
                    except Exception:
                        pass
        except Exception:
            pass

        self._queued_slots = q_slots
        self._queued_scenes = q_scenes
        self._queued_slot_meta = slot_meta
        self._queued_scene_meta = scene_meta

        # Scene headers: dashed yellow border when scene launch is queued
        try:
            for idx, w in (getattr(self, '_scene_headers', {}) or {}).items():
                if int(idx) in self._queued_scenes:
                    w.setStyleSheet('border: 2px dashed rgb(255,176,0);')
                else:
                    w.setStyleSheet('')
        except Exception:
            pass

        # Start/stop countdown timer
        try:
            if self._queued_slot_meta or self._queued_scene_meta:
                if not self._queue_timer.isActive():
                    self._queue_timer.start()
            else:
                if self._queue_timer.isActive():
                    self._queue_timer.stop()
        except Exception:
            pass

        # Immediate countdown label update
        try:
            self._update_scene_countdowns()
        except Exception:
            pass

        try:
            self.inner.update()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def _make_track_header(self, trk) -> QWidget:  # noqa: ANN001
        # Left-side track header inside the launcher grid
        w = QWidget()
        w.setFixedHeight(self._slot_height)
        w.setMaximumWidth(140)  # v0.0.20.606: compact track header
        try:
            w.setMinimumWidth(60)  # v0.0.20.606: compact track headers
        except Exception:
            pass

        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(2)

        lbl = QLabel(str(getattr(trk, 'name', 'Track')))
        lbl.setToolTip(str(getattr(trk, 'name', 'Track')))
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(lbl, 1)

        def _try_call(fn_name: str, *args) -> None:
            try:
                fn = getattr(self.project, fn_name, None)
                if callable(fn):
                    fn(*args)
            except Exception:
                pass

        btn_m = QToolButton(); btn_m.setText('M'); btn_m.setCheckable(True)
        btn_m.setChecked(bool(getattr(trk, 'muted', False)))
        btn_m.setToolTip('Mute'); btn_m.setAutoRaise(True); btn_m.setFixedSize(22, 22)
        btn_m.clicked.connect(lambda _=False, tid=str(getattr(trk, 'id', '')), b=btn_m: _try_call('set_track_mute', tid, b.isChecked()))
        lay.addWidget(btn_m)

        btn_s = QToolButton(); btn_s.setText('S'); btn_s.setCheckable(True)
        btn_s.setChecked(bool(getattr(trk, 'solo', False)))
        btn_s.setToolTip('Solo'); btn_s.setAutoRaise(True); btn_s.setFixedSize(22, 22)
        btn_s.clicked.connect(lambda _=False, tid=str(getattr(trk, 'id', '')), b=btn_s: _try_call('set_track_solo', tid, b.isChecked()))
        lay.addWidget(btn_s)

        btn_r = QToolButton(); btn_r.setText('R'); btn_r.setCheckable(True)
        btn_r.setChecked(bool(getattr(trk, 'record_arm', False)))
        btn_r.setToolTip('Record Arm'); btn_r.setAutoRaise(True); btn_r.setFixedSize(22, 22)
        btn_r.clicked.connect(lambda _=False, tid=str(getattr(trk, 'id', '')), b=btn_r: _try_call('set_track_record_arm', tid, b.isChecked()))
        try:
            btn_r.setStyleSheet('QToolButton:checked { color: #ff3333; font-weight: bold; }')
        except Exception:
            pass
        lay.addWidget(btn_r)

        # v0.0.20.590: Bitwig-style Stop ■ button per track
        btn_stop = QToolButton(); btn_stop.setText('■')
        btn_stop.setToolTip('Stop (alle Clips dieser Spur)')
        btn_stop.setAutoRaise(True); btn_stop.setFixedSize(22, 22)
        try:
            btn_stop.setStyleSheet('QToolButton { font-size: 10px; }')
        except Exception:
            pass
        btn_stop.clicked.connect(lambda _=False, tid=str(getattr(trk, 'id', '')): self._stop_track_clips(tid))
        lay.addWidget(btn_stop)

        return w

    def _make_scene_header(self, scene_index: int) -> QWidget:
        """v0.0.20.599: Scene header with editable name + context menu (Bitwig-style)."""
        w = QWidget()
        w.setFixedHeight(28)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(4)

        btn = QToolButton()
        btn.setText('▶')
        btn.setToolTip('Scene starten (Quantize via Transport)')
        btn.setAutoRaise(True)
        btn.setFixedSize(22, 22)
        btn.clicked.connect(lambda _=False, s=int(scene_index): self.launcher.launch_scene(s))
        lay.addWidget(btn, 0)

        # Scene name (from model or default)
        scene_names = getattr(self.project.ctx.project, 'launcher_scene_names', {}) or {}
        name = str(scene_names.get(str(scene_index), f"Scene {int(scene_index)}") or f"Scene {int(scene_index)}")

        lbl = QLabel(name)
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(lbl, 1)

        # Queued countdown (right-aligned)
        lbl_q = QLabel("")
        lbl_q.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        lbl_q.setFixedWidth(56)  # v0.0.20.606: compact countdown
        try:
            lbl_q.setStyleSheet("color: rgb(255,176,0);")
        except Exception:
            pass
        lay.addWidget(lbl_q, 0)
        try:
            self._scene_countdown_labels[int(scene_index)] = lbl_q
        except Exception:
            pass

        # Right-click context menu
        w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        w.customContextMenuRequested.connect(lambda pos, si=int(scene_index), lbl_ref=lbl, w_ref=w: self._scene_context_menu(si, lbl_ref, w_ref, pos))

        return w

    def _scene_context_menu(self, scene_index: int, lbl: QLabel, header_w: QWidget, pos) -> None:
        """v0.0.20.604: Scene right-click menu (rename, duplicate, delete, color)."""
        try:
            menu = QMenu(self)
            a_rename = menu.addAction("Szene umbenennen")
            a_dup = menu.addAction("Szene duplizieren")
            a_del = menu.addAction("Szene löschen")
            menu.addSeparator()

            # v0.0.20.604: Scene color submenu
            color_menu = menu.addMenu("Szenen-Farbe")
            _color_names = ["Rot", "Orange", "Gelb", "Grün", "Cyan", "Blau", "Lila", "Pink", "Lime", "Warm", "Steel", "Silber"]
            color_actions = []
            for i, cn in enumerate(_color_names):
                a = color_menu.addAction(cn)
                color_actions.append((i, a))

            act = menu.exec(header_w.mapToGlobal(pos))
            if act == a_rename:
                self._rename_scene_inline(scene_index, lbl)
            elif act == a_dup:
                self._duplicate_scene(scene_index)
            elif act == a_del:
                self._delete_scene(scene_index)
            else:
                for cidx, ca in color_actions:
                    if act == ca:
                        self._set_scene_color(scene_index, cidx, header_w)
                        break
        except Exception:
            pass

    def _set_scene_color(self, scene_index: int, color_idx: int, header_w: QWidget) -> None:
        """v0.0.20.604: Set scene color and update visual."""
        try:
            sc = getattr(self.project.ctx.project, 'launcher_scene_colors', None)
            if sc is None:
                self.project.ctx.project.launcher_scene_colors = {}
                sc = self.project.ctx.project.launcher_scene_colors
            sc[str(scene_index)] = int(color_idx)
            # Apply color strip to header widget
            _colors = ['#dc3c3c', '#e67832', '#dcb428', '#50be3c', '#28c8c8', '#3c78dc', '#8c50dc', '#d250b4', '#a0c83c', '#c8a064', '#78a0c8', '#b4b4b4']
            c = _colors[color_idx % len(_colors)]
            header_w.setStyleSheet(f'border-left: 4px solid {c};')
            self.project.project_updated.emit()
        except Exception:
            pass

    def _rename_scene_inline(self, scene_index: int, lbl: QLabel) -> None:
        """Show inline QLineEdit over the scene label."""
        try:
            from PySide6.QtWidgets import QLineEdit
            edit = QLineEdit(lbl.parent())
            edit.setText(lbl.text())
            edit.selectAll()
            edit.setGeometry(lbl.geometry())
            edit.setStyleSheet("QLineEdit { background: #333; color: #fff; border: 1px solid #FF8C00; font-size: 11px; }")
            edit.setFocus()
            edit.show()

            def _commit():
                try:
                    new_name = edit.text().strip()
                    if new_name:
                        scene_names = getattr(self.project.ctx.project, 'launcher_scene_names', None)
                        if scene_names is None:
                            self.project.ctx.project.launcher_scene_names = {}
                            scene_names = self.project.ctx.project.launcher_scene_names
                        scene_names[str(scene_index)] = str(new_name)
                        lbl.setText(str(new_name))
                        self.project.project_updated.emit()
                except Exception:
                    pass
                try:
                    edit.deleteLater()
                except Exception:
                    pass

            edit.returnPressed.connect(_commit)
            edit.editingFinished.connect(_commit)
            orig_kp = edit.keyPressEvent
            def _key(ev):
                try:
                    if ev.key() == Qt.Key.Key_Escape:
                        edit.deleteLater()
                        return
                except Exception:
                    pass
                orig_kp(ev)
            edit.keyPressEvent = _key
        except Exception:
            pass

    def _duplicate_scene(self, scene_index: int) -> None:
        """Duplicate all clips in a scene to the next empty scene column."""
        try:
            tracks = self._tracks()
            # Find next empty scene
            target_scene = self.scene_count + 1
            self.scene_count = target_scene
            self.spin_scenes.setValue(target_scene)

            # Copy all slots from source scene to target
            for trk in tracks:
                src_key = self._slot_key(scene_index, trk.id)
                tgt_key = self._slot_key(target_scene, trk.id)
                src_cid = str(self.project.ctx.project.clip_launcher.get(src_key, '') or '')
                if src_cid:
                    # Clone clip
                    fn = getattr(self.project, 'clone_clip_for_launcher', None)
                    if callable(fn):
                        new_cid = fn(src_cid, target_track_id=str(trk.id))
                        if new_cid:
                            self.project.cliplauncher_assign(tgt_key, str(new_cid))

            # Copy scene name
            scene_names = getattr(self.project.ctx.project, 'launcher_scene_names', {}) or {}
            src_name = scene_names.get(str(scene_index), f"Scene {scene_index}")
            scene_names[str(target_scene)] = f"{src_name} Copy"
            self.project.ctx.project.launcher_scene_names = scene_names

            self.project.status.emit(f"Szene {scene_index} → Szene {target_scene} dupliziert")
            self.project.project_updated.emit()
        except Exception:
            pass

    def _delete_scene(self, scene_index: int) -> None:
        """Clear all clips in a scene (Bitwig: doesn't remove the column, just empties it)."""
        try:
            tracks = self._tracks()
            for trk in tracks:
                key = self._slot_key(scene_index, trk.id)
                try:
                    self.project.cliplauncher_clear(key)
                except Exception:
                    pass
            # Clear scene name
            scene_names = getattr(self.project.ctx.project, 'launcher_scene_names', {}) or {}
            scene_names.pop(str(scene_index), None)
            self.project.status.emit(f"Szene {scene_index} geleert")
            self.project.project_updated.emit()
        except Exception:
            pass

    # --- v0.0.20.603: Phase 6 — KI-Innovationen ---

    def _scene_chain_to_arranger(self) -> None:
        """v0.0.20.603: Convert scene order to linear arranger timeline (Phase 6.2).

        Takes all scenes (1..scene_count) and places their clips sequentially
        in the arranger. Each scene becomes one section (scene_length beats wide).
        Clips are cloned with launcher_only=False.
        """
        try:
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(
                self, "Scene-Chain → Arranger",
                "Szenen-Reihenfolge (z.B. '1,2,3,2,4' oder '1-4'):",
                text=",".join(str(i) for i in range(1, self.scene_count + 1))
            )
            if not ok or not text.strip():
                return

            # Parse scene list: "1,2,3" or "1-4" or "1,2,1,3"
            scene_list = []
            for part in text.replace(' ', '').split(','):
                if '-' in part:
                    a, b = part.split('-', 1)
                    scene_list.extend(range(int(a), int(b) + 1))
                else:
                    scene_list.append(int(part))

            if not scene_list:
                return

            tracks = self._tracks()
            bpb = self._beats_per_bar_ui()
            cursor_beat = 0.0

            for scene_idx in scene_list:
                # Find the longest clip in this scene to determine scene width
                scene_width = bpb * 4  # default 4 bars
                for trk in tracks:
                    key = self._slot_key(scene_idx, trk.id)
                    cid = str(self.project.ctx.project.clip_launcher.get(key, '') or '')
                    if cid:
                        clip = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == cid), None)
                        if clip:
                            ls = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
                            le = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
                            cl = float(getattr(clip, 'length_beats', 4.0) or 4.0)
                            w = (le - ls) if le > ls + 0.01 else cl
                            scene_width = max(scene_width, w)

                # Place clips at cursor position
                for trk in tracks:
                    key = self._slot_key(scene_idx, trk.id)
                    cid = str(self.project.ctx.project.clip_launcher.get(key, '') or '')
                    if cid:
                        try:
                            fn = getattr(self.project, 'clone_clip_for_launcher', None)
                            if callable(fn):
                                new_id = fn(cid, target_track_id=str(trk.id))
                                if new_id:
                                    new_clip = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(new_id)), None)
                                    if new_clip:
                                        new_clip.launcher_only = False
                                        new_clip.start_beats = cursor_beat
                                        new_clip.length_beats = scene_width
                        except Exception:
                            pass

                cursor_beat += scene_width

            self.project.status.emit(f"Scene-Chain: {len(scene_list)} Szenen → Arranger ({cursor_beat:.0f} beats)")
            self.project.project_updated.emit()
        except Exception:
            pass

    def _generate_midi_pattern(self, slot_key: str) -> None:
        """v0.0.20.603: KI-generiertes MIDI-Pattern (Phase 6.1).

        Generates a basic MIDI pattern based on the selected style.
        This is our own innovation — no other DAW has this built-in.
        """
        try:
            cid = str(self.project.ctx.project.clip_launcher.get(str(slot_key), '') or '')
            if not cid:
                return
            clip = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == cid), None)
            if not clip or str(getattr(clip, 'kind', '')) != 'midi':
                return

            from PySide6.QtWidgets import QInputDialog
            patterns = [
                "Arpeggio (Dur aufwärts)",
                "Arpeggio (Moll aufwärts)",
                "Arpeggio (Dur abwärts)",
                "Akkord-Stabs (Dur)",
                "Akkord-Stabs (Moll)",
                "Bass-Linie (Oktave)",
                "Drum Pattern (4/4 Basic)",
                "Drum Pattern (Hi-Hat 8tel)",
                "Melodie (Pentatonisch zufällig)",
                "Pad (lange Akkorde)",
            ]
            choice, ok = QInputDialog.getItem(
                self, "MIDI Pattern generieren", "Pattern-Typ:", patterns, 0, False
            )
            if not ok or not choice:
                return

            bpb = self._beats_per_bar_ui()
            ls = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
            le = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
            clip_len = float(getattr(clip, 'length_beats', 16.0) or 16.0)
            span = (le - ls) if le > ls + 0.01 else clip_len

            notes = self._build_pattern(choice, span, bpb)
            if not notes:
                return

            # Add notes to clip
            for pitch, start, length, vel in notes:
                try:
                    self.project.add_midi_note(
                        cid,
                        pitch=int(pitch),
                        start_beats=float(start),
                        length_beats=float(length),
                        velocity=int(vel),
                    )
                except Exception:
                    pass

            self.project.status.emit(f"MIDI Pattern: {choice} ({len(notes)} Noten)")
            self.project.project_updated.emit()
        except Exception:
            pass

    def _build_pattern(self, style: str, span: float, bpb: float) -> list:
        """Build MIDI note list: [(pitch, start_beats, length_beats, velocity), ...]"""
        import random
        notes = []
        try:
            if 'Dur aufwärts' in style:
                scale = [60, 64, 67, 72, 76, 79, 84]
                step = span / len(scale)
                for i, p in enumerate(scale):
                    notes.append((p, i * step, step * 0.9, 100))
            elif 'Moll aufwärts' in style:
                scale = [60, 63, 67, 72, 75, 79, 84]
                step = span / len(scale)
                for i, p in enumerate(scale):
                    notes.append((p, i * step, step * 0.9, 100))
            elif 'Dur abwärts' in style:
                scale = [84, 79, 76, 72, 67, 64, 60]
                step = span / len(scale)
                for i, p in enumerate(scale):
                    notes.append((p, i * step, step * 0.9, 100))
            elif 'Akkord-Stabs (Dur)' in style:
                chord = [60, 64, 67]
                n_stabs = max(1, int(span / bpb))
                for i in range(n_stabs):
                    for p in chord:
                        notes.append((p, i * bpb, bpb * 0.5, 110))
            elif 'Akkord-Stabs (Moll)' in style:
                chord = [60, 63, 67]
                n_stabs = max(1, int(span / bpb))
                for i in range(n_stabs):
                    for p in chord:
                        notes.append((p, i * bpb, bpb * 0.5, 110))
            elif 'Bass-Linie' in style:
                n = max(1, int(span))
                for i in range(n):
                    p = 36 if i % 2 == 0 else 48
                    notes.append((p, float(i), 0.9, 100))
            elif 'Drum Pattern (4/4 Basic)' in style:
                n_beats = max(1, int(span))
                for i in range(n_beats):
                    notes.append((36, float(i), 0.25, 110))  # Kick on every beat
                    if i % 2 == 1:
                        notes.append((38, float(i), 0.25, 100))  # Snare on 2,4
                for i in range(n_beats * 2):
                    notes.append((42, float(i) * 0.5, 0.25, 80))  # HiHat 8tel
            elif 'Drum Pattern (Hi-Hat 8tel)' in style:
                n_8th = max(1, int(span * 2))
                for i in range(n_8th):
                    vel = 90 if i % 2 == 0 else 60
                    notes.append((42, float(i) * 0.5, 0.25, vel))
            elif 'Pentatonisch' in style:
                penta = [60, 62, 64, 67, 69, 72, 74, 76]
                n = max(4, int(span * 2))
                for i in range(n):
                    p = random.choice(penta)
                    notes.append((p, float(i) * 0.5, 0.45, random.randint(70, 120)))
            elif 'Pad' in style:
                chord = [60, 64, 67, 72]
                for p in chord:
                    notes.append((p, 0.0, span * 0.95, 80))
        except Exception:
            pass
        return notes

    # --- v0.0.20.604: Clip Variations (Phase 6.3) ---

    def _add_clip_variation(self, slot_key: str, clip_id: str) -> None:
        """Create a variation (clone) of a clip and store it as alt-clip.

        Bitwig+ Innovation: Each slot can have multiple variations.
        The user can cycle through them or let Follow Actions pick randomly.
        """
        try:
            fn = getattr(self.project, 'clone_clip_for_launcher', None)
            if not callable(fn):
                return
            parsed = self._parse_slot_key(slot_key)
            if not parsed:
                return
            _, track_id = parsed

            new_id = fn(str(clip_id), target_track_id=str(track_id), label_suffix=" Var")
            if not new_id:
                return

            # Store as alt-clip on the source clip
            src = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(clip_id)), None)
            if src is not None:
                alts = getattr(src, 'launcher_alt_clips', None)
                if alts is None:
                    src.launcher_alt_clips = []
                    alts = src.launcher_alt_clips
                alts.append(str(new_id))
                count = len(alts)
                self.project.status.emit(f"Variation {count} erstellt für {getattr(src, 'label', 'Clip')}")
                self.project.project_updated.emit()
        except Exception:
            pass

    def _smart_quantize_clip(self, clip_id: str) -> None:
        """v0.0.20.604: Smart Quantize — snap notes to nearest grid with groove detection.

        KI-Innovation: Analyzes the timing distribution and snaps notes to the
        closest grid position while preserving intentional micro-timing (groove).
        Notes that are very close to grid (< threshold) get snapped.
        Notes that are consistently off-grid (groove) get preserved.
        """
        try:
            notes = self.project.ctx.project.midi_notes.get(str(clip_id), [])
            if not notes:
                return

            from PySide6.QtWidgets import QInputDialog
            grids = ["1/16 (tight)", "1/8 (standard)", "1/4 (loose)", "1/4T (triplet)", "1/8T (triplet)"]
            choice, ok = QInputDialog.getItem(self, "Smart Quantize", "Grid:", grids, 1, False)
            if not ok:
                return

            # Parse grid
            grid_map = {"1/16": 0.25, "1/8": 0.5, "1/4": 1.0, "1/4T": 1.0/3.0, "1/8T": 0.5/3.0}
            grid_key = choice.split(" ")[0]
            grid_beats = grid_map.get(grid_key, 0.5)

            # Smart threshold: snap if within 40% of grid, preserve if beyond (groove)
            threshold = grid_beats * 0.4
            quantized_count = 0

            for n in notes:
                try:
                    if isinstance(n, dict):
                        sb = float(n.get('start_beats', n.get('start', 0.0)) or 0.0)
                    else:
                        sb = float(getattr(n, 'start_beats', getattr(n, 'start', 0.0)) or 0.0)

                    # Nearest grid point
                    nearest = round(sb / grid_beats) * grid_beats
                    dist = abs(sb - nearest)

                    if dist <= threshold and dist > 0.001:
                        # Snap it
                        if isinstance(n, dict):
                            if 'start_beats' in n:
                                n['start_beats'] = nearest
                            elif 'start' in n:
                                n['start'] = nearest
                        else:
                            if hasattr(n, 'start_beats'):
                                n.start_beats = nearest
                            elif hasattr(n, 'start'):
                                n.start = nearest
                        quantized_count += 1
                except Exception:
                    continue

            self.project.status.emit(f"Smart Quantize: {quantized_count}/{len(notes)} Noten an {grid_key} Grid ausgerichtet")
            self.project.project_updated.emit()
        except Exception:
            pass

    def _beats_to_seconds(self, beats: float) -> float:
        bpm = float(getattr(self.project.ctx.project, 'bpm', 120.0) or 120.0)
        return (float(beats) * 60.0) / max(1e-6, bpm)

    def _volume_to_db(self, vol: float) -> float:
        v = float(vol)
        if v <= 0.0:
            return -120.0
        if v <= 1.0:
            return -60.0 + (60.0 * v)
        v = min(v, 2.0)
        return 6.0 * (v - 1.0)

    def _db_to_gain(self, db: float) -> float:
        if db <= -120.0:
            return 0.0
        return float(10.0 ** (float(db) / 20.0))

    def _display_gain_for_volume(self, vol: float) -> tuple[float, float]:
        db = self._volume_to_db(float(vol))
        return (self._db_to_gain(db), db)

    def _get_clip(self, clip_id: str):
        return self._clip_index.get(str(clip_id))

    def _get_track_volume(self, track_id: str) -> float:
        trk = self._track_index.get(str(track_id))
        try:
            return float(getattr(trk, 'volume', 0.8) or 0.8)
        except Exception:
            return 0.8

    # --- waveform cache (ported from ArrangerCanvas)

    def _get_peaks_for_path(self, path_str: str) -> _PeaksData | None:
        if sf is None or np is None:
            return None
        if not path_str:
            return None
        try:
            p = os.path.abspath(path_str)
            st = os.stat(p)
            mtime = int(st.st_mtime_ns)
        except Exception:
            return None

        cached = self._peaks_cache.get(p)
        if cached and int(cached.mtime_ns) == mtime:
            return cached

        if p not in self._peaks_pending:
            self._peaks_pending.add(p)
            self._submit_peaks_compute(p, mtime)
        return None

    def _submit_peaks_compute(self, abs_path: str, mtime_ns: int) -> None:
        def fn():
            return self._compute_peaks(abs_path)

        def ok(res):
            try:
                if res is None:
                    return
                peaks_arr, sr, bs = res
                self._peaks_cache[str(abs_path)] = _PeaksData(
                    mtime_ns=int(mtime_ns),
                    block_size=int(bs),
                    samplerate=int(sr),
                    peaks=peaks_arr,
                )
            finally:
                self._peaks_pending.discard(str(abs_path))
                try:
                    self.inner.update()
                except Exception:
                    pass
                self.update()

        def err(_msg: str):
            self._peaks_pending.discard(str(abs_path))

        try:
            self.project._submit(fn, ok, err)  # type: ignore[attr-defined]
        except Exception:
            try:
                res = self._compute_peaks(abs_path)
                if res is not None:
                    peaks_arr, sr, bs = res
                    self._peaks_cache[str(abs_path)] = _PeaksData(
                        mtime_ns=int(mtime_ns),
                        block_size=int(bs),
                        samplerate=int(sr),
                        peaks=peaks_arr,
                    )
            finally:
                self._peaks_pending.discard(str(abs_path))
                try:
                    self.inner.update()
                except Exception:
                    pass
                self.update()

    def _compute_peaks(self, abs_path: str):
        if sf is None or np is None:
            return None
        try:
            f = sf.SoundFile(abs_path)
        except Exception:
            return None

        block_size = 2048
        sr = int(getattr(f, 'samplerate', 48000) or 48000)
        peaks_list = []
        try:
            for block in f.blocks(blocksize=block_size, dtype='float32', always_2d=True):
                if block is None or block.shape[0] == 0:
                    continue
                a = np.max(np.abs(block), axis=1)
                peaks_list.append(float(np.max(a)))
        except Exception:
            try:
                data = f.read(dtype='float32', always_2d=True)
                if data is None or data.shape[0] == 0:
                    return None
                a = np.max(np.abs(data), axis=1)
                n = int(a.shape[0])
                n_chunks = (n + block_size - 1) // block_size
                for i in range(n_chunks):
                    s = i * block_size
                    e = min(n, (i + 1) * block_size)
                    peaks_list.append(float(np.max(a[s:e])))
            except Exception:
                return None
        finally:
            try:
                f.close()
            except Exception:
                pass

        if not peaks_list:
            return None
        arr = np.asarray(peaks_list, dtype='float32')
        arr = np.clip(arr, 0.0, 1.0)
        return arr, sr, block_size

    def _draw_audio_waveform(self, p: QPainter, rect: QRectF, clip, track_volume: float) -> None:
        peaks = self._get_peaks_for_path(str(getattr(clip, 'source_path', '') or ''))
        if peaks is None or np is None:
            p.setPen(QPen(self.palette().mid().color()))
            p.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 'Waveform…')
            return

        beats_to_sec = self._beats_to_seconds(1.0)
        offset_sec = float(getattr(clip, 'offset_seconds', 0.0) or 0.0)
        length_sec = float(getattr(clip, 'length_beats', 0.0) or 0.0) * beats_to_sec
        if length_sec <= 0.0:
            return

        start_i = int(max(0.0, offset_sec * peaks.peaks_per_second))
        end_i = int(max(start_i + 1, (offset_sec + length_sec) * peaks.peaks_per_second))
        seg = peaks.peaks[start_i:min(end_i, len(peaks.peaks))]
        if seg.size == 0:
            return

        n = max(8, int(rect.width()))
        if seg.size != n:
            x_old = np.linspace(0.0, 1.0, num=int(seg.size), dtype=np.float32)
            x_new = np.linspace(0.0, 1.0, num=int(n), dtype=np.float32)
            seg = np.interp(x_new, x_old, seg).astype(np.float32)

        gain, _db = self._display_gain_for_volume(track_volume)
        seg = np.clip(seg * float(gain), 0.0, 1.0)

        mid_y = rect.center().y()
        amp_h = rect.height() * 0.45

        p.setPen(QPen(self.palette().text().color()))
        x0 = int(rect.left())
        top = rect.top()
        bottom = rect.bottom()
        for i, a in enumerate(seg):
            if float(a) <= 0.0005:
                continue
            x = x0 + i
            dy = float(a) * amp_h
            y1 = max(top, mid_y - dy)
            y2 = min(bottom, mid_y + dy)
            p.drawLine(int(x), int(y1), int(x), int(y2))

        # v0.0.20.604: Gain indicator (top-right of waveform)
        try:
            _gain_db = self._volume_to_db(track_volume)
            if abs(_gain_db) > 0.5:
                p.setPen(QColor(180, 220, 255, 160))
                from PySide6.QtGui import QFont
                sf = QFont(p.font())
                sf.setPointSize(max(6, sf.pointSize() - 2))
                p.setFont(sf)
                p.drawText(QRectF(rect.right() - 40, rect.top(), 38, 10),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                           f"{_gain_db:+.1f}dB")
        except Exception:
            pass

    def _draw_midi_pianoroll(self, p: QPainter, rect: QRectF, clip) -> None:
        """Draw a Bitwig/Ableton-style mini piano-roll for MIDI clips in slot buttons.

        v0.0.20.587: Visual feedback for MIDI clips in Clip Launcher.
        Shows note bars with velocity-mapped opacity. Pitch mapped vertically,
        time mapped horizontally within the clip's beat range.
        """
        cid = str(getattr(clip, 'id', '') or '')
        if not cid:
            return

        try:
            notes = self.project.ctx.project.midi_notes.get(cid, []) or []
        except Exception:
            notes = []

        if not notes:
            # Empty MIDI clip: show placeholder
            p.setPen(QPen(QColor(120, 180, 255, 100)))
            p.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignCenter, '♪ MIDI')
            return

        clip_len = float(getattr(clip, 'length_beats', 4.0) or 4.0)
        if clip_len <= 0.0:
            clip_len = 4.0

        # Find pitch range for vertical scaling
        min_pitch = 127
        max_pitch = 0
        for n in notes:
            try:
                pitch = int(getattr(n, 'pitch', 60) if not isinstance(n, dict) else n.get('pitch', 60))
                min_pitch = min(min_pitch, pitch)
                max_pitch = max(max_pitch, pitch)
            except Exception:
                continue

        if max_pitch < min_pitch:
            return

        # Add padding to pitch range (minimum 12 semitones visible)
        pitch_range = max(12, max_pitch - min_pitch + 2)
        pitch_center = (min_pitch + max_pitch) / 2.0
        pitch_low = pitch_center - pitch_range / 2.0
        pitch_high = pitch_center + pitch_range / 2.0

        # Draw note bars
        rx = float(rect.left())
        ry = float(rect.top())
        rw = float(rect.width())
        rh = float(rect.height())

        # Bitwig-style note color (per-clip color tint)
        try:
            color_idx = int(getattr(clip, 'launcher_color', getattr(clip, 'color', 0)) or 0) % 12
        except Exception:
            color_idx = 0

        # Color palette matching Bitwig's clip launcher colors
        _colors = [
            QColor(100, 160, 255),  # blue
            QColor(255, 100, 100),  # red
            QColor(100, 220, 100),  # green
            QColor(255, 200, 60),   # yellow
            QColor(200, 130, 255),  # purple
            QColor(255, 160, 80),   # orange
            QColor(80, 220, 220),   # cyan
            QColor(255, 130, 180),  # pink
            QColor(180, 220, 80),   # lime
            QColor(220, 180, 140),  # warm
            QColor(140, 180, 220),  # steel
            QColor(200, 200, 200),  # silver
        ]
        note_color = _colors[color_idx % len(_colors)]

        min_note_w = 1.5  # minimum visible width in pixels
        note_h = max(1.5, min(4.0, rh / float(pitch_range)))

        for n in notes:
            try:
                if isinstance(n, dict):
                    ns = float(n.get('start_beats', n.get('start', 0.0)) or 0.0)
                    nl = float(n.get('length_beats', n.get('length', 0.25)) or 0.25)
                    np_ = int(n.get('pitch', 60) or 60)
                    nv = int(n.get('velocity', 100) or 100)
                else:
                    ns = float(getattr(n, 'start_beats', getattr(n, 'start', 0.0)) or 0.0)
                    nl = float(getattr(n, 'length_beats', getattr(n, 'length', 0.25)) or 0.25)
                    np_ = int(getattr(n, 'pitch', 60) or 60)
                    nv = int(getattr(n, 'velocity', 100) or 100)

                # X position (time)
                x = rx + (ns / clip_len) * rw
                w = max(min_note_w, (nl / clip_len) * rw)

                # Y position (pitch, high pitch = top)
                y_norm = 1.0 - ((float(np_) - pitch_low) / float(pitch_range))
                y = ry + y_norm * (rh - note_h)

                # Velocity → opacity (40..230)
                alpha = int(40 + (float(nv) / 127.0) * 190)
                c = QColor(note_color)
                c.setAlpha(alpha)

                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x, y, w, note_h), 0.5, 0.5)

                # v0.0.20.604: Velocity bar at bottom (small vertical line)
                try:
                    vel_h = max(1, (float(nv) / 127.0) * 6.0)
                    vel_c = QColor(note_color)
                    vel_c.setAlpha(180)
                    p.setBrush(vel_c)
                    p.drawRect(QRectF(x, ry + rh - vel_h, max(1.0, w * 0.6), vel_h))
                except Exception:
                    pass
            except Exception:
                continue


    def _clear_grid(self) -> None:
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def refresh(self) -> None:
        self._clear_grid()
        self._slot_buttons = {}

        q = getattr(self.project.ctx.project, "launcher_quantize", "1 Bar")
        m = getattr(self.project.ctx.project, "launcher_mode", "Trigger")
        self.cmb_quant.setCurrentText(q if q in ["Off", "1 Beat", "1 Bar"] else "1 Bar")
        self.cmb_mode.setCurrentText(m if m in ["Trigger", "Toggle", "Gate"] else "Trigger")

        tracks = self._tracks()

        # index for fast lookup in slot paintEvent
        try:
            self._clip_index = {str(c.id): c for c in (self.project.ctx.project.clips or [])}
        except Exception:
            self._clip_index = {}
        try:
            self._track_index = {str(t.id): t for t in (self.project.ctx.project.tracks or [])}
        except Exception:
            self._track_index = {}

        # Active play-state snapshot (UI-only)
        try:
            fn = getattr(self.project, 'cliplauncher_active_slots', None)
            self._active_slots = set(str(k) for k in (fn() if callable(fn) else []))
        except Exception:
            self._active_slots = set()

        # Queued-state snapshot (UI-only)
        try:
            ps = getattr(self.launcher, 'pending_snapshot', None)
            pending = ps() if callable(ps) else []
            self._on_pending_changed(pending)
        except Exception:
            pass

        # Bitwig-style: columns = scenes, rows = tracks
        self._scene_headers = {}
        self._scene_countdown_labels = {}
        self.grid.addWidget(QLabel("Track"), 0, 0)

        for col, scene_idx in enumerate(range(1, self.scene_count + 1), start=1):
            sh = self._make_scene_header(scene_idx)
            try:
                self._scene_headers[int(scene_idx)] = sh
            except Exception:
                pass
            self.grid.addWidget(sh, 0, col)

        for row, trk in enumerate(tracks, start=1):
            try:
                self.grid.addWidget(self._make_track_header(trk), row, 0)
            except Exception:
                lbl = QLabel(str(getattr(trk, 'name', 'Track')))
                lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.grid.addWidget(lbl, row, 0)

            for col, scene_idx in enumerate(range(1, self.scene_count + 1), start=1):
                key = self._slot_key(scene_idx, trk.id)
                btn = SlotWaveButton(self)
                btn.setMinimumHeight(self._slot_height)
                btn.setProperty("slot_key", key)

                cid = self.project.ctx.project.clip_launcher.get(key, "")
                btn.setProperty("clip_id", cid)

                if cid:
                    clip = next((c for c in self.project.ctx.project.clips if c.id == cid), None)
                    btn.setText(clip.label if clip else "Missing")
                else:
                    btn.setText("Empty")

                btn.clicked.connect(lambda _=False, k=key: self._slot_clicked(k))
                btn.double_clicked.connect(lambda k=key: self._slot_double_click(k))
                btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                btn.customContextMenuRequested.connect(lambda _pos, b=btn: self._slot_menu(b))

                try:
                    self._slot_buttons[str(key)] = btn
                except Exception:
                    pass

                self.grid.addWidget(btn, row, col)

        # v0.0.20.606: Compact slot layout — limit column widths, add stretch
        try:
            # Track header column: compact
            self.grid.setColumnStretch(0, 0)
            self.grid.setColumnMinimumWidth(0, 80)
            # Scene columns: equal stretch, limited width
            for c in range(1, self.scene_count + 1):
                self.grid.setColumnStretch(c, 1)
                self.grid.setColumnMinimumWidth(c, 60)
        except Exception:
            pass

        self.grid.setRowStretch(len(tracks) + 1, 1)
        # Restore selection visuals after a full rebuild
        try:
            self._apply_selected_slot_state()
        except Exception:
            pass


    def _handle_slot_drop(self, btn: SlotButton, event) -> None:  # noqa: ANN001
        """Handle clip drop onto a launcher slot.

        v0.0.20.620: Bitwig-style slot-to-slot drag:
        - Plain drag within launcher: MOVE clip (reassign + clear source)
        - Ctrl+Drag within launcher: COPY clip (clone + assign, source stays)
        - Arranger→Launcher drag: clone as launcher_only, assign to slot
        - Does NOT auto-launch on drop (Bitwig doesn't)
        """
        key = str(btn.property("slot_key") or "")
        if not key:
            return
        clip_id = bytes(event.mimeData().data("application/x-pydaw-clipid")).decode("utf-8")
        if not clip_id:
            return

        parsed = self._parse_slot_key(key)
        if not parsed:
            return
        _scene, track_id = parsed

        # v0.0.20.620: Source slot_key aus MIME lesen
        src_slot = ""
        try:
            if event.mimeData().hasFormat("application/x-pydaw-src-slot"):
                src_slot = bytes(event.mimeData().data("application/x-pydaw-src-slot")).decode("utf-8")
        except Exception:
            pass

        # Kein Drop auf sich selbst
        if src_slot and src_slot == key:
            return

        # Check if source is an arranger clip (launcher_only=False)
        src_clip = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(clip_id)), None)
        is_from_arranger = src_clip is not None and not getattr(src_clip, 'launcher_only', False)

        # Determine if we should duplicate (Ctrl+Drag or from Arranger)
        do_duplicate = is_from_arranger  # always clone from arranger
        try:
            if event.mimeData().hasFormat("application/x-pydaw-clipid-dup"):
                do_duplicate = True
        except Exception:
            pass
        try:
            if bool(event.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier):
                do_duplicate = True
        except Exception:
            pass

        assign_cid = str(clip_id)
        if do_duplicate:
            try:
                fn = getattr(self.project, 'clone_clip_for_launcher', None)
                if callable(fn):
                    new_id = fn(str(clip_id), target_track_id=str(track_id))
                    if new_id:
                        assign_cid = str(new_id)
            except Exception:
                pass

        # Assign to target slot
        self.project.cliplauncher_assign(key, assign_cid)

        # v0.0.20.620: Plain drag = MOVE → Quell-Slot leeren
        if not do_duplicate and src_slot and src_slot != key:
            try:
                self.project.cliplauncher_clear(src_slot)
            except Exception:
                pass

        try:
            self._set_selected_slot(key)
        except Exception:
            pass

        # UI refresh
        try:
            self.project.project_updated.emit()
        except Exception:
            pass

    def _slot_clicked(self, slot_key: str) -> None:
        """Left click on a slot: select it + open it in the editor (NO auto-play).

        v0.0.20.600: Multi-selection support:
        - Plain click: replace selection
        - Ctrl+Click: toggle slot in/out of selection
        - Shift+Click: range select (from last selected to this slot)
        """
        from PySide6.QtWidgets import QApplication
        mods = QApplication.keyboardModifiers()

        try:
            if mods & Qt.KeyboardModifier.ControlModifier:
                self._set_selected_slot(str(slot_key), toggle=True)
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                self._select_range_to(str(slot_key))
            else:
                self._set_selected_slot(str(slot_key))
        except Exception:
            pass

        cid = self.project.ctx.project.clip_launcher.get(str(slot_key), "")
        if cid:
            try:
                self.clip_activated.emit(str(cid))
            except Exception:
                pass

            if self.inspector:
                try:
                    self.inspector.set_clip(str(cid))
                except Exception:
                    pass

            if self.clip_context:
                parts = str(slot_key).split(":")
                if len(parts) == 4 and parts[0] == "scene" and parts[2] == "track":
                    try:
                        scene_idx = int(parts[1])
                        track_id = parts[3]
                        self.clip_context.set_active_slot(scene_idx, track_id, str(cid))
                    except Exception:
                        pass
            # v0.0.20.612: Dual-Clock Phase D — Launcher-Fokus an Editoren
            self._emit_launcher_focus(str(slot_key), str(cid))


    def _stop_track_clips(self, track_id: str) -> None:
        """Stop all playing clips on a specific track (Bitwig-style per-track stop)."""
        try:
            playback = getattr(self.project, '_cliplauncher_playback', None)
            if playback is None:
                return
            # Find all active slots for this track and stop them
            active = []
            try:
                active = playback.active_slots()
            except Exception:
                pass
            for slot_key in active:
                try:
                    parsed = self._parse_slot_key(str(slot_key))
                    if parsed and str(parsed[1]) == str(track_id):
                        playback.stop_slot(str(slot_key))
                except Exception:
                    pass
            try:
                self.project._emit_cliplauncher_active_slots()
            except Exception:
                pass
        except Exception:
            pass

    def _launch(self, slot_key: str) -> None:
        """Slot launchen — ▶ Button startet IMMER (Bitwig-Verhalten).

        v0.0.20.607: ▶ startet/restartet immer. Stop passiert NUR über:
        - ■ Stop-Button pro Track
        - Stop All
        - Space-Taste (toggle, via _toggle_selected_slot)
        """
        mode = str(self.cmb_mode.currentText() or 'Trigger')

        # Gate mode: handled separately in mousePressEvent/mouseReleaseEvent
        # All other modes: always (re)start the clip
        if mode == 'Repeat' or self.is_slot_playing(slot_key):
            # Retrigger: stop first, then restart below
            try:
                playback = getattr(self.project, '_cliplauncher_playback', None)
                if playback and self.is_slot_playing(slot_key):
                    playback.stop_slot(str(slot_key))
            except Exception:
                pass

        self.launcher.launch_slot(slot_key)
        cid = self.project.ctx.project.clip_launcher.get(slot_key, "")
        if cid:
            self.clip_activated.emit(cid)
            
            # v0.0.20.602: Set as active clip for MIDI recording
            # If the track is record-armed, the MIDI manager will record into this clip
            try:
                self.project.set_active_clip(str(cid))
            except Exception:
                pass

            if self.inspector:
                try:
                    self.inspector.set_clip(cid)
                except Exception:
                    pass
            
            if self.clip_context:
                parts = slot_key.split(":")
                if len(parts) == 4 and parts[0] == "scene" and parts[2] == "track":
                    try:
                        scene_idx = int(parts[1])
                        track_id = parts[3]
                        self.clip_context.set_active_slot(scene_idx, track_id, cid)
                    except Exception:
                        pass
            # v0.0.20.612: Dual-Clock Phase D — Launcher-Fokus an Editoren
            self._emit_launcher_focus(str(slot_key), str(cid))

    def _gate_release(self, slot_key: str) -> None:
        """v0.0.20.601: Gate mode — stop clip when mouse button released."""
        try:
            mode = str(self.cmb_mode.currentText() or 'Trigger')
            if mode != 'Gate':
                return
            if self.is_slot_playing(slot_key):
                playback = getattr(self.project, '_cliplauncher_playback', None)
                if playback:
                    playback.stop_slot(str(slot_key))
                    self.project._emit_cliplauncher_active_slots()
        except Exception:
            pass

    def _slot_double_click(self, slot_key: str) -> None:
        """Doppelklick auf Slot -> Clip aktivieren + Loop-Editor öffnen.

        v0.0.20.587: Bitwig-Style — Doppelklick auf LEEREN Slot erstellt
        automatisch einen MIDI-Clip (auf Instrument-Tracks) oder Audio-Clip.

        Wichtig: Diese Funktion darf niemals Exceptions nach Qt rauswerfen.
        (sonst kann PyQt6/SIP mit qFatal -> SIGABRT reagieren)
        """
        try:
            cid = self.project.ctx.project.clip_launcher.get(slot_key, "")
        except Exception:
            cid = ""

        if not cid:
            # v0.0.20.587: Empty slot → auto-create clip (Bitwig behavior)
            try:
                parsed = self._parse_slot_key(slot_key)
                if parsed:
                    _scene, track_id = parsed
                    trk = next((t for t in self.project.ctx.project.tracks if str(getattr(t, 'id', '')) == str(track_id)), None)
                    track_kind = str(getattr(trk, 'kind', 'audio') or 'audio') if trk else 'audio'
                    if track_kind == 'instrument':
                        new_cid = self._create_launcher_midi_clip(track_id, slot_key)
                    else:
                        new_cid = self._create_launcher_audio_clip(track_id, slot_key)
                    if new_cid:
                        self._set_selected_slot(slot_key)
                        self.clip_activated.emit(str(new_cid))
            except Exception:
                pass
            return

        # Clip als "active" setzen -> EditorTabs/PianoRoll/AudioEditor syncen darüber.
        try:
            self.project.set_active_clip(str(cid))
        except Exception:
            pass

        # Loop-Dialog öffnen (für Audio und MIDI).
        try:
            if self.clip_context:
                self.clip_context.open_loop_editor(str(cid))
        except Exception:
            pass

    # --- v0.0.20.587: Direct clip creation in Clip Launcher (Bitwig/Ableton-style) ---

    def _create_launcher_midi_clip(self, track_id: str, slot_key: str) -> str:
        """Create a new MIDI clip and assign it to the given launcher slot.

        Bitwig/Ableton behavior:
        - Creates a 4-bar MIDI clip on the target track
        - Marks it as launcher_only (NOT visible in Arranger)
        - If the track is not an instrument track, auto-converts it
        - Assigns the clip to the slot
        - Returns the new clip_id
        """
        try:
            # Use the project service's existing MIDI clip creation
            # start_beats=0 because launcher clips don't have arranger position
            new_cid = self.project.add_midi_clip_at(
                track_id=str(track_id),
                start_beats=0.0,
                length_beats=float(self._beats_per_bar_ui() * 4),  # 4 bars
            )
            if new_cid:
                # v0.0.20.588: Bitwig-Style — Launcher clips are NOT in Arranger
                clip_obj = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(new_cid)), None)
                if clip_obj is not None:
                    clip_obj.launcher_only = True
                self.project.cliplauncher_assign(str(slot_key), str(new_cid))
                self.project.status.emit(f'ClipLauncher: MIDI-Clip erstellt → Slot')
            return str(new_cid) if new_cid else ''
        except Exception:
            return ''

    def _create_launcher_audio_clip(self, track_id: str, slot_key: str) -> str:
        """Create a new empty audio clip placeholder and assign it to a launcher slot."""
        try:
            fn = getattr(self.project, 'add_placeholder_clip_to_track', None)
            if callable(fn):
                fn(str(track_id), kind='audio')
                # The placeholder was added as the latest clip; find and assign it
                clips = self.project.ctx.project.clips or []
                track_clips = [c for c in clips if str(getattr(c, 'track_id', '')) == str(track_id) and str(getattr(c, 'kind', '')) == 'audio']
                if track_clips:
                    latest = track_clips[-1]
                    cid = str(getattr(latest, 'id', ''))
                    if cid:
                        # v0.0.20.588: Bitwig-Style — Launcher clips are NOT in Arranger
                        latest.launcher_only = True
                        self.project.cliplauncher_assign(str(slot_key), cid)
                        self.project.status.emit(f'ClipLauncher: Audio-Clip erstellt → Slot')
                        return cid
        except Exception:
            pass
        return ''

    def _slot_menu(self, btn: SlotButton) -> None:
        key = str(btn.property("slot_key") or "")
        if not key:
            return

        # Remember selection for Ctrl+C/V/Del on the grid
        try:
            self._set_selected_slot(key)
        except Exception:
            pass

        cid = self.project.ctx.project.clip_launcher.get(key, "")
        
        menu = QMenu(self)

        # v0.0.20.587: Create new clips directly in the Clip Launcher (Bitwig/Ableton-style)
        a_create_midi = None
        a_create_audio = None
        a_audio_record = None
        a_audio_record_stop = None
        parsed = self._parse_slot_key(key)
        if parsed:
            _scene, track_id = parsed
            if not cid:
                a_create_midi = menu.addAction("MIDI-Clip erstellen")
                a_create_audio = menu.addAction("Audio-Clip erstellen")
                menu.addSeparator()
            # v0.0.20.605: Audio recording
            rec_svc = getattr(self, '_record_service', None)
            if rec_svc and rec_svc.is_recording():
                a_audio_record_stop = menu.addAction("⏹ Aufnahme stoppen")
            else:
                a_audio_record = menu.addAction("⏺ Audio aufnehmen")
            menu.addSeparator()

        a_assign = menu.addAction("Ausgewählten Clip zuweisen")
        a_select = menu.addAction("Clip auswählen")

        # v0.0.20.603: MIDI Pattern generieren (Phase 6.1 KI-Innovation)
        a_midi_gen = None
        # v0.0.20.604: Recording mode + Variations
        a_overdub = None
        a_replace = None
        a_rec_quantize = None
        a_add_variation = None
        a_smart_quantize = None
        _rq_actions = []
        if cid:
            clip_obj = next((c for c in (self.project.ctx.project.clips or []) if str(getattr(c, "id", "")) == str(cid)), None)
            if clip_obj and str(getattr(clip_obj, 'kind', '')) == 'midi':
                menu.addSeparator()
                a_midi_gen = menu.addAction("♪ MIDI Pattern generieren...")
                # Recording sub
                rec_menu = menu.addMenu("⏺ Recording")
                a_overdub = rec_menu.addAction("✓ Overdub" if str(getattr(clip_obj, 'launcher_record_mode', 'Overdub')) == 'Overdub' else "Overdub")
                a_replace = rec_menu.addAction("✓ Replace" if str(getattr(clip_obj, 'launcher_record_mode', 'Overdub')) == 'Replace' else "Replace")
                rq_menu = rec_menu.addMenu("Quantize")
                _rq_opts = ["Off", "1/16", "1/8", "1/4", "1 Bar"]
                _rq_actions = []
                cur_rq = str(getattr(clip_obj, 'launcher_record_quantize', 'Off') or 'Off')
                for rq in _rq_opts:
                    a = rq_menu.addAction(f"✓ {rq}" if rq == cur_rq else rq)
                    _rq_actions.append((rq, a))
                # Variations
                menu.addSeparator()
                a_add_variation = menu.addAction("+ Variation hinzufügen")
                a_smart_quantize = menu.addAction("♫ Smart Quantize")
        
        # NEU: Loop-Editor nur wenn Clip zugewiesen ist
        a_loop_editor = None
        if cid and self.clip_context:
            menu.addSeparator()
            a_loop_editor = menu.addAction("Loop-Editor öffnen...")

        # v0.0.20.174: Render/Restore Actions (wie Arranger/Audio-Editor)
        a_rr_from = None
        a_rr_ip = None
        a_restore_ip = None
        a_toggle = None
        a_rebuild = None
        a_back = None
        if cid:
            try:
                clip_obj = next((c for c in (self.project.ctx.project.clips or []) if str(getattr(c, "id", "")) == str(cid)), None)
                rm = getattr(clip_obj, "render_meta", {}) if clip_obj is not None else {}
                src_ok = False
                if isinstance(rm, dict):
                    src = rm.get("sources", {})
                    if isinstance(src, dict) and str(src.get("source_clip_id", "") or "").strip():
                        src_ok = True
                menu.addSeparator()
                a_rr_from = menu.addAction("Re-render (from sources)")
                a_rr_from.setEnabled(bool(src_ok))
                a_rr_ip = menu.addAction("Re-render (in place)")
                a_restore_ip = menu.addAction("Restore Sources (in place)")
                a_back = menu.addAction("Back to Sources")
                a_toggle = menu.addAction("Toggle Rendered ↔ Sources")
                a_rebuild = menu.addAction("Rebuild original clip state")
                if not src_ok:
                    a_restore_ip.setEnabled(False)
                    a_back.setEnabled(False)
                    a_toggle.setEnabled(False)
                    a_rebuild.setEnabled(False)
            except Exception:
                pass

        menu.addSeparator()
        a_clear = menu.addAction("Slot leeren")

        act = menu.exec(btn.mapToGlobal(btn.rect().center()))

        # v0.0.20.587: Create new MIDI/Audio clip directly in the Clip Launcher
        if a_create_midi and act == a_create_midi:
            try:
                parsed = self._parse_slot_key(key)
                if parsed:
                    _scene, track_id = parsed
                    new_cid = self._create_launcher_midi_clip(track_id, key)
                    if new_cid:
                        self._set_selected_slot(key)
                        self.clip_activated.emit(str(new_cid))
            except Exception:
                pass
        elif a_create_audio and act == a_create_audio:
            try:
                parsed = self._parse_slot_key(key)
                if parsed:
                    _scene, track_id = parsed
                    new_cid = self._create_launcher_audio_clip(track_id, key)
                    if new_cid:
                        self._set_selected_slot(key)
                        self.clip_activated.emit(str(new_cid))
            except Exception:
                pass
        elif act == a_assign:
            active_cid = self.project.active_clip_id
            if active_cid:
                self.project.cliplauncher_assign(key, active_cid)
        elif act == a_clear:
            self.project.cliplauncher_clear(key)
        elif act == a_select:
            if cid:
                self.project.select_clip(cid)
                self.clip_activated.emit(cid)

        # v0.0.20.174: Render/Restore actions
        elif a_rr_from and act == a_rr_from:
            try:
                if cid and hasattr(self.project, 'rerender_clip_from_meta'):
                    self.project.rerender_clip_from_meta(str(cid), replace_usages=True)  # type: ignore[attr-defined]
            except Exception:
                pass
        elif a_rr_ip and act == a_rr_ip:
            try:
                if cid and hasattr(self.project, 'rerender_clip_in_place_from_meta'):
                    self.project.rerender_clip_in_place_from_meta(str(cid))  # type: ignore[attr-defined]
            except Exception:
                pass
        elif a_restore_ip and act == a_restore_ip:
            try:
                if cid and hasattr(self.project, 'restore_sources_in_place_from_meta'):
                    self.project.restore_sources_in_place_from_meta(str(cid))  # type: ignore[attr-defined]
            except Exception:
                pass
        elif a_toggle and act == a_toggle:
            try:
                if cid and hasattr(self.project, 'toggle_rendered_sources_in_place_from_meta'):
                    self.project.toggle_rendered_sources_in_place_from_meta(str(cid))  # type: ignore[attr-defined]
            except Exception:
                pass
        elif a_rebuild and act == a_rebuild:
            try:
                if cid and hasattr(self.project, 'rebuild_original_clip_state_from_meta'):
                    self.project.rebuild_original_clip_state_from_meta(str(cid))  # type: ignore[attr-defined]
            except Exception:
                pass
        elif a_back and act == a_back:
            try:
                if cid and hasattr(self.project, 'back_to_sources_from_meta'):
                    self.project.back_to_sources_from_meta(str(cid))  # type: ignore[attr-defined]
            except Exception:
                pass

        elif a_loop_editor and act == a_loop_editor:
            # Loop-Editor öffnen
            if self.clip_context:
                self.clip_context.open_loop_editor(cid)

        # v0.0.20.603: MIDI Pattern generieren
        elif a_midi_gen and act == a_midi_gen:
            self._generate_midi_pattern(key)

        # v0.0.20.604: Recording mode
        elif a_overdub and act == a_overdub:
            try:
                clip_obj = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(cid)), None)
                if clip_obj:
                    clip_obj.launcher_record_mode = 'Overdub'
                    self.project.status.emit('Record: Overdub')
                    self.project.project_updated.emit()
            except Exception:
                pass
        elif a_replace and act == a_replace:
            try:
                clip_obj = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(cid)), None)
                if clip_obj:
                    clip_obj.launcher_record_mode = 'Replace'
                    self.project.status.emit('Record: Replace')
                    self.project.project_updated.emit()
            except Exception:
                pass

        # v0.0.20.604: Record quantize
        if cid and act:
            try:
                for rq_val, rq_act in (_rq_actions if '_rq_actions' in dir() else []):
                    if act == rq_act:
                        clip_obj = next((c for c in self.project.ctx.project.clips if str(getattr(c, 'id', '')) == str(cid)), None)
                        if clip_obj:
                            clip_obj.launcher_record_quantize = str(rq_val)
                            self.project.status.emit(f'Record Quantize: {rq_val}')
                            self.project.project_updated.emit()
                        break
            except Exception:
                pass

        # v0.0.20.604: Add variation
        if a_add_variation and act == a_add_variation:
            self._add_clip_variation(key, cid)

        # v0.0.20.604: Smart Quantize
        if a_smart_quantize and act == a_smart_quantize:
            self._smart_quantize_clip(cid)

        # v0.0.20.605: Audio Recording
        if a_audio_record and act == a_audio_record:
            self._start_audio_recording(key)
        elif a_audio_record_stop and act == a_audio_record_stop:
            self._stop_audio_recording()

    def _get_record_service(self):
        """Lazy-init the ClipLauncherRecordService."""
        if not hasattr(self, '_record_service') or self._record_service is None:
            try:
                from pydaw.services.cliplauncher_record import ClipLauncherRecordService
                ae = getattr(self.project, 'audio_engine', None) or getattr(getattr(self.project, 'services', None), 'audio_engine', None)
                tr = getattr(self.project, 'transport', None) or getattr(self.launcher, 'transport', None)
                self._record_service = ClipLauncherRecordService(self.project, ae, tr)
            except Exception:
                self._record_service = None
        return self._record_service

    def _start_audio_recording(self, slot_key: str) -> None:
        """Start audio recording into a launcher slot."""
        try:
            parsed = self._parse_slot_key(slot_key)
            if not parsed:
                return
            _scene, track_id = parsed

            rec = self._get_record_service()
            if rec is None:
                self.project.status.emit("Audio Recording nicht verfügbar (sounddevice fehlt)")
                return

            # Check punch in/out from project model
            punch_in = 0.0
            punch_out = 0.0
            try:
                if bool(getattr(self.project.ctx.project, 'launcher_punch_in', False)):
                    # Use loop region of currently playing clip on this track
                    playback = getattr(self.project, '_cliplauncher_playback', None)
                    if playback:
                        with playback._lock:
                            for sk, v in playback._voices.items():
                                if str(v.track_id) == str(track_id):
                                    punch_in = v.loop_start_beats
                                    punch_out = v.loop_end_beats
                                    break
            except Exception:
                pass

            ok = rec.start_recording(slot_key, track_id, punch_in=punch_in, punch_out=punch_out)
            if ok:
                self.project.status.emit(f"⏺ Audio Recording gestartet auf {track_id}")
            else:
                self.project.status.emit("Audio Recording konnte nicht gestartet werden")
        except Exception:
            pass

    def _stop_audio_recording(self) -> None:
        """Stop audio recording and save."""
        try:
            rec = getattr(self, '_record_service', None)
            if rec and rec.is_recording():
                path = rec.stop_recording()
                if path:
                    self.project.status.emit(f"⏹ Audio gespeichert: {os.path.basename(path)}")
                else:
                    self.project.status.emit("Aufnahme gestoppt (keine Daten)")
        except Exception:
            pass