# -*- coding: utf-8 -*-
"""Compact UI widgets for the Sampler device (Pro-DAW-Style Device Panel).

Knob: small QPainter-drawn rotary knob with label + value.
WaveformDisplay: thin waveform strip with loop markers.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np

from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import QWidget, QSizePolicy, QFrame, QMenu


class CompactKnob(QWidget):
    """Compact QPainter-drawn knob (~52x64 px).

    v0.0.20.90:
    - Optional AutomationManager binding (register_parameter)
    - Right-click context menu: "Show Automation in Arranger" + reset
    - External updates (automation playback) move the knob without feedback loops

    Notes:
    - The AutomationManager emits parameter_changed(parameter_id, value) (2 args).
    - We block signals on external updates so legacy engine wiring does not fire.
    """

    valueChanged = pyqtSignal(int)

    def __init__(self, title: str = "", init: int = 0, parent=None):
        super().__init__(parent)
        self._title = title
        self._minimum = 0
        self._maximum = 100
        self._value = int(max(self._minimum, min(self._maximum, init)))
        self._dragging = False
        self._drag_y = 0

        # --- automation binding (optional)
        self._automation_manager = None
        self._automation_param = None
        self._parameter_id: str = ""
        self._track_id: str = ""
        self._default_value: float = float(self._value)
        self._external_update: bool = False
        self._mgr_connected: bool = False

        self.setFixedSize(52, 64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._format_tooltip())

    # ---------------- basic API
    def value(self) -> int:
        return self._value

    def minimum(self) -> int:
        return int(self._minimum)

    def maximum(self) -> int:
        return int(self._maximum)

    def setRange(self, minimum: int, maximum: int) -> None:
        try:
            lo = int(round(float(minimum)))
            hi = int(round(float(maximum)))
        except Exception:
            lo, hi = 0, 100
        if hi < lo:
            lo, hi = hi, lo
        self._minimum = lo
        self._maximum = hi
        self.setValue(self._value)

    def _value_ratio(self) -> float:
        span = float(self._maximum - self._minimum)
        if span <= 0.0:
            return 0.0
        return max(0.0, min(1.0, (float(self._value) - float(self._minimum)) / span))

    def _format_value_text(self) -> str:
        v = float(self._value)
        lo = int(self._minimum)
        hi = int(self._maximum)
        if lo == 0 and hi == 100:
            return f"{int(round(v))}%"
        if abs(v) >= 1000.0:
            if abs(v) >= 10000.0 or float(int(v)) == v:
                return f"{int(round(v / 1000.0))}k"
            return f"{v / 1000.0:.1f}k"
        if float(int(v)) == v:
            return str(int(v))
        return f"{v:.1f}"

    def _format_tooltip(self) -> str:
        return f"{self._title}: {self._format_value_text()}"

    def setValueExternal(self, v: int) -> None:
        """Set value from automation/playback without emitting valueChanged."""
        try:
            self._external_update = True
            self.blockSignals(True)
            self.setValue(int(v))
        finally:
            try:
                self.blockSignals(False)
            except Exception:
                pass
            self._external_update = False

    # ---------------- automation
    def bind_automation(
        self,
        automation_manager,
        parameter_id: str,
        *,
        name: str | None = None,
        track_id: str = "",
        minimum: float = 0.0,
        maximum: float = 100.0,
        default: float | None = None,
    ) -> None:
        """Bind this knob to an AutomatableParameter in the global AutomationManager."""
        self._automation_manager = automation_manager
        self._parameter_id = str(parameter_id or "")
        self._track_id = str(track_id or "")

        if default is None:
            default = float(self._value)
        self._default_value = float(default)

        # Create / fetch parameter
        try:
            if self._automation_manager is not None and self._parameter_id:
                self._automation_param = self._automation_manager.register_parameter(
                    self._parameter_id,
                    str(name or self._title or self._parameter_id),
                    float(minimum),
                    float(maximum),
                    float(default),
                    track_id=self._track_id,
                )
        except Exception:
            self._automation_param = None

        # Listen to global changes once (knob updates itself on playback)
        if (not self._mgr_connected) and (self._automation_manager is not None):
            try:
                self._automation_manager.parameter_changed.connect(self._on_mgr_parameter_changed)
                self._mgr_connected = True
            except Exception:
                self._mgr_connected = False

        # Right-click context menu (Bitwig/Ableton style)
        try:
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            try:
                self.customContextMenuRequested.disconnect(self._show_context_menu)
            except Exception:
                pass
            self.customContextMenuRequested.connect(self._show_context_menu)
        except Exception:
            pass

        # Seed base value into the parameter
        try:
            if self._automation_param is not None:
                self._automation_param.set_value(float(self._value))
        except Exception:
            pass

        # v0.0.20.569: Restore persistent CC mapping if one exists
        # (survives widget recreation on zoom out/in, track rebuild, etc.)
        try:
            persistent = getattr(self._automation_manager, "_persistent_cc_map", None)
            if isinstance(persistent, dict) and self._parameter_id:
                cc_info = persistent.get(str(self._parameter_id))
                if cc_info is not None:
                    ch, cc = int(cc_info[0]), int(cc_info[1])
                    self._midi_cc_mapping = (ch, cc)
                    self._register_midi_cc_listener()
        except Exception:
            pass

    def set_automation_target(self, parameter_id: str, *, default: float | None = None) -> None:
        """Switch this knob to control another parameter_id (e.g. Drum slot selection)."""
        self._parameter_id = str(parameter_id or "")
        if default is not None:
            self._default_value = float(default)
        try:
            if self._automation_manager is not None and self._parameter_id:
                self._automation_param = self._automation_manager.get_parameter(self._parameter_id)
        except Exception:
            self._automation_param = None

    # ---------------- value changes
    def setValue(self, v: int) -> None:
        v = int(max(self._minimum, min(self._maximum, int(v))))
        if v != self._value:
            self._value = v
            self.setToolTip(self._format_tooltip())
            self.update()

            if not self.signalsBlocked():
                self.valueChanged.emit(v)

            # Push base value into automation system ONLY for interactive changes
            if (not self._external_update) and (self._automation_param is not None):
                try:
                    self._automation_param.set_value(float(v))
                except Exception:
                    pass

    def _on_mgr_parameter_changed(self, parameter_id: str, value: float) -> None:
        """Automation playback / lane edits → GUI."""
        try:
            if str(parameter_id) != str(self._parameter_id):
                return
            self.setValueExternal(int(round(float(value))))
        except Exception:
            pass

    def _show_context_menu(self, pos) -> None:
        try:
            if self._automation_manager is None or not self._parameter_id:
                return
            menu = QMenu(self)
            act_show = menu.addAction("🔲 Show Automation in Arranger")

            # v0.0.20.397: MIDI Learn context menu
            act_learn = None
            act_unmap = None
            cc_info = getattr(self, "_midi_cc_mapping", None)
            if cc_info is not None:
                ch, cc_num = cc_info
                menu.addAction(f"🎹 Mapped: CC{cc_num} ch{ch}").setEnabled(False)
                act_unmap = menu.addAction("🎹 MIDI Mapping entfernen")
            else:
                act_learn = menu.addAction("🎹 MIDI Learn")

            act_mod = menu.addAction("🔲 Add Modulator (LFO/ENV) — coming soon")
            try:
                act_mod.setEnabled(False)
            except Exception:
                pass
            menu.addSeparator()
            act_reset = menu.addAction("↩ Reset to Default")

            chosen = menu.exec(self.mapToGlobal(pos))
            if chosen is None:
                return
            if chosen == act_show:
                try:
                    self._automation_manager.request_show_automation.emit(str(self._parameter_id))
                except Exception:
                    pass
            elif chosen == act_learn:
                self._start_midi_learn()
            elif chosen == act_unmap:
                self._midi_cc_mapping = None
                self._remove_midi_cc_listener()
                # v0.0.20.569: Also remove from persistent map
                try:
                    persistent = getattr(self._automation_manager, "_persistent_cc_map", None)
                    if isinstance(persistent, dict) and self._parameter_id:
                        persistent.pop(str(self._parameter_id), None)
                except Exception:
                    pass
            elif chosen == act_reset:
                try:
                    if self._automation_param is not None:
                        self._automation_param.set_value(float(self._default_value))
                        self._automation_param.set_automation_value(None)
                except Exception:
                    pass
                self.setValueExternal(int(round(self._default_value)))
        except Exception:
            pass

    # ── MIDI Learn (v0.0.20.397) ──

    def _start_midi_learn(self) -> None:
        """Enter MIDI Learn mode: next CC sets the mapping."""
        try:
            # Find the MidiMappingService or MIDI input
            mgr = self._automation_manager
            if mgr is None:
                return
            # Store ourselves as the learn target on the automation manager
            mgr._midi_learn_knob = self
            # Visual feedback
            self.setStyleSheet("border: 2px solid #ff6060;")
            # Status message
            try:
                from PyQt6.QtWidgets import QApplication
                sb = None
                for w in QApplication.topLevelWidgets():
                    sb = getattr(w, "statusBar", None)
                    if callable(sb):
                        sb().showMessage("MIDI Learn aktiv: bewege jetzt einen CC-Regler am Controller.", 10000)
                        break
            except Exception:
                pass
        except Exception:
            pass

    def _on_midi_learn_cc(self, channel: int, cc: int) -> None:
        """Called when a CC is received during MIDI Learn mode."""
        self._midi_cc_mapping = (int(channel), int(cc))
        self.setStyleSheet("")
        # Register CC listener
        self._register_midi_cc_listener()
        # v0.0.20.569: Save to persistent registry (survives widget rebuilds)
        try:
            mgr = self._automation_manager
            pid = getattr(self, "_parameter_id", None)
            if mgr is not None and pid:
                persistent = getattr(mgr, "_persistent_cc_map", None)
                if persistent is None:
                    mgr._persistent_cc_map = {}
                    persistent = mgr._persistent_cc_map
                persistent[str(pid)] = (int(channel), int(cc))
        except Exception:
            pass

    def _register_midi_cc_listener(self) -> None:
        """Register this knob to receive CC updates from the MIDI input."""
        try:
            mgr = self._automation_manager
            if mgr is None:
                return
            cc_listeners = getattr(mgr, "_midi_cc_listeners", None)
            if cc_listeners is None:
                mgr._midi_cc_listeners = {}
                cc_listeners = mgr._midi_cc_listeners
            mapping = self._midi_cc_mapping
            if mapping is not None:
                cc_listeners[mapping] = self
        except Exception:
            pass

    def _remove_midi_cc_listener(self) -> None:
        """Unregister this knob from CC updates."""
        try:
            mgr = self._automation_manager
            if mgr is None:
                return
            cc_listeners = getattr(mgr, "_midi_cc_listeners", None)
            if cc_listeners is None:
                return
            # Remove any entries pointing to this knob
            to_remove = [k for k, v in cc_listeners.items() if v is self]
            for k in to_remove:
                del cc_listeners[k]
        except Exception:
            pass

    def handle_midi_cc(self, value_0_127: int) -> None:
        """Apply incoming MIDI CC value (0-127) → knob 0-100 + engine."""
        try:
            lo = int(self._minimum)
            hi = int(self._maximum)
            v = lo + int(round((int(value_0_127) / 127.0) * float(hi - lo)))
            self.setValue(v)  # Updates visual + emits valueChanged → engine
        except Exception:
            pass

    # ---------------- drawing + interaction
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Title (top)
        p.setPen(QColor("#aaaaaa"))
        p.setFont(QFont("Sans", 7))
        p.drawText(0, 0, w, 12, Qt.AlignmentFlag.AlignHCenter, self._title)

        cx, cy = w // 2, 12 + 20
        r = 14

        # Background arc
        p.setPen(QPen(QColor("#333333"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        arc = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.drawArc(arc, 225 * 16, -270 * 16)

        # Value arc
        ratio = self._value_ratio()
        if ratio > 0.0:
            p.setPen(QPen(QColor("#e060e0"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            span = int(-270 * ratio)
            p.drawArc(arc, 225 * 16, span * 16)

        # Pointer
        angle = math.radians(225.0 - ratio * 270.0)
        px = cx + (r - 4) * math.cos(angle)
        py = cy - (r - 4) * math.sin(angle)
        p.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(int(cx), int(cy), int(px), int(py))

        # Center dot
        p.setBrush(QColor("#666666"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - 3, cy - 3, 6, 6)

        # Value (bottom)
        p.setPen(QColor("#cccccc"))
        p.setFont(QFont("Sans", 7))
        p.drawText(0, h - 12, w, 12, Qt.AlignmentFlag.AlignHCenter, self._format_value_text())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_y = int(e.position().y())

    def mouseMoveEvent(self, e):
        if self._dragging:
            dy = self._drag_y - int(e.position().y())
            self._drag_y = int(e.position().y())
            self.setValue(self._value + dy)

    def mouseReleaseEvent(self, _):
        self._dragging = False

    def wheelEvent(self, e):
        delta = 1 if e.angleDelta().y() > 0 else -1
        self.setValue(self._value + delta)


class WaveformStrip(QFrame):
    """Thin waveform strip for Pro-DAW device panel."""
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setMinimumHeight(40)
        self.setMaximumHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background:#0d0d0d;border:1px solid #222;border-radius:3px;")
        self.samples: Optional[np.ndarray] = None
        self.info = "No audio loaded"
        self.position = 0.0
        self.start_position = 0.0
        self.end_position = 1.0
        self.loop_start = 0.0
        self.loop_end = 1.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(40)

        # v0.0.20.214: Region Start/End Drag-Handles (UI-only, Bitwig/Ableton-Style)
        try:
            self.setMouseTracking(True)
        except Exception:
            pass
        self._region_drag = None  # "start" | "end" | None
        self._region_hover = None
        self._region_hit_px = 7

    def _poll(self):
        try:
            if getattr(self.engine, "samples", None) is not None:
                self.samples = self.engine.samples
            if self.samples is not None:
                n = max(1, len(self.samples))
                self.position = float(getattr(self.engine.state, "position", 0.0)) / n
                self.start_position = float(getattr(self.engine.state, "start_position", 0.0))
                self.end_position = float(getattr(self.engine.state, "end_position", 1.0))
                self.loop_start = float(getattr(self.engine.state, "loop_start", 0.0))
                self.loop_end = float(getattr(self.engine.state, "loop_end", 1.0))
        except Exception:
            pass
        self.update()

    def set_info(self, text: str):
        self.info = text
        self.update()

    # ---- Region handle interaction (safe, ignores missing engine APIs)
    def _wave_rect(self):
        try:
            return self.rect().adjusted(2, 2, -2, -2)
        except Exception:
            return self.rect()

    def _norm_from_x(self, x: float, rect) -> float:
        try:
            w = max(1.0, float(rect.width()))
            return float(max(0.0, min(1.0, (float(x) - float(rect.left())) / w)))
        except Exception:
            return 0.0

    def _hit_region_handle(self, pos, rect):
        try:
            if pos.y() < rect.top() or pos.y() > rect.bottom():
                return None
            x = float(pos.x())
        except Exception:
            return None
        try:
            xs = float(rect.left()) + float(self.start_position) * float(rect.width())
            xe = float(rect.left()) + float(self.end_position) * float(rect.width())
            hp = int(getattr(self, "_region_hit_px", 7) or 7)
            if abs(x - xs) <= hp:
                return "start"
            if abs(x - xe) <= hp:
                return "end"
        except Exception:
            return None
        return None

    def _set_cursor_for_region(self, which):
        try:
            if which in ("start", "end"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.unsetCursor()
        except Exception:
            pass

    def mousePressEvent(self, e):
        try:
            if e.button() == Qt.MouseButton.LeftButton and self.samples is not None and len(self.samples) > 2:
                rect = self._wave_rect()
                hit = self._hit_region_handle(e.position(), rect)
                if hit in ("start", "end"):
                    self._region_drag = hit
                    self._set_cursor_for_region(hit)
                    e.accept()
                    return
        except Exception:
            pass
        try:
            super().mousePressEvent(e)
        except Exception:
            pass

    def mouseMoveEvent(self, e):
        try:
            rect = self._wave_rect()
            if getattr(self, "_region_drag", None) in ("start", "end"):
                which = str(self._region_drag)
                n = self._norm_from_x(e.position().x(), rect)
                eng = getattr(self, "engine", None)
                if eng is not None and hasattr(eng, "set_region_norm"):
                    if which == "start":
                        try:
                            eng.set_region_norm(start=float(n), end=None)
                        except TypeError:
                            eng.set_region_norm(start=float(n))
                        self.start_position = float(n)
                    else:
                        try:
                            eng.set_region_norm(start=None, end=float(n))
                        except TypeError:
                            eng.set_region_norm(end=float(n))
                        self.end_position = float(n)
                e.accept()
                self.update()
                return

            # hover cursor
            hit = self._hit_region_handle(e.position(), rect)
            if hit != getattr(self, "_region_hover", None):
                self._region_hover = hit
                self._set_cursor_for_region(hit)
                self.update()
        except Exception:
            pass
        try:
            super().mouseMoveEvent(e)
        except Exception:
            pass

    def mouseReleaseEvent(self, e):
        try:
            if getattr(self, "_region_drag", None) in ("start", "end"):
                self._region_drag = None
                # keep hover state based on current pointer
                try:
                    rect = self._wave_rect()
                    self._region_hover = self._hit_region_handle(e.position(), rect)
                    self._set_cursor_for_region(self._region_hover)
                except Exception:
                    self._set_cursor_for_region(None)
                e.accept()
                self.update()
                return
        except Exception:
            pass
        try:
            super().mouseReleaseEvent(e)
        except Exception:
            pass

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        p.fillRect(rect, QColor("#0d0d0d"))

        if self.samples is None or len(self.samples) < 2:
            p.setPen(QColor("#666"))
            p.setFont(QFont("Sans", 8))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.info)
            return

        W = max(1, rect.width())
        n = len(self.samples)
        step = max(1, n // W)
        usable = self.samples[:n - (n % step)]
        if usable.size < step:
            return

        chunk = usable.reshape(-1, step)
        mins, maxs = chunk.min(axis=1), chunk.max(axis=1)
        mid = rect.center().y()
        amp = rect.height() / 2.2

        p.setPen(QPen(QColor("#1bd760"), 1))
        for i in range(min(len(mins), W)):
            x = rect.left() + i
            y1, y2 = int(mid - float(mins[i]) * amp), int(mid - float(maxs[i]) * amp)
            if y1 > y2: y1, y2 = y2, y1
            p.drawLine(x, y1, x, y2)

        p.setPen(QPen(QColor("#d64d2a"), 1))
        xs = rect.left() + int(self.loop_start * rect.width())
        xe = rect.left() + int(self.loop_end * rect.width())
        p.drawLine(xs, rect.top(), xs, rect.bottom())
        p.drawLine(xe, rect.top(), xe, rect.bottom())

        # Region markers (Start/End)
        try:
            p.setPen(QPen(QColor("#e060e0"), 1))
            xrs = rect.left() + int(float(self.start_position) * rect.width())
            xre = rect.left() + int(float(self.end_position) * rect.width())
            p.drawLine(xrs, rect.top(), xrs, rect.bottom())
            p.drawLine(xre, rect.top(), xre, rect.bottom())
        except Exception:
            pass

        # Region handle caps (drag handles)
        try:
            hw = 8.0
            hh = 10.0
            xs = float(rect.left()) + float(self.start_position) * float(rect.width())
            xe = float(rect.left()) + float(self.end_position) * float(rect.width())
            for tag, x in (("start", xs), ("end", xe)):
                hot = (tag == getattr(self, "_region_drag", None)) or (tag == getattr(self, "_region_hover", None))
                col = QColor("#ff7aff") if hot else QColor("#e060e0")
                r = QRectF(float(x) - hw / 2.0, float(rect.top()), hw, hh)
                p.fillRect(r, col)
                p.setPen(QPen(QColor("#0a0a0a"), 1))
                p.drawRect(r)
        except Exception:
            pass

        p.setPen(QPen(QColor("#ffaa00"), 1))
        xp = rect.left() + int(self.position * rect.width())
        p.drawLine(xp, rect.top(), xp, rect.bottom())


# Legacy compat
Knob = CompactKnob


class WaveformDisplay(WaveformStrip):
    """Backward-compat wrapper with load_wav_file."""
    
    def __init__(self, engine=None, parent=None):
        super().__init__(engine, parent)
        self.path: str = ""  # v0.0.20.75: Store path for persistence
    
    def load_wav_file(self, path: str, *, engine=None) -> bool:
        """Load audio file and display waveform.
        
        Args:
            path: Path to audio file
            engine: Optional ProSamplerEngine to load samples into.
                    If None, uses self.engine (from WaveformStrip).
        """
        try:
            from .audio_io import load_audio
            target_engine = engine if engine is not None else self.engine
            # Get target sample rate from engine
            target_sr = 48000
            if target_engine is not None:
                try:
                    target_sr = int(target_engine.target_sr)
                except Exception:
                    pass
            
            data, sr = load_audio(path, target_sr=target_sr)
            mono = data.mean(axis=1).astype(np.float32, copy=False)
            self.samples = mono
            self.info = f"{Path(path).name} | {len(mono)/sr:.2f}s | {sr}Hz"
            self.path = str(path)  # v0.0.20.75: Store path for persistence
            
            if target_engine is not None:
                ok = bool(target_engine.load_wav(path))
            else:
                ok = True
            return ok
        except Exception as e:
            self.info = f"Load error: {e}"
            return False
