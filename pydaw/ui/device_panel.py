# -*- coding: utf-8 -*-
"""Device Panel — per-track device chain (Pro-DAW-Style).

v0.0.20.130 — DevicePanel UX (Mini-Legende/Popover im Header, UI-only)\n- Neuer kompakter Header-Button „?" öffnet eine Mini-Legende/Popover direkt im DevicePanel (Batch-Icons + Bedienung).\n- Rein visuell / UI-only; keine Audio/DSP/DnD/Projektmodell-Änderungen.\n\nv0.0.20.128 — DevicePanel UX (Reset-Button als kompaktes Icon, UI-only)
- Reset-Button im DevicePanel-Header als kompaktes Icon (↺) statt Textbutton, gleiche Funktion/Tooltip.
- Nur aktiv bei DevicePanel/Kind-Fokus; keine Audio/DSP/DnD/Projektmodell-Änderungen.

v0.0.20.124 — DevicePanel UX (Collapsed Mini-Cards compact width polish, UI-only)
- Header-Batchbuttons erhalten bessere Entdeckbarkeit: Hinweiszeile + Hover-Hinweise + aktiver Fokusmodus (N/I/A/◎) markiert.
- Rein visuell/UI-only; keine Änderungen an Audio/DSP/DnD/Reorder/Projektmodell.

v0.0.20.122 — DevicePanel UX (Zone-Fokus + kompaktere Collapsed-Cards, UI-only)
- Neue Header-Aktionen „N / I / A“: nur NOTE-FX / nur INSTRUMENT / nur AUDIO-FX offen (UI-only Zonenfokus).
- Eingeklappte Device-Cards schrumpfen nun sichtbar auf Kopfzeilen-Breite statt die alte Card-Breite zu blockieren.
- UI-only: keine Änderungen an Audio/DSP/DnD/Reorder/Projektmodell.

v0.0.20.121 — DevicePanel UX (Focus Collapse / Nur Fokus offen, UI-only)
- Neue Header-Aktion „Fokus“: klappt alle Device-Cards ein und lässt nur die fokussierte Card offen.
- Falls keine FX-Card fokussiert ist, bleibt automatisch der Instrument-Anchor offen (sicherer Fallback).
- UI-only: keine Änderungen an Audio/DSP/DnD/Reorder/Projektmodell.

v0.0.20.120 — DevicePanel UX (Batch Actions compact icons + Collapse All)
- Header-Batchaktionen als kompakte Icon-Buttons mit Tooltips (ruhiger/platzsparender).
- Neue UI-only Aktion: „Alle einklappen“ für schnelle Übersicht in langen Chains.
- Keine Änderungen an Audio/DnD/Reorder/Projektmodell.

v0.0.20.119 — DevicePanel UX (Header-Line Polish: Elide + spacing)
- Device-Card header line unified (consistent icon spacing, title elide/tooltip on overflow).
- UI-only, no DnD/Reorder/Audio changes.

v0.0.20.118 — DevicePanel UX (Batch Collapse / Expand Actions)
- Header-Aktionen für schnelle Übersicht in langen Chains:
  * Alle ausklappen
  * Inaktive einklappen (deaktivierte Devices)
- UI-only, keine Änderungen an DnD/Reorder/Audio/Projektmodell.

v0.0.20.116 — DevicePanel UX (Collapsible Device-Cards / Kompaktmodus)
- Device-Cards (Note-FX / Instrument / Audio-FX) können pro Card ein-/ausgeklappt werden (UI-only).
- Zustand wird nur UI-seitig pro Card/Track gehalten (keine Projekt-/Audio-Änderung).
- DnD/Reorder/Insert-Indizes bleiben unverändert, da nur inneres Widget sichtbar/unsichtbar geschaltet wird.

v0.0.20.114 — DevicePanel UX (Subtile Zonen-Hintergründe)
- Optionale halbtransparente Hintergrundflächen für Note-FX / Instrument / Audio-FX (rein visuell).
- Umsetzung weiterhin als Overlay im chain_host (DnD-/Reorder-Indizes bleiben stabil).

v0.0.20.113 — DevicePanel UX (Visuelle Gruppierung Note-FX | Instrument | Audio-FX)
- Device-Chain zeigt jetzt Gruppen-Badges + Divider für Note-FX / Instrument / Audio-FX.
- Rein visuell (Overlay in chain_host), ohne DnD-/Reorder-Indizes zu verändern.

v0.0.20.109 — DevicePanel UX (Visible Scrollbar + Card Focus)
- Horizontal scrollbar styled for better visibility in dark theme.
- Clicking / changing FX keeps a visual card selection (highlight).
- Newly added/reordered FX is auto-scrolled into view (no more lost device in long chains).

v0.0.20.108 — DevicePanel UX (Horizontal Scroll + no card squeezing)
- Device-Chain uses real horizontal scrolling when many devices are loaded.
- Cards keep their preferred width (instrument/FX UIs stay readable instead of being squashed).
- Chain host size is synced to content width so scrollbar appears reliably.

v0.0.20.81 — Device-Drop "Insert at position"
- Dropping Note-FX / Audio-FX now inserts at the cursor position instead of always appending.
- A vertical drop indicator (cyan line) shows the insertion gap between device cards during drag.
- Indicator follows cursor in real-time, snapping between card boundaries (center-based detection).
- add_note_fx_to_track / add_audio_fx_to_track accept optional `insert_index` keyword argument.
- DragLeave cleans up the indicator. Drop captures the calculated position before hiding.

v0.0.20.80 — Instrument Power/Bypass
- Instrument anchor cards now have a working Power button (toggle on/off).
- When bypassed: no MIDI dispatch, no SF2 render, no pull-source audio.
- Track stays visible; FX chain stays intact.
- State persists in Track.instrument_enabled (saved with project).

v0.0.20.65 — Device Chain MVP + Hotfixes (Ableton/Bitwig UX)
- Browser entries are templates; adding creates a NEW instance in the chain.
- Chain order is strict:
    [Note-FX] -> [Instrument (Anchor, fixed)] -> [Audio-FX]
- Drag&Drop is bulletproof: a DropForwardHost + event-filter forwards drops from child widgets.
- Per Device-Card: Up/Down + Power (enable/disable) + Remove.
- AudioEngine.rebuild_fx_maps() is called after Audio-FX add/remove/reorder/enable/disable.
- All Qt slots are wrapped in try/except to avoid fatal Qt crashes (SIGABRT) on exceptions.

v0.0.20.64 Hotfix:
- Legacy playback: fix beats_to_samples signature mismatch (no more "takes 1 positional arg but 3 were given").
- SF2 instrument anchor: show a minimal SF2 UI instead of "Instrument failed to load".

v0.0.20.65 Hotfix:
- Pro Sampler / Pro Drum Machine: target sample-rate is derived from AudioEngine settings
  (no more silent output when the user runs 44.1k instead of 48k).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

# NOTE (v0.0.20.191):
# PyQt/SIP kann *hart* segfaulten, wenn Python-Callbacks (z.B. QTimer.singleShot)
# auf bereits gelöschte Qt-Wrapper zugreifen. Seit v0.0.20.190 räumen wir Cards
# via deleteLater() weg (statt setParent(None) → "Zombie" Fenster). Dabei können
# noch "0ms"-Callbacks im Eventloop stehen (scroll into view, title elide, etc.).
# Wir müssen daher überall defensiv prüfen, ob ein QObject bereits deleted ist.

import weakref


def _qt_is_deleted(obj: Any) -> bool:
    """Best-effort check whether a PyQt wrapper's underlying QObject is deleted."""
    if obj is None:
        return True
    try:
        # PyQt6 ships sip module as PyQt6.sip
        from PySide6 import sip  # type: ignore
        return bool(sip.isdeleted(obj))
    except Exception:
        try:
            import sip  # type: ignore
            return bool(sip.isdeleted(obj))
        except Exception:
            return False

from PySide6.QtCore import Qt, QObject, QEvent, QSize, QTimer
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QToolButton,
    QSpinBox,
    QFileDialog,
    QLayout,
    QMenu,
)

from pydaw.model.project import new_id
from pydaw.plugins.registry import get_instruments

from .chrono_icons import icon as chrono_icon
from .fx_device_widgets import make_audio_fx_widget, make_note_fx_widget


_MIME = "application/x-pydaw-plugin"


def _parse_payload(event) -> Optional[dict]:  # noqa: ANN001
    try:
        md = event.mimeData()
        if md is None or not md.hasFormat(_MIME):
            return None
        raw = bytes(md.data(_MIME))
        payload = json.loads(raw.decode("utf-8", "ignore"))
        if not isinstance(payload, dict):
            return None
        return payload
    except Exception:
        return None


def _find_track(project_obj: Any, track_id: str):
    try:
        for t in getattr(project_obj, "tracks", []) or []:
            if str(getattr(t, "id", "")) == str(track_id):
                return t
    except Exception:
        pass
    return None


class _DropForwardFilter(QObject):
    """Forwards drag/drop events from arbitrary child widgets to the DevicePanel."""
    def __init__(self, panel: "DevicePanel"):
        super().__init__(panel)
        self._panel = panel
    def _zone_focus_target_kind(self) -> Optional[str]:
        mode = str(getattr(self, "_batch_action_mode", "") or "")
        if mode == "zone:note_fx":
            return "note_fx"
        if mode == "zone:instrument":
            return "instrument"
        if mode == "zone:audio_fx":
            return "audio_fx"
        return None

    def _zone_focus_is_active(self) -> bool:
        return self._zone_focus_target_kind() is not None

    def _batch_legend_lines(self) -> List[str]:
        mode = str(getattr(self, "_batch_action_mode", "") or "")
        mode_map = {
            "": "NORMAL",
            "focus_card": "FOKUS ◎",
            "zone:note_fx": "ZONE N",
            "zone:instrument": "ZONE I",
            "zone:audio_fx": "ZONE A",
            "collapsed_all": "ALLE ZU",
            "expanded_all": "ALLE AUF",
            "collapsed_inactive": "INAKTIV ZU",
        }
        return [
            f"Status: {mode_map.get(mode, 'NORMAL')} (UI-only)",
            "",
            "◪  Inaktive Devices einklappen",
            "▾▾  Alle Device-Cards einklappen",
            "▸▸  Alle Device-Cards ausklappen",
            "◎  Fokusansicht (nur fokussierte Card offen)",
            "N   Nur NOTE-FX offen",
            "I   Nur INSTRUMENT offen",
            "A   Nur AUDIO-FX offen",
            "↺   Reset / Normalansicht",
            "?   Diese Kurzhilfe",
            "",
            "Esc  Reset (wie ↺)",
            "Doppelklick auf Card = Ein/Ausklappen",
            "▾/▸ im Card-Header = Ein/Ausklappen",
            "Hinweis: N/I/A/◎/↺/? sind Header-Buttons, keine globalen Kürzel.",
        ]

    def _show_batch_legend_popup(self) -> None:
        """Kompakte UI-Legende direkt im DevicePanel-Header (Popover via QMenu)."""
        try:
            btn = getattr(self, "_btn_batch_help", None)
            if btn is None:
                return
            menu = QMenu(self)
            try:
                menu.setObjectName("devicePanelBatchLegendMenu")
                menu.setStyleSheet(
                    "QMenu#devicePanelBatchLegendMenu { background:#23262e; color:#dde4f5; border:1px solid rgba(255,255,255,0.10); }"
                    "QMenu#devicePanelBatchLegendMenu::item { padding: 4px 12px; }"
                    "QMenu#devicePanelBatchLegendMenu::item:selected { background: rgba(129,163,255,0.16); }"
                )
            except Exception:
                pass
            try:
                menu.addSection("DevicePanel • Kurzhilfe")
            except Exception:
                pass
            for line in self._batch_legend_lines():
                if line == "":
                    try:
                        menu.addSeparator()
                    except Exception:
                        pass
                    continue
                act = menu.addAction(line)
                try:
                    act.setEnabled(False)
                except Exception:
                    pass
            try:
                menu.addSeparator()
                a = menu.addAction("OK")
                a.setEnabled(True)
            except Exception:
                pass
            pos = btn.mapToGlobal(btn.rect().bottomLeft())
            menu.exec(pos)
        except Exception:
            pass

    def _is_exclusive_target(self, obj) -> bool:  # noqa: ANN001
        """Return True if a widget wants to handle plugin drops itself.

        Some instrument UIs contain their own internal racks (e.g. per-slot FX).
        The DevicePanel installs this filter on ALL children to make DnD robust,
        but that would hijack drops from those internal racks. This opt-out keeps
        behavior Bitwig-like without touching audio/core logic.
        """
        try:
            from PySide6.QtWidgets import QWidget
            w = obj if isinstance(obj, QWidget) else None
            while w is not None:
                try:
                    if bool(w.property("pydaw_exclusive_drop_target")):
                        return True
                except Exception:
                    pass
                try:
                    w = w.parentWidget()
                except Exception:
                    break
        except Exception:
            pass
        return False

    def eventFilter(self, obj, event):  # noqa: N802, ANN001
        try:
            # Let internal instrument racks handle drops themselves (e.g. Slot-FX racks)
            if self._is_exclusive_target(obj):
                return False
            t = event.type()
            if t == QEvent.Type.DragLeave:
                try:
                    self._panel._hide_drop_indicator()
                except Exception:
                    pass
                return False
            if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
                # Only handle our custom plugin mime.
                payload = _parse_payload(event)
                if payload and payload.get("kind") in ("instrument", "note_fx", "audio_fx"):
                    return self._panel._forward_drag_event(event)
        except Exception:
            return False
        return False


class _DropIndicator(QFrame):
    """Thin vertical line shown between device cards during drag to indicate insertion position."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(3)
        self.setMinimumHeight(40)
        self.setStyleSheet("background-color: #4fc3f7; border-radius: 1px;")
        self.hide()


class _DropForwardHost(QWidget):
    """Host widget inside the scroll area. Receives drops and forwards them."""
    def __init__(self, panel: "DevicePanel", parent=None):
        super().__init__(parent)
        self._panel = panel
        try:
            self.setAcceptDrops(True)
        except Exception:
            pass

    def dragEnterEvent(self, event):  # noqa: N802, ANN001
        self._panel._forward_drag_event(event)

    def dragMoveEvent(self, event):  # noqa: N802, ANN001
        self._panel._forward_drag_event(event)

    def dropEvent(self, event):  # noqa: N802, ANN001
        self._panel._forward_drag_event(event)

    def dragLeaveEvent(self, event):  # noqa: N802, ANN001
        try:
            self._panel._hide_drop_indicator()
        except Exception:
            pass

    # v0.0.20.531: Right-click on empty chain area → add Container/FX menu
    def contextMenuEvent(self, event):  # noqa: N802, ANN001
        try:
            self._panel._show_chain_context_menu(event.globalPos())
        except Exception:
            pass


class _ToolBtn(QToolButton):
    def __init__(self, icon_name: str, tooltip: str, parent=None, *, checkable: bool = False):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setToolTip(tooltip)
        self.setIcon(chrono_icon(icon_name, 16))
        self.setIconSize(QSize(16, 16))
        self.setCheckable(bool(checkable))
        self.setFixedSize(QSize(22, 22))


_INTERNAL_MIME = "application/x-pydaw-fx-reorder"


class _DeviceCard(QFrame):
    """A single device card with controls + inner widget.
    v107: Reduced minWidth, drag handle for reorder, better styling.
    v116: Collapsible inner UI (Kompaktmodus, UI-only)."""
    def __init__(
        self,
        title: str,
        inner: QWidget,
        *,
        enabled: bool = True,
        can_up: bool = False,
        can_down: bool = False,
        on_up=None,
        on_down=None,
        on_power=None,
        on_remove=None,
        on_focus=None,
        on_toggle_collapse=None,
        collapsed: bool = False,
        collapsible: bool = True,
        device_id: str = "",
        fx_kind: str = "",
        plugin_type_id: str = "",
        plugin_name: str = "",
        source_track_id: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.device_id = device_id
        self.fx_kind = fx_kind  # "audio_fx" or "note_fx" or "instrument" for drag
        self.plugin_type_id = str(plugin_type_id or "")  # v516: cross-track drag
        self.plugin_name = str(plugin_name or "")  # v516: cross-track drag
        self.source_track_id = str(source_track_id or "")  # v516: cross-track drag
        self._on_focus_cb = on_focus
        self._on_toggle_collapse_cb = on_toggle_collapse
        # separate from drag metadata: collapse state also exists for instrument anchor
        self._collapse_state_kind = str(fx_kind or "")
        self._collapse_state_device_id = str(device_id or "")
        self._ui_enabled = bool(enabled)
        self._ui_selected = False
        self._ui_collapsed = False
        self._expanded_min_width: Optional[int] = None
        self._expanded_max_width: Optional[int] = None
        self._collapsed_fixed_width: Optional[int] = None
        self.setObjectName("deviceCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        try:
            _hint_w = int(inner.sizeHint().width()) if inner is not None else 0
        except Exception:
            _hint_w = 0
        _card_min_w = max(220, min(640, (_hint_w + 28) if _hint_w > 0 else 240))
        self.setMinimumWidth(_card_min_w)
        self.setMaximumWidth(900)
        try:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        except Exception:
            pass

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 6)
        outer.setSpacing(4)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(2)

        self._btn_collapse = QToolButton(self)
        self._btn_collapse.setAutoRaise(True)
        self._btn_collapse.setToolTip("Expand/Collapse device UI")
        self._btn_collapse.setFixedSize(QSize(20, 20))
        self._btn_collapse.setStyleSheet("QToolButton{padding:0px; margin:0px;} ")
        try:
            self._btn_collapse.clicked.connect(self._toggle_collapsed)
        except Exception:
            pass
        self._btn_collapse.setVisible(bool(collapsible))
        self._btn_collapse.setEnabled(bool(collapsible))

        self._full_title = str(title or "")
        self.lab = QLabel(self._full_title)
        self.lab.setObjectName("deviceCardTitle")
        self.lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.lab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lab.setMinimumWidth(0)
        self.lab.setStyleSheet("font-size:11px; font-weight:bold; padding-right:2px;")

        btn_up = _ToolBtn("up", "Move Left  (Ctrl+←)", self)
        btn_dn = _ToolBtn("down", "Move Right (Ctrl+→)", self)
        btn_pw = _ToolBtn("power", "Enable/Disable", self, checkable=True)
        btn_rm = _ToolBtn("close", "Remove device", self)
        self._btn_up = btn_up
        self._btn_dn = btn_dn
        self._btn_pw = btn_pw
        self._btn_rm = btn_rm

        btn_up.setEnabled(bool(can_up) and callable(on_up))
        btn_dn.setEnabled(bool(can_down) and callable(on_down))
        btn_pw.setEnabled(callable(on_power))
        btn_rm.setEnabled(callable(on_remove))

        if callable(on_up):
            btn_up.clicked.connect(lambda _=False: on_up())
        if callable(on_down):
            btn_dn.clicked.connect(lambda _=False: on_down())
        if callable(on_power):
            btn_pw.clicked.connect(lambda _=False: on_power(btn_pw.isChecked()))
        if callable(on_remove):
            btn_rm.clicked.connect(lambda _=False: on_remove())

        btn_pw.setChecked(bool(enabled))

        top.addWidget(self._btn_collapse, 0)
        top.addWidget(self.lab, 1)
        top.addWidget(btn_up, 0)
        top.addWidget(btn_dn, 0)
        top.addWidget(btn_pw, 0)
        top.addWidget(btn_rm, 0)

        outer.addLayout(top)
        self.inner_widget = inner
        outer.addWidget(inner, 1)
        # v0.0.20.545: Inner widget gets ArrowCursor (card uses OpenHandCursor for drag)
        try:
            inner.setCursor(Qt.CursorShape.ArrowCursor)
        except Exception:
            pass

        self.set_enabled_visual(bool(enabled))
        self.set_collapsed(bool(collapsed), notify=False)
        try:
            QTimer.singleShot(0, self._update_title_elide)
        except Exception:
            pass

    def _title_buttons(self):
        return [
            getattr(self, "_btn_collapse", None),
            getattr(self, "_btn_up", None),
            getattr(self, "_btn_dn", None),
            getattr(self, "_btn_pw", None),
            getattr(self, "_btn_rm", None),
        ]

    def _capture_expanded_width_bounds(self) -> None:
        try:
            if bool(getattr(self, "_ui_collapsed", False)):
                return
            self._expanded_min_width = max(0, int(QFrame.minimumWidth(self)))
            self._expanded_max_width = max(0, int(QFrame.maximumWidth(self)))
        except Exception:
            pass

    def _compute_collapsed_width(self) -> int:
        """Stable compact width for collapsed cards.

        Do not derive the value from the *current* header width. The title label expands
        with the card and can otherwise keep the collapsed card nearly full-width.
        """
        try:
            try:
                fm = QFontMetrics(self.lab.font()) if getattr(self, "lab", None) is not None else None
                title = str(getattr(self, "_full_title", "") or "")
                title_w = int(fm.horizontalAdvance(title)) if (fm is not None and title) else 0
            except Exception:
                title_w = 0
            # Hard cap for compact mode so long titles do not dominate width.
            title_w = max(48, min(108, int(title_w) + 8))

            btn_w = 0
            visible_btns = 0
            for btn in self._title_buttons():
                if btn is None or not btn.isVisible():
                    continue
                visible_btns += 1
                try:
                    btn_w += int(max(btn.minimumSizeHint().width(), btn.sizeHint().width(), btn.width(), 20))
                except Exception:
                    btn_w += 22

            try:
                outer_layout = self.layout()
                if outer_layout is not None:
                    m = outer_layout.contentsMargins()
                    outer_pad = int(m.left()) + int(m.right())
                else:
                    outer_pad = 0
            except Exception:
                outer_pad = 0

            spacing = 2 * max(0, visible_btns - 1)
            frame_pad = int(max(0, self.frameWidth()) * 2)
            w = int(frame_pad + outer_pad + btn_w + spacing + title_w + 10)
            return max(112, min(196, w))
        except Exception:
            return 140

    def setMinimumWidth(self, minw: int) -> None:  # noqa: N802
        try:
            self._expanded_min_width = int(minw)
        except Exception:
            pass
        if bool(getattr(self, "_ui_collapsed", False)):
            try:
                w = int(getattr(self, "_collapsed_fixed_width", 0) or self._compute_collapsed_width())
                self._collapsed_fixed_width = w
                return QFrame.setMinimumWidth(self, w)
            except Exception:
                pass
        return QFrame.setMinimumWidth(self, int(minw))

    def setMaximumWidth(self, maxw: int) -> None:  # noqa: N802
        try:
            self._expanded_max_width = int(maxw)
        except Exception:
            pass
        if bool(getattr(self, "_ui_collapsed", False)):
            try:
                w = int(getattr(self, "_collapsed_fixed_width", 0) or self._compute_collapsed_width())
                self._collapsed_fixed_width = w
                return QFrame.setMaximumWidth(self, w)
            except Exception:
                pass
        return QFrame.setMaximumWidth(self, int(maxw))

    def _update_title_elide(self) -> None:
        # v0.0.20.191: defensive guard (pending singleShot after card removal)
        if _qt_is_deleted(self):
            return
        try:
            lab = getattr(self, "lab", None)
            if lab is None:
                return
            full = str(getattr(self, "_full_title", "") or "")
            if not full:
                lab.setText("")
                lab.setToolTip("")
                return
            avail = int(lab.width())
            if avail <= 8:
                avail = max(48, int(self.width()) - 120)
            fm = QFontMetrics(lab.font())
            txt = fm.elidedText(full, Qt.TextElideMode.ElideRight, max(48, avail))
            lab.setText(txt)
            lab.setToolTip(full if txt != full else "")
        except Exception:
            pass

    def _apply_card_style(self) -> None:
        try:
            selected = bool(getattr(self, "_ui_selected", False))
            enabled = bool(getattr(self, "_ui_enabled", True))
            if enabled:
                title_css = "font-size:11px; font-weight:bold; padding-right:2px;"
            else:
                title_css = "font-size:11px; font-weight:bold; color:#7a7a7a; padding-right:2px;"
            if selected and enabled:
                frame_css = (
                    "background-color: rgba(65, 205, 82, 0.06);"
                    "border:1px solid rgba(65, 205, 82, 0.75);"
                    "border-radius:4px;"
                )
                title_css += " color:#e8fbe8;"
            elif selected and not enabled:
                frame_css = (
                    "background-color: rgba(120,120,120,0.06);"
                    "border:1px solid rgba(150,150,150,0.45);"
                    "border-radius:4px;"
                )
            elif not enabled:
                frame_css = "background-color: rgba(255,255,255,0.02); border-radius:4px;"
            else:
                frame_css = ""
            self.lab.setStyleSheet(title_css)
            self.setStyleSheet(frame_css)
            self._update_title_elide()
        except Exception:
            pass

    def set_enabled_visual(self, enabled: bool) -> None:
        self._ui_enabled = bool(enabled)
        self._apply_card_style()

    def set_selected_visual(self, selected: bool) -> None:
        self._ui_selected = bool(selected)
        self._apply_card_style()

    def _update_collapse_button(self) -> None:
        try:
            if getattr(self, "_btn_collapse", None) is None or not self._btn_collapse.isVisible():
                return
            self._btn_collapse.setText("▸" if self._ui_collapsed else "▾")
            self._btn_collapse.setToolTip("Expand device UI" if self._ui_collapsed else "Collapse device UI")
        except Exception:
            pass

    def _toggle_collapsed(self) -> None:
        try:
            self.set_collapsed(not bool(getattr(self, "_ui_collapsed", False)), notify=True)
        except Exception:
            pass

    def set_collapsed(self, collapsed: bool, *, notify: bool = False) -> None:
        prev = bool(getattr(self, "_ui_collapsed", False))
        target = bool(collapsed)
        if (not prev) and target:
            try:
                self._capture_expanded_width_bounds()
            except Exception:
                pass
        self._ui_collapsed = target
        try:
            if getattr(self, "inner_widget", None) is not None:
                self.inner_widget.setVisible(not self._ui_collapsed)
        except Exception:
            pass
        try:
            if self._ui_collapsed:
                w = int(self._compute_collapsed_width())
                self._collapsed_fixed_width = w
                QFrame.setMinimumWidth(self, w)
                QFrame.setMaximumWidth(self, w)
                self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            else:
                mn = int(getattr(self, "_expanded_min_width", 0) or 0)
                mx = int(getattr(self, "_expanded_max_width", 900) or 900)
                QFrame.setMinimumWidth(self, mn)
                QFrame.setMaximumWidth(self, mx)
                self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        except Exception:
            pass
        try:
            self._update_collapse_button()
        except Exception:
            pass
        try:
            if bool(self._ui_collapsed):
                self.lab.setMaximumWidth(112)
                self.lab.setMinimumWidth(28)
                self.lab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            else:
                self.lab.setMaximumWidth(16777215)
                self.lab.setMinimumWidth(0)
                self.lab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        try:
            self._update_title_elide()
        except Exception:
            pass
        try:
            self.updateGeometry()
            if self.parentWidget() is not None:
                self.parentWidget().updateGeometry()
        except Exception:
            pass
        if notify:
            try:
                cb = getattr(self, "_on_toggle_collapse_cb", None)
                if callable(cb):
                    cb(bool(self._ui_collapsed))
            except Exception:
                pass

    def is_collapsed(self) -> bool:
        return bool(getattr(self, "_ui_collapsed", False))

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        finally:
            try:
                self._update_title_elide()
            except Exception:
                pass

    # ---- v0.0.20.709: P6C Pro-Plugin Sandbox Override context menu ----
    def contextMenuEvent(self, event):  # noqa: N802, ANN001
        """Right-click on a device card → sandbox override options for external plugins."""
        try:
            ptid = str(self.plugin_type_id or "")
            # Only show sandbox options for external plugins (ext.vst3, ext.vst2, ext.clap, ext.lv2, ext.ladspa)
            if not ptid.startswith("ext."):
                # For built-in plugins, delegate to chain context menu if panel exists
                try:
                    panel = self.parent()
                    while panel is not None and not isinstance(panel, DevicePanel):
                        panel = panel.parent()
                    if panel is not None and hasattr(panel, "_show_chain_context_menu"):
                        panel._show_chain_context_menu(event.globalPos())
                except Exception:
                    pass
                return

            # Determine plugin_type and plugin_path from the plugin_type_id
            plugin_type = ""
            plugin_path = ""
            if ptid.startswith("ext.vst3:"):
                plugin_type = "vst3"
                plugin_path = ptid.split(":", 1)[1] if ":" in ptid else ""
            elif ptid.startswith("ext.vst2:"):
                plugin_type = "vst2"
                plugin_path = ptid.split(":", 1)[1] if ":" in ptid else ""
            elif ptid.startswith("ext.clap:"):
                plugin_type = "clap"
                plugin_path = ptid.split(":", 1)[1] if ":" in ptid else ""
            elif ptid.startswith("ext.lv2:"):
                plugin_type = "lv2"
                plugin_path = ptid.split(":", 1)[1] if ":" in ptid else ""
            elif ptid.startswith("ext.ladspa:"):
                plugin_type = "ladspa"
                plugin_path = ptid.split(":", 1)[1] if ":" in ptid else ""
            else:
                return

            from pydaw.services.sandbox_overrides import (
                get_override, set_override,
                OVERRIDE_DEFAULT, OVERRIDE_SANDBOX, OVERRIDE_INPROCESS,
            )

            current = get_override(plugin_type, plugin_path)
            pname = str(self.plugin_name or plugin_path.rsplit("/", 1)[-1])

            menu = QMenu(self)
            menu.setStyleSheet("QMenu { font-size: 11px; }")

            lbl = menu.addAction(f"🔌 {pname}")
            lbl.setEnabled(False)
            menu.addSeparator()

            a_default = menu.addAction("⚙ Global-Einstellung verwenden")
            a_default.setCheckable(True)
            a_default.setChecked(current == OVERRIDE_DEFAULT)

            a_sandbox = menu.addAction("🛡️ Immer in Sandbox laden")
            a_sandbox.setCheckable(True)
            a_sandbox.setChecked(current == OVERRIDE_SANDBOX)

            a_inprocess = menu.addAction("⚡ Ohne Sandbox laden (in-process)")
            a_inprocess.setCheckable(True)
            a_inprocess.setChecked(current == OVERRIDE_INPROCESS)

            menu.addSeparator()
            a_info = menu.addAction(f"Typ: {plugin_type.upper()}")
            a_info.setEnabled(False)

            chosen = menu.exec(event.globalPos())
            if chosen is None:
                return

            new_mode = OVERRIDE_DEFAULT
            if chosen == a_sandbox:
                new_mode = OVERRIDE_SANDBOX
            elif chosen == a_inprocess:
                new_mode = OVERRIDE_INPROCESS
            elif chosen == a_default:
                new_mode = OVERRIDE_DEFAULT

            if new_mode != current:
                set_override(plugin_type, plugin_path, new_mode, plugin_name=pname)

        except Exception:
            pass

    # ---- Drag support for reordering within chain ----
    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                try:
                    if callable(getattr(self, "_on_focus_cb", None)):
                        self._on_focus_cb()
                except Exception:
                    pass
                self._drag_start_pos = event.pos()
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton and getattr(self, "_btn_collapse", None) is not None and self._btn_collapse.isVisible():
                self._toggle_collapsed()
                event.accept()
                return
        except Exception:
            pass
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        try:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                return super().mouseMoveEvent(event)
            if not hasattr(self, '_drag_start_pos'):
                return super().mouseMoveEvent(event)
            if (event.pos() - self._drag_start_pos).manhattanLength() < 20:
                return super().mouseMoveEvent(event)
            if not self.device_id or not self.fx_kind:
                return super().mouseMoveEvent(event)
            # Start internal drag for reorder / cross-track move (v516)
            from PySide6.QtCore import QMimeData
            from PySide6.QtGui import QDrag
            drag = QDrag(self)
            mime = QMimeData()
            payload = json.dumps({
                "kind": self.fx_kind,
                "device_id": self.device_id,
                "plugin_id": self.plugin_type_id or self.device_id,
                "name": self.plugin_name or self.fx_kind or "Device",
                "source_track_id": self.source_track_id,
                "reorder": True,
            })
            mime.setData(_INTERNAL_MIME, payload.encode("utf-8"))
            # Also set the standard plugin mime so Arranger/TrackList accept cross-track drops
            mime.setData(_MIME, payload.encode("utf-8"))
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
        except Exception:
            pass


class _Sf2InstrumentWidget(QWidget):
    """Minimal SF2 anchor UI.

    Wichtig: SF2 ist (noch) kein Qt-Instrument-Plugin in der Registry,
    aber wird von der Engine über Offline-Render (FluidSynth) unterstützt.
    Track.plugin_type == "sf2" ist daher ein valider Instrument-Anker.
    """

    def __init__(self, panel: "DevicePanel", track_id: str, *, sf2_path: str = "", bank: int = 0, preset: int = 0, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._track_id = str(track_id or "")

        self._path = str(sf2_path or "")
        self._apply_pending = False  # avoid UI rebuild during spinbox events

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(6)

        self._path_lab = QLabel()
        self._path_lab.setWordWrap(True)
        self._path_lab.setStyleSheet("color:#bdbdbd;")

        self._btn_load = _ToolBtn("plus", "Load SF2 (SoundFont)", self)
        self._btn_load.clicked.connect(self._on_load)

        row.addWidget(self._path_lab, 1)
        row.addWidget(self._btn_load, 0)
        root.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(10)

        lab_bank = QLabel("Bank")
        lab_bank.setStyleSheet("color:#9a9a9a;")
        self._bank = QSpinBox()
        self._bank.setRange(0, 127)
        self._bank.setValue(int(bank) if bank is not None else 0)
        self._bank.valueChanged.connect(self._on_bank_preset)

        lab_preset = QLabel("Preset")
        lab_preset.setStyleSheet("color:#9a9a9a;")
        self._preset = QSpinBox()
        self._preset.setRange(0, 127)
        self._preset.setValue(int(preset) if preset is not None else 0)
        self._preset.valueChanged.connect(self._on_bank_preset)

        row2.addWidget(lab_bank)
        row2.addWidget(self._bank)
        row2.addSpacing(8)
        row2.addWidget(lab_preset)
        row2.addWidget(self._preset)
        row2.addStretch(1)

        root.addLayout(row2)

        hint = QLabel("SF2 SoundFont — Live-MIDI + Playback. MIDI-Keyboard spielt sofort.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#7f7f7f; font-size:11px;")
        root.addWidget(hint)

        self._refresh_label()

    def _refresh_label(self) -> None:
        try:
            if self._path:
                name = os.path.basename(self._path)
                self._path_lab.setText(f"SF2: {name}")
            else:
                self._path_lab.setText("No SF2 loaded. Click + to load a SoundFont.")
        except Exception:
            pass

    def _on_load(self) -> None:
        try:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "SoundFont (SF2) auswählen",
                "",
                "SoundFont (*.sf2);;Alle Dateien (*)",
            )
            if not path:
                return
            self._path = str(path)
            self._schedule_apply_sf2()
        except Exception:
            return

    def _schedule_apply_sf2(self) -> None:
        """Defer SF2 apply to next event-loop tick.

        Hintergrund: set_track_soundfont() emittiert project_updated, was das DevicePanel
        neu rendert. Wenn das während eines QSpinBox-Mouse-Events passiert (Bank/Preset),
        kann Qt den SpinBox-Widget-Zustand invalidieren -> SIGSEGV in QAbstractSpinBox::stepBy.
        """
        try:
            if getattr(self, "_apply_pending", False):
                return
            self._apply_pending = True
            QTimer.singleShot(0, self._apply_sf2_deferred)
        except Exception:
            try:
                self._apply_pending = False
            except Exception:
                pass
            try:
                self._apply_sf2()
            except Exception:
                pass

    def _apply_sf2_deferred(self) -> None:
        # v0.0.20.191: avoid segfault if widget was deleted between schedule/apply.
        if _qt_is_deleted(self):
            return
        try:
            self._apply_pending = False
            # if no file selected, just refresh label (do not touch project)
            if not getattr(self, "_path", ""):
                try:
                    self._refresh_label()
                except Exception:
                    pass
                return
            self._apply_sf2()
        except RuntimeError:
            # Qt wrapper deleted (track switched / panel rerendered)
            return
        except Exception:
            try:
                self._apply_pending = False
            except Exception:
                pass
            return

    def _on_bank_preset(self, _=None) -> None:
        # allow setting bank/preset before picking a file
        if not self._path:
            try:
                self._refresh_label()
            except Exception:
                pass
            return
        self._schedule_apply_sf2()

    def _apply_sf2(self) -> None:
        """Write SF2 settings into track model + emit updates."""
        if not self._track_id:
            return
        try:
            proj, project_obj, trk = self._panel._get_project_track(self._track_id)
            if trk is None:
                return

            # Ensure routing mode
            try:
                trk.plugin_type = "sf2"
            except Exception:
                pass

            try:
                trk.sf2_path = str(self._path)
                trk.sf2_bank = int(self._bank.value())
                trk.sf2_preset = int(self._preset.value())
            except Exception:
                pass

            # Prefer service API (emits status/project_updated)
            try:
                if proj is not None and hasattr(proj, "set_track_soundfont"):
                    proj.set_track_soundfont(self._track_id, str(self._path), bank=int(self._bank.value()), preset=int(self._preset.value()))
            except Exception:
                pass

            self._refresh_label()
            self._panel._restart_if_playing()
        except Exception:
            return


class DevicePanel(QWidget):
    """Bottom device view — per-track strict device chain."""

    def __init__(self, services=None, parent=None):
        super().__init__(parent)
        self.setObjectName("devicePanel")
        self._services = services

        # Hidden stash parent for widgets that must temporarily leave layouts.
        # IMPORTANT: calling setParent(None) on a visible widget turns it into a
        # top-level window ("zombie" duplicates). We therefore reparent to this
        # invisible stash instead (and optionally deleteLater).
        try:
            self._widget_stash = QWidget(self)
            self._widget_stash.setObjectName("chronoWidgetStash")
            self._widget_stash.setVisible(False)
            self._widget_stash.setFixedSize(0, 0)
        except Exception:
            self._widget_stash = None

        self._current_track: str = ""
        self._selected_fx_kind: str = ""
        self._selected_fx_device_id: str = ""
        self._pending_focus_kind: str = ""
        self._pending_focus_device_id: str = ""
        self._rendered_fx_cards: Dict[Tuple[str, str], QWidget] = {}
        self._zone_badges: Dict[str, QLabel] = {}
        self._zone_dividers: Dict[str, QFrame] = {}
        self._zone_backdrops: Dict[str, QFrame] = {}
        self._zone_layout_meta: Dict[str, Any] = {}
        self._card_collapse_state: Dict[str, bool] = {}
        self._batch_action_mode: str = ""
        self._batch_hover_hints: Dict[QObject, str] = {}

        # v0.0.20.554: Bitwig-style container zoom navigation
        # Stack of dicts: [{"type": "layer", "track_id": ..., "device_id": ...,
        #                    "layer_index": ..., "layer_name": ...}, ...]
        self._nav_stack: list = []


        # Keep instrument widgets alive per track (state preservation).
        self._track_instruments: Dict[str, dict] = {}  # track_id -> {plugin_id, widget}

        self._drop_filter = _DropForwardFilter(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)

        title = QLabel("Device")
        title.setObjectName("devicePanelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._btn_collapse_inactive = QToolButton(self)
        self._btn_collapse_inactive.setText("◪")
        self._btn_collapse_inactive.setToolTip("Inaktive einklappen (deaktivierte Devices, UI-only)")
        self._btn_collapse_inactive.setAutoRaise(True)
        self._btn_collapse_inactive.setFixedSize(QSize(24, 24))
        try:
            self._btn_collapse_inactive.clicked.connect(self._collapse_inactive_device_cards)
        except Exception:
            pass

        self._btn_collapse_all = QToolButton(self)
        self._btn_collapse_all.setText("▾▾")
        self._btn_collapse_all.setToolTip("Alle Device-Cards einklappen (UI-only)")
        self._btn_collapse_all.setAutoRaise(True)
        self._btn_collapse_all.setFixedSize(QSize(28, 24))
        try:
            self._btn_collapse_all.clicked.connect(self._collapse_all_device_cards)
        except Exception:
            pass

        self._btn_expand_all = QToolButton(self)
        self._btn_expand_all.setText("▸▸")
        self._btn_expand_all.setToolTip("Alle Device-Cards ausklappen (UI-only)")
        self._btn_expand_all.setAutoRaise(True)
        self._btn_expand_all.setFixedSize(QSize(28, 24))
        try:
            self._btn_expand_all.clicked.connect(self._expand_all_device_cards)
        except Exception:
            pass

        self._btn_focus_only = QToolButton(self)
        self._btn_focus_only.setText("◎")
        self._btn_focus_only.setToolTip("Fokusansicht: nur fokussierte Card offen lassen (Fallback: Instrument)")
        self._btn_focus_only.setAutoRaise(True)
        self._btn_focus_only.setFixedSize(QSize(24, 24))
        self._btn_focus_only.setCheckable(True)
        try:
            self._btn_focus_only.clicked.connect(self._collapse_focus_device_cards)
        except Exception:
            pass

        self._btn_focus_note_zone = QToolButton(self)
        self._btn_focus_note_zone.setText("N")
        self._btn_focus_note_zone.setToolTip("Nur NOTE-FX offen lassen (UI-only Zonenfokus)")
        self._btn_focus_note_zone.setAutoRaise(True)
        self._btn_focus_note_zone.setFixedSize(QSize(22, 24))
        self._btn_focus_note_zone.setCheckable(True)
        try:
            self._btn_focus_note_zone.clicked.connect(lambda _=False: self._focus_only_zone_device_cards("note_fx"))
        except Exception:
            pass

        self._btn_focus_instrument_zone = QToolButton(self)
        self._btn_focus_instrument_zone.setText("I")
        self._btn_focus_instrument_zone.setToolTip("Nur INSTRUMENT offen lassen (UI-only Zonenfokus)")
        self._btn_focus_instrument_zone.setAutoRaise(True)
        self._btn_focus_instrument_zone.setFixedSize(QSize(22, 24))
        self._btn_focus_instrument_zone.setCheckable(True)
        try:
            self._btn_focus_instrument_zone.clicked.connect(lambda _=False: self._focus_only_zone_device_cards("instrument"))
        except Exception:
            pass

        self._btn_focus_audio_zone = QToolButton(self)
        self._btn_focus_audio_zone.setText("A")
        self._btn_focus_audio_zone.setToolTip("Nur AUDIO-FX offen lassen (UI-only Zonenfokus)")
        self._btn_focus_audio_zone.setAutoRaise(True)
        self._btn_focus_audio_zone.setFixedSize(QSize(22, 24))
        self._btn_focus_audio_zone.setCheckable(True)
        try:
            self._btn_focus_audio_zone.clicked.connect(lambda _=False: self._focus_only_zone_device_cards("audio_fx"))
        except Exception:
            pass

        self._btn_reset_view = QToolButton(self)
        self._btn_reset_view.setObjectName("deviceResetViewButton")
        self._btn_reset_view.setText("↺")
        self._btn_reset_view.setToolTip("↺ Reset: Alle Zonen normal / alle Device-Cards ausklappen (UI-only, Esc)")
        self._btn_reset_view.setAutoRaise(True)
        self._btn_reset_view.setFixedSize(QSize(24, 24))
        try:
            self._btn_reset_view.clicked.connect(self._reset_normal_device_view)
        except Exception:
            pass

        self._btn_batch_help = QToolButton(self)
        self._btn_batch_help.setObjectName("deviceBatchHelpButton")
        self._btn_batch_help.setText("?")
        self._btn_batch_help.setToolTip("Kurzhilfe: DevicePanel-Icons / Fokus / Collapse (UI-only)")
        self._btn_batch_help.setAutoRaise(True)
        self._btn_batch_help.setFixedSize(QSize(22, 24))
        try:
            self._btn_batch_help.clicked.connect(self._show_batch_legend_popup)
        except Exception:
            pass


        for _btn in (
            self._btn_collapse_inactive,
            self._btn_collapse_all,
            self._btn_expand_all,
            self._btn_focus_only,
            self._btn_focus_note_zone,
            self._btn_focus_instrument_zone,
            self._btn_focus_audio_zone,
            self._btn_reset_view,
            self._btn_batch_help,
        ):
            try:
                _btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _btn.setStyleSheet(
                    "QToolButton { color:#d7d7de; border:1px solid rgba(255,255,255,0.08); "
                    "border-radius:6px; background: rgba(255,255,255,0.02); padding:0px; }"
                    "QToolButton:hover { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.16); }"
                    "QToolButton:checked { color:#f2f5ff; background: rgba(129,163,255,0.14); border-color: rgba(129,163,255,0.42); }"
                    "QToolButton:disabled { color:#777; border-color: rgba(255,255,255,0.04); background: rgba(255,255,255,0.01); }"
                    "QToolButton#deviceResetViewButton { color:#dfe8ff; border-color: rgba(129,163,255,0.22); }"
                    "QToolButton#deviceResetViewButton:hover { background: rgba(129,163,255,0.08); border-color: rgba(129,163,255,0.34); }"
                    "QToolButton#deviceBatchHelpButton { color:#d7deef; border-color: rgba(255,255,255,0.14); }"
                    "QToolButton#deviceBatchHelpButton:hover { background: rgba(255,255,255,0.07); border-color: rgba(255,255,255,0.22); }"
                )
            except Exception:
                pass

        self._batch_mode_badge = QLabel("NORMAL", self)
        try:
            self._batch_mode_badge.setObjectName("deviceBatchModeBadge")
            self._batch_mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._batch_mode_badge.setMinimumWidth(62)
            self._batch_mode_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        self._batch_hint_label = QLabel(self._default_batch_hint_text(), self)
        try:
            self._batch_hint_label.setObjectName("deviceBatchHintLabel")
            self._batch_hint_label.setMinimumWidth(0)
            self._batch_hint_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self._batch_hint_label.setStyleSheet(
                "QLabel#deviceBatchHintLabel { color:#8c90a6; font-size: 11px; padding-left: 4px; }"
            )
            self._batch_hint_label.setToolTip(
                "Batch-Hinweis: Hover über Header-Buttons zeigt die Aktion. N/I/A = Zonenfokus (UI-only), ↺/Esc = Reset, ? = Kurzhilfe-Popup."
            )
        except Exception:
            pass

        self._batch_hover_hints = {
            self._btn_collapse_inactive: "◪ Inaktive einklappen (nur deaktivierte Devices, UI-only)",
            self._btn_collapse_all: "▾▾ Alle Device-Cards einklappen (UI-only)",
            self._btn_expand_all: "▸▸ Alle Device-Cards ausklappen (UI-only)",
            self._btn_focus_only: "◎ Fokusansicht: nur fokussierte Card offen (Fallback: Instrument)",
            self._btn_focus_note_zone: "N = Nur NOTE-FX offen (Zonenfokus, UI-only)",
            self._btn_focus_instrument_zone: "I = Nur INSTRUMENT offen (Zonenfokus, UI-only)",
            self._btn_focus_audio_zone: "A = Nur AUDIO-FX offen (Zonenfokus, UI-only)",
            self._btn_reset_view: "↺ Reset = Alle Zonen normal / alle Cards offen (UI-only, Esc)",
            self._btn_batch_help: "? Kurzhilfe: Legende/Bedienung für Header-Icons (UI-only)",
        }
        try:
            for _btn in self._batch_hover_hints.keys():
                _btn.installEventFilter(self)
        except Exception:
            pass
        try:
            if getattr(self, "_batch_mode_badge", None) is not None:
                self._batch_mode_badge.installEventFilter(self)
        except Exception:
            pass

        self._group_strip = QFrame(self)
        self._group_strip.setObjectName("deviceGroupStrip")
        self._group_strip.setVisible(False)
        try:
            self._group_strip.setStyleSheet(
                "QFrame#deviceGroupStrip { background: rgba(255,185,110,0.08); border: 1px solid rgba(255,185,110,0.22); border-radius: 8px; }"
            )
        except Exception:
            pass
        _group_root = QVBoxLayout(self._group_strip)
        _group_root.setContentsMargins(8, 6, 8, 6)
        _group_root.setSpacing(4)
        _group_top = QHBoxLayout()
        _group_top.setContentsMargins(0, 0, 0, 0)
        _group_top.setSpacing(6)
        self._group_title_label = QLabel("", self._group_strip)
        self._group_title_label.setStyleSheet("color:#f3d6a8; font-weight:700;")
        self._group_title_label.setWordWrap(True)
        self._group_members_label = QLabel("", self._group_strip)
        self._group_members_label.setStyleSheet("color:#c9c3b3; font-size: 11px;")
        self._group_members_label.setWordWrap(True)
        self._btn_group_note_fx = QToolButton(self._group_strip)
        self._btn_group_note_fx.setText("NOTE→Gruppe")
        self._btn_group_note_fx.setToolTip("NOTE-FX für alle Instrumente dieser Gruppe hinzufügen")
        self._btn_group_note_fx.setAutoRaise(True)
        self._btn_group_note_fx.setFixedSize(QSize(104, 24))
        self._btn_group_audio_fx = QToolButton(self._group_strip)
        self._btn_group_audio_fx.setText("AUDIO→Gruppe")
        self._btn_group_audio_fx.setToolTip("AUDIO-FX auf alle Tracks dieser Gruppe anwenden")
        self._btn_group_audio_fx.setAutoRaise(True)
        self._btn_group_audio_fx.setFixedSize(QSize(112, 24))
        for _btn in (self._btn_group_note_fx, self._btn_group_audio_fx):
            try:
                _btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _btn.setStyleSheet(
                    "QToolButton { color:#f3e4c3; border:1px solid rgba(255,185,110,0.30); border-radius:6px; background: rgba(255,185,110,0.06); padding:0px 6px; font-weight:600; }"
                    "QToolButton:hover { background: rgba(255,185,110,0.14); border-color: rgba(255,185,110,0.44); }"
                    "QToolButton:disabled { color:#8f8677; border-color: rgba(255,255,255,0.06); background: rgba(255,255,255,0.02); }"
                )
            except Exception:
                pass
        try:
            self._btn_group_note_fx.clicked.connect(lambda _=False: self._show_group_fx_menu("note_fx", self._btn_group_note_fx))
            self._btn_group_audio_fx.clicked.connect(lambda _=False: self._show_group_fx_menu("audio_fx", self._btn_group_audio_fx))
        except Exception:
            pass
        _group_top.addWidget(self._group_title_label, 1)
        _group_top.addWidget(self._btn_group_note_fx, 0)
        _group_top.addWidget(self._btn_group_audio_fx, 0)
        _group_root.addLayout(_group_top)
        _group_root.addWidget(self._group_members_label, 0)

        self._scope_strip = QFrame(self)
        self._scope_strip.setObjectName("deviceScopeStrip")
        self._scope_strip.setVisible(False)
        try:
            self._scope_strip.setStyleSheet(
                "QFrame#deviceScopeStrip { background: rgba(86,168,255,0.06); border: 1px solid rgba(86,168,255,0.18); border-radius: 8px; }"
            )
        except Exception:
            pass
        _scope_root = QVBoxLayout(self._scope_strip)
        _scope_root.setContentsMargins(8, 6, 8, 6)
        _scope_root.setSpacing(3)
        self._scope_title_label = QLabel("", self._scope_strip)
        self._scope_title_label.setStyleSheet("color:#b9dcff; font-weight:700;")
        self._scope_title_label.setWordWrap(True)
        self._scope_body_label = QLabel("", self._scope_strip)
        self._scope_body_label.setStyleSheet("color:#c9d6e5; font-size: 11px;")
        self._scope_body_label.setWordWrap(True)
        _scope_root.addWidget(self._scope_title_label, 0)
        _scope_root.addWidget(self._scope_body_label, 0)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addWidget(title, 0)
        header.addWidget(self._batch_mode_badge, 0)
        header.addWidget(self._batch_hint_label, 1)

        # v0.0.20.643: Grouped dropdown menus instead of 9 squeezed buttons (AP8 UI fix)
        # "View" dropdown: collapse/expand/focus actions
        from PySide6.QtWidgets import QToolButton as _QTB, QMenu as _QM
        self._btn_view_menu = _QTB(self)
        self._btn_view_menu.setText("👁 View")
        self._btn_view_menu.setToolTip("View Controls: Collapse, Expand, Focus")
        self._btn_view_menu.setAutoRaise(True)
        self._btn_view_menu.setPopupMode(_QTB.ToolButtonPopupMode.InstantPopup)
        self._btn_view_menu.setStyleSheet(
            "QToolButton { font-size: 10px; padding: 2px 6px; border: 1px solid #555; border-radius: 3px; }"
            "QToolButton:hover { background: #444; }"
            "QToolButton::menu-indicator { image: none; }"
        )
        _view_menu = _QM(self._btn_view_menu)
        _view_menu.setStyleSheet("QMenu { font-size: 10px; } QMenu::item { padding: 4px 12px; }")
        _view_menu.addAction("◪ Inaktive einklappen", self._collapse_inactive_device_cards)
        _view_menu.addAction("▾▾ Alle einklappen", self._collapse_all_device_cards)
        _view_menu.addAction("▸▸ Alle ausklappen", self._expand_all_device_cards)
        _view_menu.addSeparator()
        _view_menu.addAction("◎ Fokusansicht", self._collapse_focus_device_cards)
        _view_menu.addAction("↺ Reset", self._reset_normal_device_view)
        self._btn_view_menu.setMenu(_view_menu)
        header.addWidget(self._btn_view_menu, 0)

        # "Zone" dropdown: focus by zone type
        self._btn_zone_menu = _QTB(self)
        self._btn_zone_menu.setText("🎯 Zone")
        self._btn_zone_menu.setToolTip("Zone Focus: Note-FX / Instrument / Audio-FX")
        self._btn_zone_menu.setAutoRaise(True)
        self._btn_zone_menu.setPopupMode(_QTB.ToolButtonPopupMode.InstantPopup)
        self._btn_zone_menu.setStyleSheet(
            "QToolButton { font-size: 10px; padding: 2px 6px; border: 1px solid #555; border-radius: 3px; }"
            "QToolButton:hover { background: #444; }"
            "QToolButton::menu-indicator { image: none; }"
        )
        _zone_menu = _QM(self._btn_zone_menu)
        _zone_menu.setStyleSheet("QMenu { font-size: 10px; } QMenu::item { padding: 4px 12px; }")
        _zone_menu.addAction("N — Nur Note-FX", lambda: self._focus_only_zone_device_cards("note_fx"))
        _zone_menu.addAction("I — Nur Instrument", lambda: self._focus_only_zone_device_cards("instrument"))
        _zone_menu.addAction("A — Nur Audio-FX", lambda: self._focus_only_zone_device_cards("audio_fx"))
        self._btn_zone_menu.setMenu(_zone_menu)
        header.addWidget(self._btn_zone_menu, 0)

        # Keep the original buttons hidden but alive (for keyboard shortcuts/programmatic access)
        for _btn in [self._btn_collapse_inactive, self._btn_collapse_all, self._btn_expand_all,
                     self._btn_focus_only, self._btn_focus_note_zone, self._btn_focus_instrument_zone,
                     self._btn_focus_audio_zone, self._btn_reset_view]:
            _btn.setVisible(False)

        header.addWidget(self._btn_batch_help, 0)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)

        self.scroll = QScrollArea()
        # v108 UX: chain soll horizontal scrollen statt alle Device-Cards zusammenzuquetschen.
        # WidgetResizable=False + explizite Host-Größe → echte Scrollbar bei vielen Devices.
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        try:
            self.scroll.horizontalScrollBar().setSingleStep(48)
            self.scroll.horizontalScrollBar().setPageStep(240)
        except Exception:
            pass
        # v109 UX: Dark-Theme Scrollbar sichtbar machen (war oft optisch kaum erkennbar).
        try:
            self.scroll.setStyleSheet(
                """
                QScrollBar:horizontal {
                    height: 14px;
                    margin: 0px 2px 0px 2px;
                    background: rgba(255,255,255,0.03);
                    border: 1px solid rgba(255,255,255,0.06);
                    border-radius: 6px;
                }
                QScrollBar::handle:horizontal {
                    min-width: 28px;
                    background: rgba(120,120,140,0.85);
                    border: 1px solid rgba(255,255,255,0.12);
                    border-radius: 6px;
                }
                QScrollBar::handle:horizontal:hover {
                    background: rgba(150,150,180,0.95);
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                    height: 0px;
                    background: transparent;
                    border: none;
                }
                QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                    background: transparent;
                }
                """
            )
        except Exception:
            pass

        self.chain_host = _DropForwardHost(self)
        self.chain_host.setObjectName("deviceChainHost")
        self.chain_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.chain = QHBoxLayout(self.chain_host)
        # v113: kleine Kopfzeile für Gruppen-Badges (Note-FX | Instrument | Audio-FX)
        # ohne zusätzliche Layout-Widgets in der Chain (DnD-Indizes bleiben stabil).
        self.chain.setContentsMargins(0, 22, 0, 0)
        self.chain.setSpacing(8)
        try:
            self.chain.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        except Exception:
            pass

        self.empty_label = QLabel("Track auswählen.\\nDann Devices aus dem Browser hierher ziehen oder doppelklicken.")
        self.empty_label.setObjectName("devicePanelEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.empty_label.setStyleSheet("color:#9a9a9a;")
        self.chain.addWidget(self.empty_label)
        self.chain.addStretch(1)

        self.scroll.setWidget(self.chain_host)
        try:
            self.chain_host.setMinimumSize(1, 1)
        except Exception:
            pass

        # v113: visuelle Gruppierungs-Overlays (absolut positioniert, nicht im Layout).
        try:
            self._ensure_zone_visuals()
            self._hide_zone_visuals()
        except Exception:
            pass

        # Drop indicator for insert-at-position
        self._drop_indicator = _DropIndicator(self.chain_host)
        self._drop_insert_kind: str = ""      # "note_fx" | "audio_fx"
        self._drop_insert_index: int = -1     # -1 = append

        root.addLayout(header)
        root.addWidget(self._group_strip, 0)
        root.addWidget(self._scope_strip, 0)
        root.addWidget(sep)

        # v0.0.20.554: Breadcrumb bar for container zoom navigation
        self._breadcrumb_bar = QWidget(self)
        self._breadcrumb_bar.setVisible(False)
        _bc_lay = QHBoxLayout(self._breadcrumb_bar)
        _bc_lay.setContentsMargins(4, 2, 4, 2)
        _bc_lay.setSpacing(6)
        self._btn_zoom_back = QPushButton("← Zurück")
        self._btn_zoom_back.setFixedHeight(22)
        self._btn_zoom_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_zoom_back.setStyleSheet(
            "QPushButton { font-size: 10px; font-weight: bold; color: #fff; "
            "padding: 2px 10px; border: 1px solid #7e57c2; border-radius: 3px; "
            "background: rgba(126, 87, 194, 60); }"
            "QPushButton:hover { background: rgba(126, 87, 194, 100); }"
        )
        self._btn_zoom_back.clicked.connect(lambda _=False: self.zoom_out())
        _bc_lay.addWidget(self._btn_zoom_back)
        self._breadcrumb_label = QLabel("")
        self._breadcrumb_label.setStyleSheet(
            "font-size: 10px; color: #ce93d8; font-weight: bold;"
        )
        _bc_lay.addWidget(self._breadcrumb_label, 1)
        root.addWidget(self._breadcrumb_bar, 0)

        root.addWidget(self.scroll, 1)

        try:
            self._shortcut_reset_escape = QShortcut(QKeySequence("Esc"), self)
            self._shortcut_reset_escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self._shortcut_reset_escape.setAutoRepeat(False)
            self._shortcut_reset_escape.activated.connect(self._handle_escape_reset_shortcut)
        except Exception:
            self._shortcut_reset_escape = None

        try:
            self.setAcceptDrops(True)
        except Exception:
            pass

        # project updated -> refresh (SAFE)
        try:
            proj = getattr(self._services, "project", None) if self._services else None
            if proj is not None and hasattr(proj, "project_updated"):
                proj.project_updated.connect(self._safe_render_current_track)
        except Exception:
            pass

        try:
            self._set_batch_action_mode("")
            self._update_batch_hint_visibility()
        except Exception:
            pass

    def _current_group_info(self) -> tuple[str, str, list[Any]]:
        tid = str(getattr(self, "_current_track", "") or "")
        if not tid or self._services is None:
            return "", "", []
        proj = getattr(self._services, "project", None)
        ctx = getattr(proj, "ctx", None) if proj is not None else None
        project_obj = getattr(ctx, "project", None) if ctx is not None else None
        trk = _find_track(project_obj, tid) if project_obj is not None else None
        if trk is None:
            return "", "", []
        gid = str(getattr(trk, "track_group_id", "") or "")
        if not gid:
            return "", "", []
        try:
            members = [
                t for t in (getattr(project_obj, "tracks", []) or [])
                if str(getattr(t, "track_group_id", "") or "") == gid
                and str(getattr(t, "kind", "") or "") != "master"
            ]
        except Exception:
            members = []
        if len(members) < 2:
            return "", "", []
        grp_name = str(getattr(trk, "track_group_name", "") or getattr(members[0], "track_group_name", "") or "Gruppe")
        return gid, grp_name, members

    def browser_add_scope(self, device_kind: str = "") -> tuple[str, str]:
        """Return a short badge text + tooltip for Browser/Add flows.

        Safe/UI-only: this only explains the current target. It does not change any
        add-routing behaviour. Normal browser Add / double-click / drag&drop still
        goes to the active track, while NOTE→Gruppe / AUDIO→Gruppe remain the only
        group-wide actions in this UI.
        """
        try:
            proj = getattr(self._services, "project", None) if self._services is not None else None
            ctx = getattr(proj, "ctx", None) if proj is not None else None
            project_obj = getattr(ctx, "project", None) if ctx is not None else None
            trk = _find_track(project_obj, str(getattr(self, "_current_track", "") or "")) if project_obj is not None else None
            if trk is None:
                return ("Ziel: keine Spur", "Keine aktive Spur ausgewählt. Bitte zuerst eine Spur im Arranger auswählen.")
            name = str(getattr(trk, "name", "") or getattr(trk, "id", "") or "Track")
            kind = str(device_kind or "").strip().lower()
            gid, grp_name, members = self._current_group_info()
            if gid and members:
                if kind == "instrument":
                    short = f"Ziel: Spur {name}"
                    tip = (
                        f"Instrument hinzufügen → aktive Spur: {name}.\n"
                        f"Diese Spur ist Teil der Gruppe '{grp_name}', aber Browser-Add wirkt hier nicht auf die ganze Gruppe.\n"
                        f"Für echte Gruppen-Aktionen weiterhin nur die Gruppenbuttons im DevicePanel verwenden."
                    )
                elif kind in ("note_fx", "audio_fx"):
                    short = f"Add → Spur {name}"
                    group_label = "NOTE→Gruppe" if kind == "note_fx" else "AUDIO→Gruppe"
                    tip = (
                        f"Browser-Add / Doppelklick / Drag&Drop landet auf der aktiven Spur: {name}.\n"
                        f"Nicht auf die ganze Gruppe '{grp_name}'.\n"
                        f"Für die ganze Gruppe nur {group_label} im DevicePanel verwenden."
                    )
                else:
                    short = f"Ziel: Spur {name}"
                    tip = (
                        f"Aktive Spur: {name}.\n"
                        f"Diese Spur gehört zur Gruppe '{grp_name}', aber normale Browser-Aktionen wirken weiterhin nur auf diese Spur."
                    )
            else:
                short = f"Ziel: Spur {name}"
                if kind == "instrument":
                    tip = f"Instrument hinzufügen → aktive Spur: {name}."
                elif kind in ("note_fx", "audio_fx"):
                    tip = f"Browser-Add / Doppelklick / Drag&Drop landet auf der aktiven Spur: {name}."
                else:
                    tip = f"Aktive Spur: {name}."
            return (short, tip)
        except Exception:
            return ("Ziel: Spur", "Aktive Spur konnte nicht sicher ermittelt werden.")

    def _describe_track_fx_counts(self, trk: Any) -> str:
        try:
            note_chain = getattr(trk, "note_fx_chain", None)
            note_count = len(note_chain.get("devices", []) or []) if isinstance(note_chain, dict) else 0
        except Exception:
            note_count = 0
        try:
            audio_chain = getattr(trk, "audio_fx_chain", None)
            audio_count = len(audio_chain.get("devices", []) or []) if isinstance(audio_chain, dict) else 0
        except Exception:
            audio_count = 0
        try:
            plugin_id = str(getattr(trk, "plugin_type", "") or "")
            sf2_path = str(getattr(trk, "sf2_path", "") or "")
            has_instrument = bool(plugin_id or sf2_path or str(getattr(trk, "kind", "") or "") == "instrument")
        except Exception:
            has_instrument = False
        instrument_text = "Instrument 1" if has_instrument else "Instrument 0"
        return f"Note-FX {note_count} • {instrument_text} • Audio-FX {audio_count}"

    def _update_scope_strip(self, trk: Any = None) -> None:
        try:
            if trk is None:
                proj = getattr(self._services, "project", None) if self._services is not None else None
                ctx = getattr(proj, "ctx", None) if proj is not None else None
                project_obj = getattr(ctx, "project", None) if ctx is not None else None
                trk = _find_track(project_obj, str(getattr(self, "_current_track", "") or "")) if project_obj is not None else None
            if trk is None:
                self._scope_strip.setVisible(False)
                return
            tid = str(getattr(trk, "id", "") or "")
            name = str(getattr(trk, "name", "") or tid or "Track")
            kind = str(getattr(trk, "kind", "") or "track")
            gid, grp_name, members = self._current_group_info()
            fx_counts = self._describe_track_fx_counts(trk)
            self._scope_title_label.setText(f"Aktive Spur-Ziel — {name} ({kind})")
            lines = [
                f"Sichtbare Device-Kette unten gehört nur zu dieser Spur: {name}.",
                f"Inhalt dieser Spur: {fx_counts}.",
                "Browser-Add / Doppelklick / Drag&Drop landen hier immer nur auf der aktiven Spur.",
            ]
            if gid and members:
                lines.append(
                    f"Diese Spur ist Teil der Gruppe '{grp_name}'. Für die ganze Gruppe immer nur NOTE→Gruppe oder AUDIO→Gruppe oben benutzen."
                )
                lines.append("Wichtig: Diese Ansicht zeigt keinen gemeinsamen Gruppenbus und keine gemeinsame Gruppen-Device-Kette.")
            self._scope_body_label.setText("\n".join(lines))
            self._scope_strip.setVisible(True)
        except Exception:
            try:
                self._scope_strip.setVisible(False)
            except Exception:
                pass

    def _update_group_strip(self) -> None:
        try:
            gid, grp_name, members = self._current_group_info()
            if not gid or not members:
                self._group_strip.setVisible(False)
                return
            inst_members = [t for t in members if str(getattr(t, "kind", "") or "") == "instrument"]
            member_names = [str(getattr(t, "name", "") or getattr(t, "id", "") or "Track") for t in members]
            member_preview = "  •  ".join(member_names[:6])
            if len(member_names) > 6:
                member_preview += f"  •  +{len(member_names) - 6} weitere"
            active_name = "aktive Spur"
            try:
                proj = getattr(self._services, "project", None) if self._services is not None else None
                ctx = getattr(proj, "ctx", None) if proj is not None else None
                project_obj = getattr(ctx, "project", None) if ctx is not None else None
                active_track = _find_track(project_obj, str(getattr(self, "_current_track", "") or "")) if project_obj is not None else None
                if active_track is not None:
                    active_name = str(getattr(active_track, "name", "") or getattr(active_track, "id", "") or "aktive Spur")
            except Exception:
                pass
            self._group_title_label.setText(f"Gruppen-Aktionen — {grp_name} ({len(members)} Tracks, kein gemeinsamer Bus)")
            self._group_members_label.setText(
                f"Aktive Spur in dieser Gruppe: {active_name}. Die sichtbare Device-Kette unten bleibt nur auf dieser Spur.\n"
                f"Ganze Gruppe nur über NOTE→Gruppe / AUDIO→Gruppe oben. Mitglieder: {member_preview}"
            )
            self._btn_group_note_fx.setEnabled(bool(inst_members))
            self._btn_group_audio_fx.setEnabled(True)
            self._btn_group_note_fx.setToolTip(
                "NOTE-FX für alle Instrumente dieser Gruppe hinzufügen" if inst_members else "In dieser Gruppe sind keine Instrument-Tracks für NOTE-FX"
            )
            self._btn_group_audio_fx.setToolTip("AUDIO-FX auf alle Tracks dieser Gruppe anwenden")
            self._group_strip.setVisible(True)
        except Exception:
            try:
                self._group_strip.setVisible(False)
            except Exception:
                pass

    def _show_group_fx_menu(self, kind: str, anchor_btn) -> None:  # noqa: ANN001
        gid, grp_name, members = self._current_group_info()
        if not gid or not members or anchor_btn is None:
            return
        menu = QMenu(self)
        try:
            title = "NOTE-FX" if str(kind) == "note_fx" else "AUDIO-FX"
            menu.addSection(f"{title} → Gruppe: {grp_name}")
        except Exception:
            pass
        specs = []
        try:
            if str(kind) == "note_fx":
                from .fx_specs import get_note_fx
                specs = list(get_note_fx() or [])
            else:
                from .fx_specs import get_audio_fx
                specs = list(get_audio_fx() or [])
        except Exception:
            specs = []
        if str(kind) == "note_fx":
            members = [t for t in members if str(getattr(t, "kind", "") or "") == "instrument"]
        if not specs or not members:
            a = menu.addAction("(keine passenden Ziele)")
            a.setEnabled(False)
        else:
            try:
                specs = sorted(specs, key=lambda s: str(getattr(s, "name", "") or getattr(s, "plugin_id", "")))
            except Exception:
                pass
            for spec in specs[:80]:
                name = str(getattr(spec, "name", "") or getattr(spec, "plugin_id", "") or "FX")
                pid = str(getattr(spec, "plugin_id", "") or "")
                act = menu.addAction(name)
                act.triggered.connect(lambda _=False, _k=str(kind), _pid=pid, _name=name: self._apply_fx_to_current_group(_k, _pid, _name))
        try:
            menu.exec(anchor_btn.mapToGlobal(anchor_btn.rect().bottomLeft()))
        except Exception:
            pass

    def _apply_fx_to_current_group(self, kind: str, plugin_id: str, name: str = "") -> None:
        kind = str(kind or "").strip()
        plugin_id = str(plugin_id or "").strip()
        if kind not in ("note_fx", "audio_fx") or not plugin_id:
            return
        gid, grp_name, members = self._current_group_info()
        if not gid or not members:
            return
        if kind == "note_fx":
            members = [t for t in members if str(getattr(t, "kind", "") or "") == "instrument"]
        track_ids = [str(getattr(t, "id", "") or "") for t in members if str(getattr(t, "id", "") or "")]
        if not track_ids:
            return
        changed = 0
        proj = getattr(self._services, "project", None) if self._services else None
        ctx = getattr(proj, "ctx", None) if proj is not None else None
        project_obj = getattr(ctx, "project", None) if ctx is not None else None
        for tid in track_ids:
            try:
                if kind == "note_fx":
                    ok = self.add_note_fx_to_track(tid, plugin_id, name=name, defer_emit=True, defer_restart=True)
                else:
                    ok = self.add_audio_fx_to_track(tid, plugin_id, name=name, defer_emit=True, defer_restart=True, defer_rebuild=True)
                if ok:
                    changed += 1
            except Exception:
                continue
        if changed <= 0:
            return
        try:
            if kind == "audio_fx" and project_obj is not None:
                self._rebuild_audio_fx(project_obj)
        except Exception:
            pass
        try:
            self._restart_if_playing()
        except Exception:
            pass
        try:
            self._emit_project_updated()
        except Exception:
            pass
        try:
            if proj is not None and hasattr(proj, "status"):
                fx_label = "NOTE-FX" if kind == "note_fx" else "AUDIO-FX"
                proj.status.emit(f"{fx_label} '{name or plugin_id}' auf Gruppe '{grp_name}' angewendet ({changed} Tracks)")
        except Exception:
            pass

    def _update_batch_action_button_state(self) -> None:
        try:
            cards = self._iter_device_cards()
            has_cards = bool(cards)
            has_inactive = any(not bool(getattr(c, "_ui_enabled", True)) for c in cards)
            has_collapsed = any(bool(c.is_collapsed()) for c in cards)
            has_expanded = any(not bool(c.is_collapsed()) for c in cards)
            if getattr(self, "_btn_collapse_inactive", None) is not None:
                self._btn_collapse_inactive.setEnabled(bool(has_cards and has_inactive))
            if getattr(self, "_btn_collapse_all", None) is not None:
                self._btn_collapse_all.setEnabled(bool(has_cards and has_expanded))
            if getattr(self, "_btn_expand_all", None) is not None:
                self._btn_expand_all.setEnabled(bool(has_cards and has_collapsed))
            if getattr(self, "_btn_focus_only", None) is not None:
                self._btn_focus_only.setEnabled(bool(has_cards and len(cards) > 1))
            zone_counts = {"note_fx": 0, "instrument": 0, "audio_fx": 0}
            for c in cards:
                k = str(getattr(c, "_collapse_state_kind", "") or "")
                if k in zone_counts:
                    zone_counts[k] += 1
            if getattr(self, "_btn_focus_note_zone", None) is not None:
                self._btn_focus_note_zone.setEnabled(bool(zone_counts.get("note_fx", 0)))
            if getattr(self, "_btn_focus_instrument_zone", None) is not None:
                self._btn_focus_instrument_zone.setEnabled(bool(zone_counts.get("instrument", 0)))
            if getattr(self, "_btn_focus_audio_zone", None) is not None:
                self._btn_focus_audio_zone.setEnabled(bool(zone_counts.get("audio_fx", 0)))

            mode = str(getattr(self, "_batch_action_mode", "") or "")
            has_focus_mode = bool(mode == "focus_card" or mode.startswith("zone:"))
            if getattr(self, "_btn_reset_view", None) is not None:
                self._btn_reset_view.setEnabled(bool(has_cards and (has_collapsed or has_focus_mode)))
            if not has_cards:
                self._set_batch_action_mode("")
            elif mode == "focus_card" and not bool(has_cards and len(cards) > 1):
                self._set_batch_action_mode("")
            elif mode == "zone:note_fx" and not bool(zone_counts.get("note_fx", 0)):
                self._set_batch_action_mode("")
            elif mode == "zone:instrument" and not bool(zone_counts.get("instrument", 0)):
                self._set_batch_action_mode("")
            elif mode == "zone:audio_fx" and not bool(zone_counts.get("audio_fx", 0)):
                self._set_batch_action_mode("")
        except Exception:
            pass

    def _default_batch_hint_text(self) -> str:
        return "Batch: ◪ inaktiv | ▾▾ zu | ▸▸ auf | ◎ Fokus | N/I/A Zonen | ↺/Esc Reset | ? Hilfe"

    def _restore_batch_hint_text(self) -> None:
        try:
            mode = str(getattr(self, "_batch_action_mode", "") or "")
            if mode == "focus_card":
                txt = "Ansicht: ◎ Fokus-Card offen (UI-only)"
            elif mode == "zone:note_fx":
                txt = "Ansicht: N / nur NOTE-FX offen (UI-only)"
            elif mode == "zone:instrument":
                txt = "Ansicht: I / nur INSTRUMENT offen (UI-only)"
            elif mode == "zone:audio_fx":
                txt = "Ansicht: A / nur AUDIO-FX offen (UI-only)"
            elif mode == "collapsed_all":
                txt = "Ansicht: alle Device-Cards eingeklappt (UI-only)"
            elif mode == "expanded_all":
                txt = "Ansicht: alle Device-Cards ausgeklappt (UI-only)"
            elif mode == "collapsed_inactive":
                txt = "Ansicht: inaktive Devices eingeklappt (UI-only)"
            else:
                txt = self._default_batch_hint_text()
            if getattr(self, "_batch_hint_label", None) is not None:
                self._batch_hint_label.setText(txt)
        except Exception:
            pass

    def _update_batch_mode_badge(self) -> None:
        try:
            lbl = getattr(self, "_batch_mode_badge", None)
            if lbl is None:
                return
            mode = str(getattr(self, "_batch_action_mode", "") or "")
            text = "NORMAL"
            style = (
                "QLabel#deviceBatchModeBadge { color:#c9cedf; background: rgba(255,255,255,0.03); "
                "border:1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 600; }"
            )
            if mode == "focus_card":
                text = "FOKUS ◎"
                style = (
                    "QLabel#deviceBatchModeBadge { color:#eef3ff; background: rgba(129,163,255,0.16); "
                    "border:1px solid rgba(129,163,255,0.45); border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 700; }"
                )
            elif mode == "zone:note_fx":
                text = "ZONE N"
                style = (
                    "QLabel#deviceBatchModeBadge { color:#dff3ff; background: rgba(84,184,255,0.13); "
                    "border:1px solid rgba(84,184,255,0.35); border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 700; }"
                )
            elif mode == "zone:instrument":
                text = "ZONE I"
                style = (
                    "QLabel#deviceBatchModeBadge { color:#ebf0ff; background: rgba(117,132,255,0.14); "
                    "border:1px solid rgba(117,132,255,0.34); border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 700; }"
                )
            elif mode == "zone:audio_fx":
                text = "ZONE A"
                style = (
                    "QLabel#deviceBatchModeBadge { color:#e5ffe9; background: rgba(70,200,110,0.12); "
                    "border:1px solid rgba(70,200,110,0.34); border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 700; }"
                )
            elif mode == "collapsed_all":
                text = "ALLE ZU"
            elif mode == "expanded_all":
                text = "ALLE AUF"
            elif mode == "collapsed_inactive":
                text = "INAKTIV ZU"
            lbl.setText(text)
            if mode and mode != "":
                lbl.setToolTip(f"Aktuelle Device-Ansicht: {text} (UI-only)\nKlick = Quick-Reset, Rechtsklick = Ansichtsmenü")
            else:
                lbl.setToolTip("Aktuelle Device-Ansicht: NORMAL (UI-only)\nKlick = Kurzhilfe, Rechtsklick = Ansichtsmenü")
            lbl.setStyleSheet(style)
            try:
                lbl.adjustSize()
            except Exception:
                pass
        except Exception:
            pass

    def _set_batch_action_mode(self, mode: str) -> None:
        try:
            self._batch_action_mode = str(mode or "")
            mode = self._batch_action_mode
            if getattr(self, "_btn_focus_only", None) is not None:
                self._btn_focus_only.setChecked(mode == "focus_card")
            if getattr(self, "_btn_focus_note_zone", None) is not None:
                self._btn_focus_note_zone.setChecked(mode == "zone:note_fx")
            if getattr(self, "_btn_focus_instrument_zone", None) is not None:
                self._btn_focus_instrument_zone.setChecked(mode == "zone:instrument")
            if getattr(self, "_btn_focus_audio_zone", None) is not None:
                self._btn_focus_audio_zone.setChecked(mode == "zone:audio_fx")
        except Exception:
            pass
        try:
            self._update_batch_mode_badge()
        except Exception:
            pass
        try:
            self._restore_batch_hint_text()
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802, ANN001
        try:
            hints = getattr(self, "_batch_hover_hints", {}) or {}
            if obj in hints:
                et = event.type() if event is not None else None
                if et in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
                    if getattr(self, "_batch_hint_label", None) is not None:
                        self._batch_hint_label.setText(str(hints.get(obj, "") or self._default_batch_hint_text()))
                elif et in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                    self._restore_batch_hint_text()
        except Exception:
            pass
        try:
            badge = getattr(self, "_batch_mode_badge", None)
            if obj is badge and event is not None:
                et = event.type()
                if et in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
                    if getattr(self, "_batch_hint_label", None) is not None:
                        mode = str(getattr(self, "_batch_action_mode", "") or "")
                        if mode:
                            self._batch_hint_label.setText("Badge: Klick = Reset auf NORMAL, Rechtsklick = Ansichtsmenü (UI-only)")
                        else:
                            self._batch_hint_label.setText("Badge: Klick = Kurzhilfe, Rechtsklick = Ansichtsmenü (UI-only)")
                elif et in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                    self._restore_batch_hint_text()
                elif et == QEvent.Type.MouseButtonRelease:
                    try:
                        btn = event.button()
                    except Exception:
                        btn = None
                    if btn == Qt.MouseButton.LeftButton:
                        self._handle_batch_mode_badge_left_click()
                        return True
                    if btn == Qt.MouseButton.RightButton:
                        self._show_batch_mode_badge_menu(event.globalPosition().toPoint())
                        return True
                elif et == QEvent.Type.ContextMenu:
                    try:
                        self._show_batch_mode_badge_menu(event.globalPos())
                    except Exception:
                        pass
                    return True
        except Exception:
            pass
        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False

    def _update_batch_hint_visibility(self) -> None:
        try:
            lbl = getattr(self, "_batch_hint_label", None)
            if lbl is None:
                return
            # Auf kleineren Breiten lieber Platz für Buttons lassen.
            lbl.setVisible(self.width() >= 1280)
        except Exception:
            pass

    def resizeEvent(self, event):  # noqa: N802, ANN001
        try:
            super().resizeEvent(event)
        finally:
            try:
                self._sync_chain_host_size()
            except Exception:
                pass
            try:
                self._update_zone_visuals()
            except Exception:
                pass
            try:
                self._update_batch_hint_visibility()
            except Exception:
                pass

    def _ensure_zone_visuals(self) -> None:
        try:
            if getattr(self, "chain_host", None) is None:
                return
            for key, label_text in (("note_fx", "NOTE-FX"), ("instrument", "INSTRUMENT"), ("audio_fx", "AUDIO-FX")):
                if key not in self._zone_backdrops:
                    bg = QFrame(self.chain_host)
                    bg.setObjectName(f"deviceZoneBackdrop_{key}")
                    try:
                        bg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    except Exception:
                        pass
                    if key == "instrument":
                        bg_style = (
                            "QFrame {"
                            " background: rgba(255, 170, 40, 0.045);"
                            " border: 1px solid rgba(255, 170, 40, 0.16);"
                            " border-radius: 10px;"
                            "}"
                        )
                    elif key == "note_fx":
                        bg_style = (
                            "QFrame {"
                            " background: rgba(90, 140, 255, 0.035);"
                            " border: 1px solid rgba(90, 140, 255, 0.10);"
                            " border-radius: 10px;"
                            "}"
                        )
                    else:
                        bg_style = (
                            "QFrame {"
                            " background: rgba(120, 230, 200, 0.028);"
                            " border: 1px solid rgba(120, 230, 200, 0.09);"
                            " border-radius: 10px;"
                            "}"
                        )
                    bg.setStyleSheet(bg_style)
                    bg.hide()
                    self._zone_backdrops[key] = bg
                if key not in self._zone_badges:
                    lab = QLabel(label_text, self.chain_host)
                    lab.setObjectName(f"deviceZoneBadge_{key}")
                    try:
                        lab.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    except Exception:
                        pass
                    lab.setStyleSheet(
                        "QLabel {"
                        " color:#c8d7ff;"
                        " background: rgba(80, 120, 255, 0.10);"
                        " border: 1px solid rgba(120, 170, 255, 0.28);"
                        " border-radius: 8px;"
                        " padding: 1px 8px;"
                        " font-size: 10px;"
                        " font-weight: 700;"
                        " letter-spacing: 0.5px;"
                        "}"
                    )
                    lab.hide()
                    self._zone_badges[key] = lab
                if key != "audio_fx" and key not in self._zone_dividers:
                    ln = QFrame(self.chain_host)
                    ln.setObjectName(f"deviceZoneDivider_{key}")
                    try:
                        ln.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    except Exception:
                        pass
                    ln.setStyleSheet(
                        "QFrame {"
                        " background: rgba(190, 198, 216, 0.16);"
                        " border: none;"
                        "}"
                    )
                    ln.setFixedWidth(1)
                    ln.hide()
                    self._zone_dividers[key] = ln
        except Exception:
            pass

    def _hide_zone_visuals(self) -> None:
        try:
            for w in (self._zone_backdrops or {}).values():
                try:
                    w.hide()
                except Exception:
                    pass
            for w in (self._zone_badges or {}).values():
                try:
                    w.hide()
                except Exception:
                    pass
            for w in (self._zone_dividers or {}).values():
                try:
                    w.hide()
                except Exception:
                    pass
        except Exception:
            pass

    def _update_zone_visuals(self) -> None:
        """Update group badges/dividers without touching layout indices (UI-only)."""
        try:
            self._ensure_zone_visuals()
            self._hide_zone_visuals()
            meta = self._zone_layout_meta if isinstance(getattr(self, '_zone_layout_meta', None), dict) else {}
            if not meta or not self._current_track:
                return

            n_note = int(meta.get('n_note', 0) or 0)
            n_audio = int(meta.get('n_audio', 0) or 0)
            inst_card = meta.get('inst_card')
            if inst_card is None or inst_card.parent() is None:
                return

            # Anchor geometry
            ix = int(inst_card.x())
            iw = int(inst_card.width())
            if iw <= 0:
                return

            gap = int(self.chain.spacing()) if self.chain is not None else 8
            host_w = int(self.chain_host.width()) if self.chain_host is not None else 0
            host_h = int(self.chain_host.height()) if self.chain_host is not None else 0
            if host_w <= 0 or host_h <= 0:
                return

            row_y = 2
            # v117 UX-Polish: Divider nur im Kopfbereich (nicht durch Device-Widgets)
            line_top = 4
            line_h = 12

            note_start = 4
            note_end = max(note_start + 32, ix - gap // 2)
            inst_start = max(4, ix)
            inst_end = min(host_w - 4, ix + iw)
            audio_start = min(host_w - 4, ix + iw + gap // 2)

            if n_audio > 0:
                # Last audio card gives a better visual end for the divider span.
                start_idx = n_note + 1
                last_item = self.chain.itemAt(start_idx + n_audio - 1) if self.chain is not None else None
                if last_item and last_item.widget():
                    lw = last_item.widget()
                    audio_end = max(audio_start + 64, int(lw.x()) + int(lw.width()))
                else:
                    audio_end = max(audio_start + 64, host_w - 8)
            else:
                audio_end = max(audio_start + 96, host_w - 12)
            audio_end = min(host_w - 8, audio_end)

            zones = {
                'note_fx': (note_start, max(0, note_end - note_start)),
                'instrument': (inst_start, max(0, inst_end - inst_start)),
                'audio_fx': (audio_start, max(0, audio_end - audio_start)),
            }

            # Zone-Fokus-Overlay kompakter darstellen (v125, UI-only):
            # Nicht fokussierte Zonen werden als schmale Rails um ihre
            # eingeklappten Cards gezeichnet, statt über die volle Zonenbreite.
            focus_zone = self._zone_focus_target_kind()
            if focus_zone:
                visible_cards = [w for w in self.chain_host.findChildren(_DeviceCard) if w.isVisible()]
                zone_cards = {"note_fx": [], "instrument": [], "audio_fx": []}
                for c in visible_cards:
                    try:
                        zk = str(getattr(c, '_zone_kind', '') or '')
                    except Exception:
                        zk = ''
                    if zk in zone_cards:
                        zone_cards[zk].append(c)

                def _card_span(cards_list):
                    if not cards_list:
                        return None
                    xs = []
                    xe = []
                    for c in cards_list:
                        try:
                            g = c.geometry()
                            if not g.isValid():
                                continue
                            xs.append(int(g.x()))
                            xe.append(int(g.x()) + max(1, int(g.width())))
                        except Exception:
                            continue
                    if not xs or not xe:
                        return None
                    return (min(xs), max(xe))

                def _to_rail(kind, zx, zw):
                    span = _card_span(zone_cards.get(kind) or [])
                    rail_min = 22
                    rail_max = 52
                    pad = 6
                    if span is not None:
                        sx0, sx1 = span
                        sx0 = max(2, sx0 - pad)
                        sx1 = min(host_w - 2, sx1 + pad)
                        width = max(rail_min, min(rail_max, sx1 - sx0))
                        cx = (sx0 + sx1) // 2
                        rx = max(2, min(host_w - width - 2, cx - width // 2))
                        return (rx, width)
                    width = rail_min
                    if kind == 'audio_fx':
                        rx = max(2, min(host_w - width - 2, zx + max(0, zw - width)))
                    else:
                        rx = max(2, min(host_w - width - 2, zx))
                    return (rx, width)

                for key in ("note_fx", "instrument", "audio_fx"):
                    if key == focus_zone:
                        continue
                    zx, zw = zones.get(key, (0, 0))
                    if zw <= 0:
                        continue
                    zones[key] = _to_rail(key, int(zx), int(zw))

            # Subtile Hintergründe (v114+, UI-only)
            # Instrument immer zeigen; Note-/Audio-Zonen nur wenn dort Devices existieren.
            focus_zone = self._zone_focus_target_kind()
            for key, (zx, zw) in zones.items():
                bg = (self._zone_backdrops or {}).get(key)
                if bg is None:
                    continue
                has_devices = (key == 'instrument') or (key == 'note_fx' and n_note > 0) or (key == 'audio_fx' and n_audio > 0)
                min_zone_w = 18 if (focus_zone and key != focus_zone) else 70
                min_draw_w = 14 if (focus_zone and key != focus_zone) else 40
                if (not has_devices) or zw < min_zone_w:
                    continue
                try:
                    bx = max(2, int(zx))
                    bw = max(0, min(host_w - 4, int(zw)) - (bx - int(zx)))
                    by = 18
                    bh = max(20, host_h - by - 6)
                    if bw >= min_draw_w and bh >= 16:
                        try:
                            if focus_zone and key != focus_zone:
                                bg.setStyleSheet("QFrame { background: rgba(90, 108, 145, 0.05); border: 1px solid rgba(120, 150, 210, 0.16); border-radius: 8px; }")
                            else:
                                bg.setStyleSheet("QFrame { background: rgba(120, 138, 175, 0.08); border: 1px solid rgba(120, 150, 210, 0.22); border-radius: 10px; }")
                        except Exception:
                            pass
                        bg.setGeometry(bx, by, bw, bh)
                        bg.show()
                        bg.lower()
                except Exception:
                    pass

            # Badges
            focus_zone = self._zone_focus_target_kind()
            for key, (zx, zw) in zones.items():
                lab = (self._zone_badges or {}).get(key)
                if lab is None:
                    continue
                if focus_zone and key != focus_zone:
                    # Bei Zonenfokus Rails bewusst ohne Badge lassen – wirkt ruhiger
                    # und suggeriert nicht mehr fälschlich eine breite geöffnete Zone.
                    continue
                if zw < 80:
                    continue
                try:
                    lab.adjustSize()
                    lw = int(lab.sizeHint().width())
                    lh = int(lab.sizeHint().height())
                    tx = max(zx + 4, min(zx + zw - lw - 4, zx + 10))
                    if key == 'instrument' and zw > (lw + 24):
                        tx = zx + (zw - lw) // 2
                    lab.setGeometry(int(tx), row_y, max(lw, 10), max(lh, 14))
                    lab.show()
                    lab.raise_()
                except Exception:
                    pass

            # Dividers after NOTE-FX and after INSTRUMENT
            focus_zone = self._zone_focus_target_kind()
            div_note = (self._zone_dividers or {}).get('note_fx')
            if div_note is not None and not focus_zone and n_note > 0 and note_end < host_w - 8:
                try:
                    div_note.setGeometry(int(note_end), line_top, 1, line_h)
                    div_note.show()
                    div_note.raise_()
                except Exception:
                    pass
            div_inst = (self._zone_dividers or {}).get('instrument')
            if div_inst is not None and not focus_zone and n_audio > 0 and inst_end < host_w - 8:
                try:
                    div_inst.setGeometry(int(inst_end + gap // 2), line_top, 1, line_h)
                    div_inst.show()
                    div_inst.raise_()
                except Exception:
                    pass
        except Exception:
            pass

    def _set_pending_fx_focus(self, kind: str, device_id: str) -> None:
        try:
            self._pending_focus_kind = str(kind or "")
            self._pending_focus_device_id = str(device_id or "")
        except Exception:
            self._pending_focus_kind = ""
            self._pending_focus_device_id = ""

    def _focus_fx_card(self, kind: str, device_id: str, *, ensure_visible: bool = False) -> None:
        kind = str(kind or "")
        device_id = str(device_id or "")
        if not kind or not device_id:
            return
        self._selected_fx_kind = kind
        self._selected_fx_device_id = device_id
        for (k, did), card in (self._rendered_fx_cards or {}).items():
            try:
                if hasattr(card, "set_selected_visual"):
                    card.set_selected_visual(bool(k == kind and did == device_id))
            except Exception:
                pass
        if ensure_visible:
            card = (self._rendered_fx_cards or {}).get((kind, device_id))
            if card is not None:
                self._queue_scroll_card_into_view(card)

    def _queue_scroll_card_into_view(self, card: QWidget) -> None:
        try:
            # Use weakref so deleted cards don't keep the UI alive.
            wr = weakref.ref(card) if card is not None else None

            def _cb() -> None:
                c = wr() if wr is not None else None
                if c is None or _qt_is_deleted(c):
                    return
                self._scroll_card_into_view(c)

            QTimer.singleShot(0, _cb)
        except Exception:
            pass

    def _scroll_card_into_view(self, card: QWidget) -> None:
        try:
            if card is None or self.scroll is None:
                return
            if _qt_is_deleted(card):
                return
            sb = self.scroll.horizontalScrollBar()
            if sb is None:
                return
            x = int(card.x())
            w = int(card.width())
            vp_w = int(self.scroll.viewport().width()) if self.scroll.viewport() is not None else 0
            if vp_w <= 0:
                return
            left_margin = 16
            right_margin = 24
            cur = int(sb.value())
            if x < cur + left_margin:
                sb.setValue(max(0, x - left_margin))
                return
            if (x + w) > (cur + vp_w - right_margin):
                # center-ish when possible so parameter knobs are directly visible
                target = x - max(0, (vp_w - w) // 2)
                sb.setValue(max(0, target))
        except Exception:
            pass

    def _card_state_key(self, kind: str, device_id: str) -> str:
        try:
            return f"{str(kind or '').strip()}::{str(device_id or '').strip()}"
        except Exception:
            return ""

    def _is_card_collapsed(self, kind: str, device_id: str) -> bool:
        key = self._card_state_key(kind, device_id)
        if not key:
            return False
        return bool((self._card_collapse_state or {}).get(key, False))

    def _set_card_collapsed_state(self, kind: str, device_id: str, collapsed: bool) -> None:
        key = self._card_state_key(kind, device_id)
        if not key:
            return
        try:
            self._card_collapse_state[key] = bool(collapsed)
        except Exception:
            pass

    def _make_card_collapse_callback(self, kind: str, device_id: str):
        def _cb(collapsed: bool) -> None:
            try:
                self._set_card_collapsed_state(kind, device_id, bool(collapsed))
            except Exception:
                pass
            try:
                card = (self._rendered_fx_cards or {}).get((str(kind or ''), str(device_id or '')))
                if card is not None:
                    self._queue_scroll_card_into_view(card)
            except Exception:
                pass
            try:
                self._sync_chain_host_size()
                self._update_zone_visuals()
                self._update_batch_action_button_state()
            except Exception:
                pass
        return _cb

    def _iter_device_cards(self) -> List[_DeviceCard]:
        cards: List[_DeviceCard] = []
        try:
            if getattr(self, "chain", None) is None:
                return cards
            for i in range(self.chain.count()):
                item = self.chain.itemAt(i)
                if item is None:
                    continue
                w = item.widget()
                if isinstance(w, _DeviceCard):
                    cards.append(w)
        except Exception:
            return cards
        return cards

    def _apply_batch_collapse(self, *, collapse_inactive_only: bool = False, expand_all: bool = False, collapse_all: bool = False) -> None:
        changed = False
        try:
            for card in self._iter_device_cards():
                if card is None:
                    continue
                target = None
                if expand_all:
                    target = False
                elif collapse_all:
                    target = True
                elif collapse_inactive_only:
                    is_enabled = bool(getattr(card, "_ui_enabled", True))
                    if not is_enabled:
                        target = True
                if target is None:
                    continue
                if bool(card.is_collapsed()) == bool(target):
                    continue
                try:
                    c_kind = str(getattr(card, "_collapse_state_kind", "") or "")
                    c_dev = str(getattr(card, "_collapse_state_device_id", "") or "")
                    if c_kind and c_dev:
                        self._set_card_collapsed_state(c_kind, c_dev, bool(target))
                except Exception:
                    pass
                try:
                    card.set_collapsed(bool(target), notify=False)
                    changed = True
                except Exception:
                    pass
        except Exception:
            pass
        if changed:
            try:
                self._sync_chain_host_size()
                self._update_zone_visuals()
            except Exception:
                pass
        try:
            if expand_all:
                self._set_batch_action_mode("expanded_all")
            elif collapse_all:
                self._set_batch_action_mode("collapsed_all")
            elif collapse_inactive_only:
                self._set_batch_action_mode("collapsed_inactive")
        except Exception:
            pass
        try:
            self._update_batch_action_button_state()
        except Exception:
            pass

    def _resolve_focus_card_for_batch_action(self) -> Optional[_DeviceCard]:
        """Return target card for focus batch action.

        Priority:
        1) currently selected FX card (note/audio)
        2) instrument anchor card (safe fallback)
        3) first visible device card
        """
        try:
            kind = str(getattr(self, "_selected_fx_kind", "") or "")
            did = str(getattr(self, "_selected_fx_device_id", "") or "")
            if kind and did:
                card = (self._rendered_fx_cards or {}).get((kind, did))
                if isinstance(card, _DeviceCard):
                    return card
        except Exception:
            pass
        try:
            inst = (self._zone_layout_meta or {}).get("inst_card")
            if isinstance(inst, _DeviceCard):
                return inst
        except Exception:
            pass
        try:
            cards = self._iter_device_cards()
            return cards[0] if cards else None
        except Exception:
            return None

    def _collapse_focus_device_cards(self) -> None:
        """UI-only focus view: keep one card expanded, collapse the rest."""
        target_card = self._resolve_focus_card_for_batch_action()
        if target_card is None:
            try:
                self._update_batch_action_button_state()
            except Exception:
                pass
            return
        changed = False
        try:
            for card in self._iter_device_cards():
                if card is None:
                    continue
                want_collapsed = bool(card is not target_card)
                if bool(card.is_collapsed()) == want_collapsed:
                    continue
                try:
                    c_kind = str(getattr(card, "_collapse_state_kind", "") or "")
                    c_dev = str(getattr(card, "_collapse_state_device_id", "") or "")
                    if c_kind and c_dev:
                        self._set_card_collapsed_state(c_kind, c_dev, want_collapsed)
                except Exception:
                    pass
                try:
                    card.set_collapsed(want_collapsed, notify=False)
                    changed = True
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if changed:
                self._sync_chain_host_size()
                self._update_zone_visuals()
            self._queue_scroll_card_into_view(target_card)
        except Exception:
            pass
        try:
            self._set_batch_action_mode("focus_card")
        except Exception:
            pass
        try:
            self._update_batch_action_button_state()
        except Exception:
            pass

    def _focus_only_zone_device_cards(self, zone_kind: str) -> None:
        """UI-only: collapse all cards except one zone (note_fx / instrument / audio_fx)."""
        try:
            zone_kind = str(zone_kind or "")
            if zone_kind not in ("note_fx", "instrument", "audio_fx"):
                return
            cards = self._iter_device_cards()
            if not cards:
                return
            zone_cards = [c for c in cards if str(getattr(c, "_collapse_state_kind", "") or "") == zone_kind]
            if not zone_cards:
                return
            target_card = getattr(self, "_focused_card", None)
            if target_card not in zone_cards:
                target_card = zone_cards[0]
            changed = False
            for card in cards:
                if card is None:
                    continue
                want_collapsed = bool(card not in zone_cards)
                if bool(card.is_collapsed()) == want_collapsed:
                    continue
                try:
                    c_kind = str(getattr(card, "_collapse_state_kind", "") or "")
                    c_dev = str(getattr(card, "_collapse_state_device_id", "") or "")
                    if c_kind and c_dev:
                        self._set_card_collapsed_state(c_kind, c_dev, want_collapsed)
                except Exception:
                    pass
                try:
                    card.set_collapsed(want_collapsed, notify=False)
                    changed = True
                except Exception:
                    pass
            try:
                if target_card is not None:
                    self._focused_card = target_card
            except Exception:
                pass
            try:
                if changed:
                    self._sync_chain_host_size()
                    self._update_zone_visuals()
                if target_card is not None:
                    self._queue_scroll_card_into_view(target_card)
            except Exception:
                pass
            try:
                self._set_batch_action_mode(f"zone:{zone_kind}")
            except Exception:
                pass
            try:
                self._update_batch_action_button_state()
            except Exception:
                pass
        except Exception:
            pass

    def _handle_escape_reset_shortcut(self) -> None:
        """UI-only comfort shortcut: Esc resets focus/zone/collapse view to normal."""
        try:
            cards = self._iter_device_cards()
            if not cards:
                return
            has_collapsed = any(bool(c.is_collapsed()) for c in cards)
            mode = str(getattr(self, "_batch_action_mode", "") or "")
            has_focus_mode = bool(mode == "focus_card" or mode.startswith("zone:"))
            if not (has_collapsed or has_focus_mode):
                return
        except Exception:
            return
        try:
            self._reset_normal_device_view()
        except Exception:
            pass
    def _handle_batch_mode_badge_left_click(self) -> None:
        """Header badge comfort action: reset active mode, else open mini-help."""
        try:
            mode = str(getattr(self, "_batch_action_mode", "") or "")
            if mode:
                self._reset_normal_device_view()
                return
        except Exception:
            pass
        try:
            self._show_batch_legend_popup()
        except Exception:
            pass

    def _show_batch_mode_badge_menu(self, global_pos=None) -> None:  # noqa: ANN001
        """Optional quick menu for the batch mode badge (UI-only)."""
        try:
            menu = QMenu(self)
            a_reset = menu.addAction("↺ Normalansicht / Reset")
            menu.addSeparator()
            a_focus = menu.addAction("◎ Nur fokussierte Card offen")
            a_note = menu.addAction("N Nur NOTE-FX offen")
            a_inst = menu.addAction("I Nur INSTRUMENT offen")
            a_audio = menu.addAction("A Nur AUDIO-FX offen")
            menu.addSeparator()
            a_inactive = menu.addAction("◪ Inaktive einklappen")
            a_collapse = menu.addAction("▾▾ Alle einklappen")
            a_expand = menu.addAction("▸▸ Alle ausklappen")
            menu.addSeparator()
            a_help = menu.addAction("? Kurzhilfe anzeigen")

            mode = str(getattr(self, "_batch_action_mode", "") or "")
            try:
                a_reset.setEnabled(bool(mode) or any(bool(c.is_collapsed()) for c in self._iter_device_cards()))
            except Exception:
                pass
            try:
                a_focus.setCheckable(True); a_focus.setChecked(mode == "focus_card")
                a_note.setCheckable(True); a_note.setChecked(mode == "zone:note_fx")
                a_inst.setCheckable(True); a_inst.setChecked(mode == "zone:instrument")
                a_audio.setCheckable(True); a_audio.setChecked(mode == "zone:audio_fx")
            except Exception:
                pass

            chosen = menu.exec(global_pos) if global_pos is not None else menu.exec(self.mapToGlobal(self.rect().center()))
            if chosen is None:
                return
            if chosen == a_reset:
                self._reset_normal_device_view()
            elif chosen == a_focus:
                self._collapse_focus_device_cards()
            elif chosen == a_note:
                self._focus_only_zone_device_cards("note_fx")
            elif chosen == a_inst:
                self._focus_only_zone_device_cards("instrument")
            elif chosen == a_audio:
                self._focus_only_zone_device_cards("audio_fx")
            elif chosen == a_inactive:
                self._collapse_inactive_device_cards()
            elif chosen == a_collapse:
                self._collapse_all_device_cards()
            elif chosen == a_expand:
                self._expand_all_device_cards()
            elif chosen == a_help:
                self._show_batch_legend_popup()
        except Exception:
            pass

    def _reset_normal_device_view(self) -> None:
        """UI-only reset: all zones visible, all rendered cards expanded."""
        changed = False
        try:
            for card in self._iter_device_cards():
                if card is None:
                    continue
                if not bool(card.is_collapsed()):
                    continue
                try:
                    c_kind = str(getattr(card, "_collapse_state_kind", "") or "")
                    c_dev = str(getattr(card, "_collapse_state_device_id", "") or "")
                    if c_kind and c_dev:
                        self._set_card_collapsed_state(c_kind, c_dev, False)
                except Exception:
                    pass
                try:
                    card.set_collapsed(False, notify=False)
                    changed = True
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if changed:
                self._sync_chain_host_size()
                self._update_zone_visuals()
        except Exception:
            pass
        try:
            self._set_batch_action_mode("")
        except Exception:
            pass
        try:
            self._update_batch_action_button_state()
        except Exception:
            pass

    def _collapse_inactive_device_cards(self) -> None:
        self._apply_batch_collapse(collapse_inactive_only=True)

    def _collapse_all_device_cards(self) -> None:
        self._apply_batch_collapse(collapse_all=True)

    def _expand_all_device_cards(self) -> None:
        self._apply_batch_collapse(expand_all=True)

    def _sync_chain_host_size(self) -> None:
        """Keep device-chain host at content width so horizontal scrolling works.

        Without this, Qt shrinks all cards into the viewport width and the UI becomes
        unreadable when many FX are chained.
        """
        try:
            if not hasattr(self, 'scroll') or not hasattr(self, 'chain_host'):
                return
            vp = self.scroll.viewport().size() if self.scroll.viewport() is not None else QSize(0, 0)
            layout_hint = self.chain.sizeHint() if self.chain is not None else QSize(0, 0)
            host_hint = self.chain_host.sizeHint()
            content_w = max(int(layout_hint.width()), int(host_hint.width()), 1)
            content_h = max(int(layout_hint.height()), int(host_hint.height()), 1)
            target_w = max(content_w, int(vp.width()))
            target_h = max(content_h, int(vp.height()))
            self.chain_host.resize(target_w, target_h)
            self.chain_host.setMinimumSize(content_w, target_h)
            self.chain_host.updateGeometry()
        except Exception:
            pass

    # ----------------- public API -----------------

    def show_track(self, track_id: str) -> None:
        self._current_track = str(track_id or "")
        self._nav_stack.clear()  # v0.0.20.554: reset zoom on track change
        self._breadcrumb_bar.setVisible(False)
        self._safe_render_current_track()

    # v0.0.20.554: Bitwig-style container zoom --------------------------------

    def zoom_into_layer(self, track_id: str, device_id: str,
                        layer_index: int, layer_name: str = "") -> None:
        """Zoom into an instrument layer — shows layer's instrument + FX chain."""
        self._nav_stack.append({
            "type": "layer",
            "track_id": str(track_id),
            "device_id": str(device_id),
            "layer_index": int(layer_index),
            "layer_name": str(layer_name or f"Layer {layer_index + 1}"),
        })
        self._update_breadcrumb()
        self._safe_render_current_track()

    def zoom_into_fx_layer(self, track_id: str, device_id: str,
                            layer_index: int, layer_name: str = "") -> None:
        """v0.0.20.562: Zoom into an FX layer — shows layer's FX devices."""
        self._nav_stack.append({
            "type": "fx_layer",
            "track_id": str(track_id),
            "device_id": str(device_id),
            "layer_index": int(layer_index),
            "layer_name": str(layer_name or f"Layer {layer_index + 1}"),
        })
        self._update_breadcrumb()
        self._safe_render_current_track()

    def zoom_into_chain(self, track_id: str, device_id: str) -> None:
        """v0.0.20.562: Zoom into a chain container — shows chain's FX devices."""
        self._nav_stack.append({
            "type": "chain",
            "track_id": str(track_id),
            "device_id": str(device_id),
        })
        self._update_breadcrumb()
        self._safe_render_current_track()

    def zoom_out(self) -> None:
        """Go back one level in the container navigation."""
        if self._nav_stack:
            self._nav_stack.pop()
        self._update_breadcrumb()
        self._safe_render_current_track()

    def _update_breadcrumb(self) -> None:
        """Update the breadcrumb bar visibility and text."""
        try:
            if not self._nav_stack:
                self._breadcrumb_bar.setVisible(False)
                return
            self._breadcrumb_bar.setVisible(True)
            parts = []
            for ctx in self._nav_stack:
                ctype = ctx.get("type", "")
                if ctype == "layer":
                    parts.append(f"Instrument Layer › {ctx.get('layer_name', '?')}")
                elif ctype == "fx_layer":
                    parts.append(f"FX Layer › {ctx.get('layer_name', '?')}")
                elif ctype == "chain":
                    parts.append(f"Chain (Seriell)")
            self._breadcrumb_label.setText("  ›  ".join(parts))
        except Exception:
            pass

    def _get_layer_context(self) -> dict | None:
        """Return the current zoom context if we're zoomed in, else None.
        Works for all container types: layer, fx_layer, chain."""
        if self._nav_stack and self._nav_stack[-1].get("type") in ("layer", "fx_layer", "chain"):
            return self._nav_stack[-1]
        return None

    def _show_layer_add_fx_menu(self) -> None:
        """Show a popup menu to add Audio-FX inside the current zoomed layer."""
        try:
            from PySide6.QtGui import QCursor
            ctx = self._get_layer_context()
            if ctx is None:
                return
            track_id = str(ctx.get("track_id") or "")
            device_id = str(ctx.get("device_id") or "")
            layer_index = int(ctx.get("layer_index", 0))
            ctype = str(ctx.get("type") or "")

            menu = QMenu(self)
            menu.setStyleSheet("QMenu { font-size: 11px; min-width: 200px; }")
            actions = self._build_full_fx_menu(menu)

            if not actions:
                menu.addAction("(keine FX verfügbar)").setEnabled(False)

            chosen = menu.exec(QCursor.pos())
            if chosen is None:
                return
            for a, pid, name in actions:
                if chosen == a:
                    if ctype == "chain":
                        # Chain: add to chain devices list
                        devs = self._get_chain_devices_list(track_id, device_id)
                        if devs is not None:
                            devs.append({
                                "id": new_id("afx"), "plugin_id": pid,
                                "name": name or pid.split(".")[-1],
                                "enabled": True, "params": {},
                            })
                            self._emit_layer_update()
                            self._safe_render_current_track()
                    else:
                        # Layer: add to layer devices list
                        self._add_fx_to_layer(track_id, device_id, layer_index, pid, name)
                    break
        except Exception:
            import traceback
            traceback.print_exc()

    def _build_full_fx_menu(self, menu: QMenu) -> list:
        """v0.0.20.565: Build a complete FX menu with Built-in + External plugins.

        Returns list of (QAction, plugin_id, name) tuples.
        Used by both layer and chain add-FX menus.
        """
        actions = []

        # --- Built-in FX ---
        try:
            menu.addSection("🔊 Built-in Audio-FX")
            from pydaw.ui.fx_specs import get_audio_fx
            for spec in (get_audio_fx() or []):
                name = str(getattr(spec, "name", "") or "")
                pid = str(getattr(spec, "plugin_id", "") or "")
                if name and pid:
                    a = menu.addAction(f"  🔊 {name}")
                    actions.append((a, pid, name))
        except Exception:
            pass

        # --- External FX from plugin cache ---
        try:
            from pydaw.services import plugin_scanner
            cache = plugin_scanner.load_cache() or {}
            _format_labels = {
                "lv2": "🔌 LV2", "ladspa": "🔌 LADSPA", "dssi": "🔌 DSSI",
                "vst2": "🔌 VST2", "vst3": "🔌 VST3", "clap": "🔌 CLAP",
            }
            for kind in ("vst3", "clap", "vst2", "lv2", "dssi", "ladspa"):
                plugins = cache.get(kind, []) or []
                # FX = everything that is NOT an instrument
                fx_plugins = [p for p in plugins if not getattr(p, "is_instrument", False)]
                if not fx_plugins:
                    continue
                label = _format_labels.get(kind, kind.upper())
                sub = menu.addMenu(f"{label} ({len(fx_plugins)})")
                sub.setStyleSheet("QMenu { font-size: 11px; max-height: 600px; }")
                # Split into columns of 40 for readability
                if len(fx_plugins) > 40:
                    for col_start in range(0, len(fx_plugins), 40):
                        chunk = fx_plugins[col_start:col_start + 40]
                        first_name = str(getattr(chunk[0], "name", "?") or "?")[:12]
                        last_name = str(getattr(chunk[-1], "name", "?") or "?")[:12]
                        col_sub = sub.addMenu(f"{first_name} … {last_name}")
                        col_sub.setStyleSheet("QMenu { font-size: 11px; }")
                        for p in chunk:
                            p_name = str(getattr(p, "name", "") or "")
                            p_pid = str(getattr(p, "plugin_id", "") or "")
                            if p_name and p_pid:
                                ext_pid = f"ext.{kind}:{p_pid}"
                                a = col_sub.addAction(f"  {p_name}")
                                actions.append((a, ext_pid, p_name))
                else:
                    for p in fx_plugins:
                        p_name = str(getattr(p, "name", "") or "")
                        p_pid = str(getattr(p, "plugin_id", "") or "")
                        if p_name and p_pid:
                            ext_pid = f"ext.{kind}:{p_pid}"
                            a = sub.addAction(f"  {p_name}")
                            actions.append((a, ext_pid, p_name))
        except Exception:
            pass

        return actions

    def _add_fx_to_layer(self, track_id: str, device_id: str,
                          layer_index: int, plugin_id: str, name: str) -> None:
        """Add an audio FX device to a specific layer inside a container."""
        try:
            proj, project_obj, trk = self._get_project_track(track_id)
            if trk is None:
                return
            chain = getattr(trk, "audio_fx_chain", None)
            if not isinstance(chain, dict):
                return
            for dev in (chain.get("devices") or []):
                if not isinstance(dev, dict):
                    continue
                if str(dev.get("id") or "") == device_id or \
                   str(dev.get("plugin_id") or "") == "chrono.container.instrument_layer":
                    layers = dev.get("layers") or []
                    if 0 <= layer_index < len(layers):
                        devs = layers[layer_index].setdefault("devices", [])
                        devs.append({
                            "id": new_id("afx"),
                            "plugin_id": plugin_id,
                            "name": name or plugin_id.split(".")[-1],
                            "enabled": True,
                            "params": {},
                        })
                        # Refresh zoom view
                        try:
                            ps = getattr(self._services, "project", None)
                            if ps is not None and hasattr(ps, "_emit_updated"):
                                ps._emit_updated()
                        except Exception:
                            pass
                        self._safe_render_current_track()
                        return
        except Exception:
            import traceback
            traceback.print_exc()

    def _get_layer_devices_list(self, track_id: str, device_id: str,
                                 layer_index: int) -> list | None:
        """Return the mutable devices list for a specific layer, or None."""
        try:
            proj, project_obj, trk = self._get_project_track(track_id)
            if trk is None:
                return None
            chain = getattr(trk, "audio_fx_chain", None)
            if not isinstance(chain, dict):
                return None
            for dev in (chain.get("devices") or []):
                if not isinstance(dev, dict):
                    continue
                if str(dev.get("id") or "") == device_id or \
                   str(dev.get("plugin_id") or "") == "chrono.container.instrument_layer":
                    layers = dev.get("layers") or []
                    if 0 <= layer_index < len(layers):
                        return layers[layer_index].setdefault("devices", [])
        except Exception:
            pass
        return None

    def _layer_move_fx(self, track_id: str, device_id: str,
                        layer_index: int, fx_index: int, direction: int) -> None:
        """v0.0.20.561: Reorder FX device within a layer."""
        try:
            devs = self._get_layer_devices_list(track_id, device_id, layer_index)
            if devs is None:
                return
            new_idx = fx_index + direction
            if 0 <= fx_index < len(devs) and 0 <= new_idx < len(devs):
                devs[fx_index], devs[new_idx] = devs[new_idx], devs[fx_index]
                self._emit_layer_update()
                self._safe_render_current_track()
        except Exception:
            import traceback
            traceback.print_exc()

    def _layer_toggle_fx(self, track_id: str, device_id: str,
                          layer_index: int, fx_index: int) -> None:
        """v0.0.20.561: Toggle enable/disable for a layer FX device."""
        try:
            devs = self._get_layer_devices_list(track_id, device_id, layer_index)
            if devs is None:
                return
            if 0 <= fx_index < len(devs) and isinstance(devs[fx_index], dict):
                devs[fx_index]["enabled"] = not bool(devs[fx_index].get("enabled", True))
                self._emit_layer_update()
                self._safe_render_current_track()
        except Exception:
            import traceback
            traceback.print_exc()

    def _layer_remove_fx(self, track_id: str, device_id: str,
                          layer_index: int, fx_index: int) -> None:
        """v0.0.20.561: Remove FX device from a layer."""
        try:
            devs = self._get_layer_devices_list(track_id, device_id, layer_index)
            if devs is None:
                return
            if 0 <= fx_index < len(devs):
                devs.pop(fx_index)
                self._emit_layer_update()
                self._safe_render_current_track()
        except Exception:
            import traceback
            traceback.print_exc()

    def _emit_layer_update(self) -> None:
        """Emit project updated signal after layer mutation."""
        try:
            ps = getattr(self._services, "project", None)
            if ps is not None and hasattr(ps, "_emit_updated"):
                ps._emit_updated()
        except Exception:
            pass

    # v0.0.20.562: Chain container zoom management methods

    def _get_chain_devices_list(self, track_id: str, device_id: str) -> list | None:
        """Return the mutable devices list for a chain container, or None."""
        try:
            proj, project_obj, trk = self._get_project_track(track_id)
            if trk is None:
                return None
            chain = getattr(trk, "audio_fx_chain", None)
            if not isinstance(chain, dict):
                return None
            for dev in (chain.get("devices") or []):
                if not isinstance(dev, dict):
                    continue
                if str(dev.get("id") or "") == device_id or \
                   str(dev.get("plugin_id") or "") == "chrono.container.chain":
                    return dev.setdefault("devices", [])
        except Exception:
            pass
        return None

    def _chain_move_fx(self, track_id: str, device_id: str,
                        fx_index: int, direction: int) -> None:
        try:
            devs = self._get_chain_devices_list(track_id, device_id)
            if devs is None:
                return
            new_idx = fx_index + direction
            if 0 <= fx_index < len(devs) and 0 <= new_idx < len(devs):
                devs[fx_index], devs[new_idx] = devs[new_idx], devs[fx_index]
                self._emit_layer_update()
                self._safe_render_current_track()
        except Exception:
            pass

    def _chain_toggle_fx(self, track_id: str, device_id: str, fx_index: int) -> None:
        try:
            devs = self._get_chain_devices_list(track_id, device_id)
            if devs is None:
                return
            if 0 <= fx_index < len(devs) and isinstance(devs[fx_index], dict):
                devs[fx_index]["enabled"] = not bool(devs[fx_index].get("enabled", True))
                self._emit_layer_update()
                self._safe_render_current_track()
        except Exception:
            pass

    def _chain_remove_fx(self, track_id: str, device_id: str, fx_index: int) -> None:
        try:
            devs = self._get_chain_devices_list(track_id, device_id)
            if devs is None:
                return
            if 0 <= fx_index < len(devs):
                devs.pop(fx_index)
                self._emit_layer_update()
                self._safe_render_current_track()
        except Exception:
            pass

    def _show_chain_add_fx_menu(self) -> None:
        """v0.0.20.565: Delegate to unified _show_layer_add_fx_menu (handles chain type)."""
        self._show_layer_add_fx_menu()

    # --------------------------------------------------------------------------

    def has_device_for_track(self, track_id: str) -> bool:
        return bool(self._track_instruments.get(str(track_id or "")))

    def get_track_devices(self, track_id: str) -> list:
        """Return instrument widgets for this track (used by mixer routing / VU)."""
        tid = str(track_id or "")
        ent = self._track_instruments.get(tid)
        if ent and ent.get("widget") is not None:
            return [ent["widget"]]
        return []

    def remove_track_devices(self, track_id: str) -> None:
        tid = str(track_id or "")
        try:
            self._remove_instrument(tid)
        except Exception:
            pass

    def add_instrument(self, plugin_id: str) -> bool:
        """Add instrument to CURRENT track (compat helper)."""
        if not self._current_track:
            return False
        return self.add_instrument_to_track(self._current_track, plugin_id)

    def add_instrument_to_track(self, track_id: str, plugin_id: str) -> bool:
        track_id = str(track_id or "")
        plugin_id = (plugin_id or "").strip()
        if not track_id or not plugin_id:
            return False

        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or project_obj is None or trk is None:
            return False

        instruments = {i.plugin_id: i for i in get_instruments()}
        spec = instruments.get(plugin_id)
        if spec is None:
            return False

        # Update model
        try:
            trk.plugin_type = plugin_id
            # If we switch away from SF2 routing, clear any lingering SF2 metadata
            # so the anchor doesn't show stale soundfont info.
            if hasattr(trk, "sf2_path"):
                trk.sf2_path = ""
            if hasattr(trk, "sf2_bank"):
                trk.sf2_bank = 0
            if hasattr(trk, "sf2_preset"):
                trk.sf2_preset = 0
        except Exception:
            pass

        # Build/replace widget
        self._create_or_replace_instrument_widget(track_id, plugin_id, spec)

        self._emit_project_updated()
        return True

    # ---- FX API (called by DnD and by Browser "Add")

    def add_note_fx_to_track(
        self,
        track_id: str,
        plugin_id: str,
        *,
        insert_index: int = -1,
        name: str = "",
        params: Optional[Dict[str, Any]] = None,
        defer_emit: bool = False,
        defer_restart: bool = False,
    ) -> bool:
        track_id = str(track_id or "")
        plugin_id = str(plugin_id or "").strip()
        if not track_id or not plugin_id:
            return False

        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or project_obj is None or trk is None:
            return False

        chain = getattr(trk, "note_fx_chain", None)
        if not isinstance(chain, dict):
            trk.note_fx_chain = {"devices": []}
            chain = trk.note_fx_chain

        dev_id = new_id("nfx")
        defaults = {}
        try:
            from .fx_specs import get_note_fx
            spec = next((s for s in get_note_fx() if s.plugin_id == plugin_id), None)
            if spec is not None:
                defaults = dict(spec.defaults)
        except Exception:
            defaults = {}

        # Merge safe extra params (e.g. external plugin metadata)
        extra_params: Dict[str, Any] = params if isinstance(params, dict) else {}
        try:
            defaults.update(extra_params)
        except Exception:
            pass

        # LV2 insert: make audible by default (SAFE heuristic)
        # Many LV2 plugins ship with BYPASS enabled or very dry defaults.
        # We only tweak a few well-known controls (e.g. BYPASS, wet_dry) on INSERT.
        if plugin_id.startswith("ext.lv2:"):
            try:
                from pydaw.audio import lv2_host
                uri = plugin_id.split(":", 1)[1] if ":" in plugin_id else ""
                if uri and lv2_host.is_available():
                    ctrls = lv2_host.describe_controls(uri)
                    for c in (ctrls or []):
                        try:
                            sym = str(getattr(c, "symbol", "") or "")
                            if not sym:
                                continue
                            key = sym.lower()
                            mn = float(getattr(c, "minimum", 0.0))
                            mx = float(getattr(c, "maximum", mn + 1.0))
                            # BYPASS: prefer off (= minimum)
                            if "bypass" in key and sym not in defaults:
                                defaults[sym] = mn
                            # Dry/Wet faders are inconsistent across plugins.
                            # Best-effort: set towards "wet" so the effect is audible.
                            if ("dry_wet" in key or "drywet" in key) and sym not in defaults:
                                defaults[sym] = mx
                            if ("wet_dry" in key or "wetdry" in key) and sym not in defaults:
                                defaults[sym] = mn
                        except Exception:
                            continue
            except Exception:
                pass

        dev_name = str(name or "").strip() or plugin_id.split(".")[-1]

        new_dev = {
            "id": dev_id,
            "plugin_id": plugin_id,
            "name": dev_name,
            "enabled": True,
            "params": defaults,
        }

        chain.setdefault("devices", [])
        devs = chain["devices"]
        if 0 <= insert_index <= len(devs):
            devs.insert(insert_index, new_dev)
        else:
            devs.append(new_dev)

        self._set_pending_fx_focus("note_fx", dev_id)

        if not bool(defer_restart):
            self._restart_if_playing()
        if not bool(defer_emit):
            self._emit_project_updated()
        return True

    def add_audio_fx_to_track(
        self,
        track_id: str,
        plugin_id: str,
        *,
        insert_index: int = -1,
        name: str = "",
        params: Optional[Dict[str, Any]] = None,
        defer_emit: bool = False,
        defer_restart: bool = False,
        defer_rebuild: bool = False,
    ) -> bool:
        track_id = str(track_id or "")
        plugin_id = str(plugin_id or "").strip()
        if not track_id or not plugin_id:
            return False

        # v0.0.20.531: Route container plugin_ids to dedicated methods
        if plugin_id == "chrono.container.fx_layer":
            return self.add_fx_layer_to_track(track_id, insert_index=insert_index)
        if plugin_id == "chrono.container.chain":
            return self.add_chain_container_to_track(track_id, insert_index=insert_index)
        # v0.0.20.536: Instrument Layer
        if plugin_id == "chrono.container.instrument_layer":
            return self.add_instrument_layer_to_track(track_id, insert_index=insert_index)

        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or project_obj is None or trk is None:
            return False

        chain = getattr(trk, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            trk.audio_fx_chain = {"type": "chain", "mix": 1.0, "wet_gain": 1.0, "devices": []}
            chain = trk.audio_fx_chain

        dev_id = new_id("afx")
        defaults = {}
        try:
            from .fx_specs import get_audio_fx
            spec = next((s for s in get_audio_fx() if s.plugin_id == plugin_id), None)
            if spec is not None:
                defaults = dict(spec.defaults)
        except Exception:
            defaults = {}

        # Merge safe extra params (e.g. external plugin metadata)
        extra_params: Dict[str, Any] = dict(params) if isinstance(params, dict) else {}

        # External VST safety: always persist the *exact* plugin reference as
        # one canonical field. Some UI paths only had base path + sub-plugin,
        # others only the encoded plugin_id reference. Keeping all three makes
        # insertion, project reload and browser/device round-trips robust.
        if plugin_id.startswith("ext.vst3:") or plugin_id.startswith("ext.vst2:"):
            try:
                from pydaw.audio.vst3_host import build_plugin_reference, split_plugin_reference
                raw_ref = plugin_id.split(":", 1)[1] if ":" in plugin_id else plugin_id
                ref_path, ref_name = split_plugin_reference(raw_ref)
                ext_path = str(extra_params.get("__ext_path") or ref_path or raw_ref or "")
                ext_name = str(extra_params.get("__ext_plugin_name") or ref_name or "")
                ext_ref = str(extra_params.get("__ext_ref") or raw_ref or "")
                if ext_path and ext_name:
                    ext_ref = build_plugin_reference(ext_path, ext_name)
                elif ext_path and not ext_ref:
                    ext_ref = ext_path
                if ext_ref:
                    extra_params["__ext_ref"] = ext_ref
                if ext_path:
                    extra_params["__ext_path"] = ext_path
                if ext_name:
                    extra_params["__ext_plugin_name"] = ext_name
            except Exception:
                pass

        # External CLAP safety: persist exact reference (path::plugin_id)
        if plugin_id.startswith("ext.clap:"):
            try:
                from pydaw.audio.clap_host import build_plugin_reference, split_plugin_reference
                raw_ref = plugin_id.split(":", 1)[1] if ":" in plugin_id else plugin_id
                ref_path, ref_name = split_plugin_reference(raw_ref)
                ext_path = str(extra_params.get("__ext_path") or ref_path or raw_ref or "")
                ext_name = str(extra_params.get("__ext_plugin_name") or ref_name or "")
                ext_ref = str(extra_params.get("__ext_ref") or raw_ref or "")
                if ext_path and ext_name:
                    ext_ref = build_plugin_reference(ext_path, ext_name)
                elif ext_path and not ext_ref:
                    ext_ref = ext_path
                if ext_ref:
                    extra_params["__ext_ref"] = ext_ref
                if ext_path:
                    extra_params["__ext_path"] = ext_path
                if ext_name:
                    extra_params["__ext_plugin_name"] = ext_name
            except Exception:
                pass

        try:
            defaults.update(extra_params)
        except Exception:
            pass

        # LV2 insert: make audible by default (SAFE heuristic)
        # Many LV2 plugins ship with BYPASS enabled or very dry defaults.
        # We only tweak a few well-known controls (e.g. BYPASS, wet_dry) on INSERT.
        if plugin_id.startswith("ext.lv2:"):
            try:
                from pydaw.audio import lv2_host
                uri = plugin_id.split(":", 1)[1] if ":" in plugin_id else ""
                if uri and lv2_host.is_available():
                    ctrls = lv2_host.describe_controls(uri)
                    for c in (ctrls or []):
                        try:
                            sym = str(getattr(c, "symbol", "") or "")
                            if not sym:
                                continue
                            key = sym.lower()
                            mn = float(getattr(c, "minimum", 0.0))
                            mx = float(getattr(c, "maximum", mn + 1.0))
                            # BYPASS: prefer off (= minimum)
                            if "bypass" in key and sym not in defaults:
                                defaults[sym] = mn
                            # Dry/Wet faders are inconsistent across plugins.
                            # Best-effort: set towards "wet" so the effect is audible.
                            if ("dry_wet" in key or "drywet" in key) and sym not in defaults:
                                defaults[sym] = mx
                            if ("wet_dry" in key or "wetdry" in key) and sym not in defaults:
                                defaults[sym] = mn
                        except Exception:
                            continue
            except Exception:
                pass

        dev_name = str(name or "").strip() or plugin_id.split(".")[-1]

        new_dev = {
            "id": dev_id,
            "plugin_id": plugin_id,
            "name": dev_name,
            "enabled": True,
            "params": defaults,
        }

        chain.setdefault("devices", [])
        devs = chain["devices"]
        if 0 <= insert_index <= len(devs):
            devs.insert(insert_index, new_dev)
        else:
            devs.append(new_dev)

        self._set_pending_fx_focus("audio_fx", dev_id)
        if not bool(defer_rebuild):
            self._rebuild_audio_fx(project_obj)
        if not bool(defer_restart):
            self._restart_if_playing()
        if not bool(defer_emit):
            self._emit_project_updated()
        return True

    # ---- Device Containers (v0.0.20.530) ----

    def add_fx_layer_to_track(self, track_id: str, *, insert_index: int = -1, num_layers: int = 2) -> bool:
        """Add an FX Layer container (parallel processing) to the audio FX chain.

        Creates N empty layers that the user can fill with devices.
        """
        track_id = str(track_id or "")
        if not track_id:
            return False
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or trk is None:
            return False

        chain = getattr(trk, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            trk.audio_fx_chain = {"type": "chain", "mix": 1.0, "wet_gain": 1.0, "devices": []}
            chain = trk.audio_fx_chain

        dev_id = new_id("afx")
        layers = []
        for i in range(max(1, min(8, num_layers))):
            layers.append({
                "name": f"Layer {i + 1}",
                "enabled": True,
                "volume": 1.0,
                "devices": [],
            })

        new_dev = {
            "id": dev_id,
            "plugin_id": "chrono.container.fx_layer",
            "name": "FX Layer",
            "enabled": True,
            "params": {"mix": 1.0},
            "layers": layers,
        }

        devs = chain.setdefault("devices", [])
        if 0 <= insert_index <= len(devs):
            devs.insert(insert_index, new_dev)
        else:
            devs.append(new_dev)

        self._set_pending_fx_focus("audio_fx", dev_id)
        self._rebuild_audio_fx(project_obj)
        self._restart_if_playing()
        self._emit_project_updated()
        return True

    def add_chain_container_to_track(self, track_id: str, *, insert_index: int = -1) -> bool:
        """Add a Chain container (serial sub-chain) to the audio FX chain.

        Creates an empty sub-chain that the user can fill with devices.
        """
        track_id = str(track_id or "")
        if not track_id:
            return False
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or trk is None:
            return False

        chain = getattr(trk, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            trk.audio_fx_chain = {"type": "chain", "mix": 1.0, "wet_gain": 1.0, "devices": []}
            chain = trk.audio_fx_chain

        dev_id = new_id("afx")
        new_dev = {
            "id": dev_id,
            "plugin_id": "chrono.container.chain",
            "name": "Chain",
            "enabled": True,
            "params": {"mix": 1.0},
            "devices": [],
        }

        devs = chain.setdefault("devices", [])
        if 0 <= insert_index <= len(devs):
            devs.insert(insert_index, new_dev)
        else:
            devs.append(new_dev)

        self._set_pending_fx_focus("audio_fx", dev_id)
        self._rebuild_audio_fx(project_obj)
        self._restart_if_playing()
        self._emit_project_updated()
        return True

    def add_instrument_layer_to_track(self, track_id: str, *, insert_index: int = -1, num_layers: int = 2) -> bool:
        """v0.0.20.536: Add an Instrument Layer (Stack) container to the audio FX chain.

        Creates N empty layers, each with instrument + per-layer FX slots.
        """
        track_id = str(track_id or "")
        if not track_id:
            return False
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or trk is None:
            return False

        chain = getattr(trk, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            trk.audio_fx_chain = {"type": "chain", "mix": 1.0, "wet_gain": 1.0, "devices": []}
            chain = trk.audio_fx_chain

        dev_id = new_id("afx")
        layers = []
        for i in range(min(max(1, int(num_layers)), 8)):
            layers.append({
                "name": f"Layer {i+1}",
                "enabled": True,
                "volume": 1.0,
                "instrument": "",
                "instrument_name": "",
                "devices": [],
            })

        new_dev = {
            "id": dev_id,
            "plugin_id": "chrono.container.instrument_layer",
            "name": "Instrument Layer",
            "enabled": True,
            "params": {"mix": 1.0},
            "layers": layers,
        }

        devs = chain.setdefault("devices", [])
        if 0 <= insert_index <= len(devs):
            devs.insert(insert_index, new_dev)
        else:
            devs.append(new_dev)

        self._set_pending_fx_focus("audio_fx", dev_id)
        self._rebuild_audio_fx(project_obj)
        self._restart_if_playing()
        self._emit_project_updated()
        return True

    def add_device_to_container(self, track_id: str, container_device_id: str,
                                 plugin_id: str, *, layer_index: int = 0,
                                 name: str = "", params: Optional[Dict[str, Any]] = None) -> bool:
        """Add a device inside an existing container (FX Layer layer or Chain sub-chain).

        For FX Layer: layer_index selects which layer to add to.
        For Chain: layer_index is ignored (single device list).
        """
        track_id = str(track_id or "")
        container_device_id = str(container_device_id or "")
        plugin_id = str(plugin_id or "").strip()
        if not track_id or not container_device_id or not plugin_id:
            return False

        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or trk is None:
            return False

        chain = getattr(trk, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return False

        # Find the container device
        container = None
        for dev in (chain.get("devices", []) or []):
            if isinstance(dev, dict) and str(dev.get("id", "")) == container_device_id:
                container = dev
                break
        if container is None:
            return False

        cpid = str(container.get("plugin_id", ""))
        dev_id = new_id("afx")
        new_dev = {
            "id": dev_id,
            "plugin_id": plugin_id,
            "name": str(name or plugin_id.split(".")[-1]),
            "enabled": True,
            "params": dict(params) if isinstance(params, dict) else {},
        }

        if cpid == "chrono.container.fx_layer":
            layers = container.get("layers", []) or []
            idx = max(0, min(len(layers) - 1, int(layer_index)))
            if idx < len(layers):
                layers[idx].setdefault("devices", []).append(new_dev)
            else:
                return False
        elif cpid == "chrono.container.chain":
            container.setdefault("devices", []).append(new_dev)
        else:
            return False

        self._rebuild_audio_fx(project_obj)
        self._restart_if_playing()
        self._emit_project_updated()
        return True

    def remove_note_fx_device(self, track_id: str, device_id: str) -> None:
        track_id = str(track_id or "")
        device_id = str(device_id or "")
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or trk is None:
            return
        chain = getattr(trk, "note_fx_chain", None)
        if not isinstance(chain, dict):
            return
        devs = chain.get("devices", []) or []
        chain["devices"] = [d for d in devs if not (isinstance(d, dict) and str(d.get("id","")) == device_id)]
        if self._selected_fx_kind == "note_fx" and self._selected_fx_device_id == device_id:
            self._selected_fx_kind = ""
            self._selected_fx_device_id = ""
        self._restart_if_playing()
        self._emit_project_updated()

    def remove_audio_fx_device(self, track_id: str, device_id: str) -> None:
        track_id = str(track_id or "")
        device_id = str(device_id or "")
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or project_obj is None or trk is None:
            return
        chain = getattr(trk, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return
        devs = chain.get("devices", []) or []
        chain["devices"] = [d for d in devs if not (isinstance(d, dict) and str(d.get("id","")) == device_id)]
        if self._selected_fx_kind == "audio_fx" and self._selected_fx_device_id == device_id:
            self._selected_fx_kind = ""
            self._selected_fx_device_id = ""
        self._rebuild_audio_fx(project_obj)
        self._restart_if_playing()
        self._emit_project_updated()

    # ---- v0.0.20.531: Right-click context menu on chain area ----

    def _show_chain_context_menu(self, global_pos) -> None:
        """Show context menu for adding containers and built-in FX to the chain."""
        try:
            tid = self._current_track
            if not tid:
                return

            menu = QMenu(self)
            menu.setStyleSheet("QMenu { font-size: 10px; }")

            # Container section
            menu.addSection("📦 Container")
            a_layer = menu.addAction("⧉ FX Layer (Parallel)")
            a_chain = menu.addAction("⟐ Chain (Seriell)")
            a_inst_layer = menu.addAction("🎹 Instrument Layer (Stack)")

            # Built-in Audio-FX
            menu.addSection("🎚️ Audio-FX")
            fx_actions = []
            try:
                from .fx_specs import get_audio_fx
                for spec in (get_audio_fx() or []):
                    name = str(getattr(spec, "name", "") or "")
                    pid = str(getattr(spec, "plugin_id", "") or "")
                    if name and pid:
                        a = menu.addAction(f"  {name}")
                        fx_actions.append((a, pid, name))
            except Exception:
                pass

            chosen = menu.exec(global_pos)
            if chosen is None:
                return

            if chosen == a_layer:
                self.add_fx_layer_to_track(tid)
            elif chosen == a_chain:
                self.add_chain_container_to_track(tid)
            elif chosen == a_inst_layer:
                self.add_instrument_layer_to_track(tid)
            else:
                for a, pid, name in fx_actions:
                    if chosen == a:
                        self.add_audio_fx_to_track(tid, pid, name=name)
                        break
        except Exception:
            pass

    # ----------------- DnD plumbing -----------------

    def _forward_drag_event(self, event) -> bool:  # noqa: ANN001
        """Forwarded from host or child widgets. Calculates insertion position.
        v107: Also handles internal reorder (drag within chain)."""
        try:
            payload = _parse_payload(event)
            if payload is None:
                event.ignore()
                return True
            kind = str(payload.get("kind") or "")
            is_reorder = bool(payload.get("reorder", False))
            if kind not in ("instrument", "note_fx", "audio_fx", "container"):
                event.ignore()
                return True

            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                event.setDropAction(Qt.DropAction.MoveAction if is_reorder else Qt.DropAction.CopyAction)
                event.accept()
                # Calculate and show insertion indicator
                if kind in ("note_fx", "audio_fx", "container"):
                    try:
                        # v0.0.20.531: Containers drop into audio_fx zone
                        indicator_kind = "audio_fx" if kind == "container" else kind
                        self._update_drop_indicator(event, indicator_kind)
                    except Exception:
                        pass
                return True

            if event.type() == QEvent.Type.Drop:
                event.setDropAction(Qt.DropAction.MoveAction if is_reorder else Qt.DropAction.CopyAction)
                event.accept()
                if not self._current_track:
                    self._hide_drop_indicator()
                    return True

                # Capture insert position before hiding indicator
                insert_kind = self._drop_insert_kind
                insert_index = self._drop_insert_index
                self._hide_drop_indicator()

                if is_reorder:
                    # Internal reorder: move device to new position
                    device_id = str(payload.get("device_id") or "")
                    if device_id and insert_kind == kind:
                        self._reorder_fx_to(self._current_track, kind, device_id, insert_index)
                    return True

                plugin_id = str(payload.get("plugin_id") or "")
                dev_name = str(payload.get("name") or "").strip()
                dev_params = payload.get("params") if isinstance(payload.get("params"), dict) else None
                if kind == "instrument":
                    self.add_instrument_to_track(self._current_track, plugin_id)
                elif kind == "note_fx":
                    idx = insert_index if insert_kind == "note_fx" else -1
                    self.add_note_fx_to_track(self._current_track, plugin_id, insert_index=idx, name=dev_name, params=dev_params)
                elif kind == "audio_fx":
                    idx = insert_index if insert_kind == "audio_fx" else -1
                    self.add_audio_fx_to_track(self._current_track, plugin_id, insert_index=idx, name=dev_name, params=dev_params)
                elif kind == "container":
                    # v0.0.20.531: Container drag from browser
                    idx = insert_index if insert_kind == "audio_fx" else -1
                    if plugin_id == "chrono.container.fx_layer":
                        self.add_fx_layer_to_track(self._current_track, insert_index=idx)
                    elif plugin_id == "chrono.container.chain":
                        self.add_chain_container_to_track(self._current_track, insert_index=idx)
                return True
        except Exception:
            try:
                self._hide_drop_indicator()
            except Exception:
                pass
            try:
                event.ignore()
            except Exception:
                pass
            return True

        return False

    def _update_drop_indicator(self, event, kind: str) -> None:
        """Calculate which slot the cursor is over and show the drop indicator there.

        The chain layout is: [Note-FX cards...] [Instrument anchor] [Audio-FX cards...] [stretch]
        We find all cards of the matching kind and determine which gap the cursor falls into.
        """
        try:
            # Map event position to chain_host coordinates
            pos = event.position() if hasattr(event, 'position') else event.posF()
            source_widget = None
            try:
                # The event comes from different widgets; we need to map to chain_host
                source_widget = event.source() if hasattr(event, 'source') else None
            except Exception:
                pass

            # Get global position and map to chain_host
            try:
                if hasattr(event, 'position'):
                    local_pos = event.position()
                else:
                    local_pos = event.posF()
                # Map from the widget that received the event to chain_host
                # We use globalPosition for reliable mapping
                if hasattr(event, 'globalPosition'):
                    global_pos = event.globalPosition().toPoint()
                elif hasattr(event, 'globalPos'):
                    global_pos = event.globalPos()
                else:
                    global_pos = self.chain_host.mapToGlobal(local_pos.toPoint())
                host_pos = self.chain_host.mapFromGlobal(global_pos)
                cursor_x = host_pos.x()
            except Exception:
                cursor_x = int(pos.x()) if pos else 0

            # Collect cards of the matching kind with their positions
            cards_info = self._get_chain_card_positions(kind)

            if not cards_info:
                # No existing cards: show indicator at the zone's start position
                zone_x = self._get_zone_start_x(kind)
                self._show_drop_indicator_at(zone_x)
                self._drop_insert_kind = kind
                self._drop_insert_index = 0
                return

            # Find which gap the cursor falls into
            # Gaps: [before card 0] [card 0] [between 0 and 1] [card 1] ... [after last card]
            insert_idx = len(cards_info)  # default: append
            for i, (card_x, card_w) in enumerate(cards_info):
                card_center = card_x + card_w // 2
                if cursor_x < card_center:
                    insert_idx = i
                    break

            # Position the indicator
            if insert_idx == 0:
                indicator_x = cards_info[0][0] - 4
            elif insert_idx < len(cards_info):
                prev_right = cards_info[insert_idx - 1][0] + cards_info[insert_idx - 1][1]
                next_left = cards_info[insert_idx][0]
                indicator_x = (prev_right + next_left) // 2
            else:
                last_right = cards_info[-1][0] + cards_info[-1][1]
                indicator_x = last_right + 4

            self._show_drop_indicator_at(indicator_x)
            self._drop_insert_kind = kind
            self._drop_insert_index = insert_idx

        except Exception:
            self._hide_drop_indicator()

    def _get_chain_card_positions(self, kind: str) -> List[Tuple[int, int]]:
        """Return list of (x_pos, width) for all device cards of the given kind in chain_host coords.

        Chain layout: [Note-FX 0..N] [Instrument anchor] [Audio-FX 0..M] [stretch]
        """
        result = []
        try:
            if not self._current_track:
                return result
            _, project_obj, trk = self._get_project_track(self._current_track)
            if trk is None:
                return result

            # Count devices to know which layout items belong to which zone
            note_chain = getattr(trk, "note_fx_chain", None)
            note_devs = note_chain.get("devices", []) if isinstance(note_chain, dict) else []
            note_devs = [d for d in (note_devs or []) if isinstance(d, dict)]
            n_note = len(note_devs)

            audio_chain = getattr(trk, "audio_fx_chain", None)
            audio_devs = audio_chain.get("devices", []) if isinstance(audio_chain, dict) else []
            audio_devs = [d for d in (audio_devs or []) if isinstance(d, dict)]
            n_audio = len(audio_devs)

            # Layout items: [note_fx cards (0..n_note-1)] [instrument card (n_note)] [audio_fx cards (n_note+1..n_note+n_audio)] [stretch]
            if kind == "note_fx":
                for i in range(n_note):
                    item = self.chain.itemAt(i)
                    if item and item.widget():
                        w = item.widget()
                        result.append((w.x(), w.width()))
            elif kind == "audio_fx":
                start = n_note + 1  # skip note-fx cards + instrument anchor
                for i in range(n_audio):
                    item = self.chain.itemAt(start + i)
                    if item and item.widget():
                        w = item.widget()
                        result.append((w.x(), w.width()))
        except Exception:
            pass
        return result

    def _get_zone_start_x(self, kind: str) -> int:
        """Get the x coordinate where new cards of this kind should start."""
        try:
            if kind == "note_fx":
                return 0
            elif kind == "audio_fx":
                # Right after the instrument anchor card
                _, _, trk = self._get_project_track(self._current_track)
                if trk is None:
                    return 0
                note_chain = getattr(trk, "note_fx_chain", None)
                note_devs = note_chain.get("devices", []) if isinstance(note_chain, dict) else []
                note_devs = [d for d in (note_devs or []) if isinstance(d, dict)]
                anchor_idx = len(note_devs)  # instrument anchor is right after note-fx
                item = self.chain.itemAt(anchor_idx)
                if item and item.widget():
                    w = item.widget()
                    return w.x() + w.width() + 8
        except Exception:
            pass
        return 0

    def _show_drop_indicator_at(self, x: int) -> None:
        """Show the vertical drop indicator line at the given x position."""
        try:
            self._drop_indicator.setParent(self.chain_host)
            self._drop_indicator.setFixedHeight(max(self.chain_host.height() - 8, 40))
            self._drop_indicator.move(max(0, x - 1), 4)
            self._drop_indicator.show()
            self._drop_indicator.raise_()
        except Exception:
            pass

    def _hide_drop_indicator(self) -> None:
        """Hide the drop indicator and reset state."""
        try:
            self._drop_indicator.hide()
        except Exception:
            pass
        self._drop_insert_kind = ""
        self._drop_insert_index = -1

    def dragEnterEvent(self, event):  # noqa: N802, ANN001
        self._forward_drag_event(event)

    def dragMoveEvent(self, event):  # noqa: N802, ANN001
        self._forward_drag_event(event)

    def dropEvent(self, event):  # noqa: N802, ANN001
        self._forward_drag_event(event)

    def dragLeaveEvent(self, event):  # noqa: N802, ANN001
        try:
            self._hide_drop_indicator()
        except Exception:
            pass

    # ---- internal drag reorder (v107) ----

    def _reorder_fx_to(self, track_id: str, kind: str, device_id: str, target_index: int) -> None:
        """Move *device_id* of *kind* to *target_index* in the chain.

        This is invoked when the user drags an FX card to a new position within
        the same FX zone (note_fx or audio_fx).
        """
        track_id = str(track_id or "")
        device_id = str(device_id or "")
        target_index = int(target_index)
        if not track_id or not device_id:
            return
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or project_obj is None or trk is None:
            return

        chain_attr = "note_fx_chain" if kind == "note_fx" else "audio_fx_chain"
        chain = getattr(trk, chain_attr, None)
        if not isinstance(chain, dict):
            return
        devs = chain.get("devices", []) or []
        devs = [d for d in devs if isinstance(d, dict)]

        # Find current position
        src_idx = next((i for i, d in enumerate(devs) if str(d.get("id", "")) == device_id), None)
        if src_idx is None:
            return

        # Nothing to do if already at target
        if src_idx == target_index or (src_idx + 1 == target_index):
            # target_index is the *insertion* index (gap index), so
            # dropping right after the same card means no move.
            return

        device = devs.pop(src_idx)
        # Adjust target after removal
        ins = target_index if target_index <= src_idx else target_index - 1
        ins = max(0, min(ins, len(devs)))
        devs.insert(ins, device)
        chain["devices"] = devs

        if kind == "audio_fx":
            self._rebuild_audio_fx(project_obj)

        self._set_pending_fx_focus(kind, device_id)
        self._emit_project_updated()

    # ----------------- render -----------------

    # v0.0.20.554: Bitwig-style layer zoom rendering ----------------------------

    def _render_layer_zoom(self, ctx: dict) -> None:
        """Render zoomed container content — Bitwig-style.

        v0.0.20.562: Handles all 3 container types:
        - "layer" → Instrument Layer (instrument + FX chain)
        - "fx_layer" → FX Layer (FX devices in parallel layer)
        - "chain" → Chain (FX devices in serial chain)
        """
        ctype = str(ctx.get("type") or "")
        if ctype == "fx_layer":
            self._render_fx_layer_zoom(ctx)
            return
        if ctype == "chain":
            self._render_chain_zoom(ctx)
            return
        # Default: instrument layer
        self._render_instrument_layer_zoom(ctx)

    def _render_fx_layer_zoom(self, ctx: dict) -> None:
        """Render FX Layer zoom — shows all FX devices in a parallel layer."""
        try:
            track_id = str(ctx.get("track_id") or "")
            device_id = str(ctx.get("device_id") or "")
            layer_index = int(ctx.get("layer_index", 0))

            proj, project_obj, trk = self._get_project_track(track_id)
            if trk is None:
                self.chain.addWidget(QLabel("Track nicht gefunden"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            chain = getattr(trk, "audio_fx_chain", None)
            if not isinstance(chain, dict):
                self.chain.addWidget(QLabel("Keine Audio-FX-Chain"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            # Find container
            container = None
            for dev in (chain.get("devices") or []):
                if isinstance(dev, dict) and (str(dev.get("id") or "") == device_id or
                   str(dev.get("plugin_id") or "") == "chrono.container.fx_layer"):
                    container = dev
                    break
            if container is None:
                self.chain.addWidget(QLabel("FX Layer Container nicht gefunden"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            layers = container.get("layers") or []
            if layer_index < 0 or layer_index >= len(layers):
                self.chain.addWidget(QLabel(f"Layer {layer_index} nicht gefunden"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            layer = layers[layer_index]
            if not isinstance(layer, dict):
                self.chain.addWidget(QLabel("Layer-Daten ungültig"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            # Render all FX devices in this layer
            layer_devs = [d for d in (layer.get("devices") or []) if isinstance(d, dict)]
            for j, dev in enumerate(layer_devs):
                did = str(dev.get("id") or f"fxlayer_{j}")
                title = str(dev.get("name") or dev.get("plugin_id") or "FX")
                enabled = bool(dev.get("enabled", True))
                inner = make_audio_fx_widget(self._services, track_id, dev) or QLabel("No UI")

                card = _DeviceCard(
                    title, inner, enabled=enabled,
                    can_up=j > 0, can_down=j < len(layer_devs) - 1,
                    on_up=lambda _tid=track_id, _did=device_id, _li=layer_index, _j=j:
                        self._layer_move_fx(_tid, _did, _li, _j, -1),
                    on_down=lambda _tid=track_id, _did=device_id, _li=layer_index, _j=j:
                        self._layer_move_fx(_tid, _did, _li, _j, +1),
                    on_power=lambda checked, _tid=track_id, _did=device_id, _li=layer_index, _j=j:
                        self._layer_toggle_fx(_tid, _did, _li, _j),
                    on_remove=lambda _tid=track_id, _did=device_id, _li=layer_index, _j=j:
                        self._layer_remove_fx(_tid, _did, _li, _j),
                    collapsible=True, collapsed=False, device_id=did,
                    fx_kind="audio_fx",
                    plugin_type_id=str(dev.get("plugin_id") or ""),
                    plugin_name=title, source_track_id=track_id,
                )
                try:
                    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                except Exception:
                    pass
                self._install_drop_filter(card)
                self.chain.addWidget(card)

            if not layer_devs:
                empty = QLabel("Leerer Layer — FX über den Button unten hinzufügen")
                empty.setStyleSheet("color: #888; font-size: 11px; padding: 20px; "
                                    "border: 2px dashed #4fc3f7; border-radius: 6px;")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.chain.addWidget(empty)

            # + FX button
            try:
                btn_add = QPushButton("+ Audio-FX → Layer")
                btn_add.setFixedHeight(28)
                btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_add.setStyleSheet(
                    "QPushButton { font-size: 10px; color: #4fc3f7; "
                    "padding: 4px 12px; border: 1px dashed #4fc3f7; border-radius: 4px; }"
                    "QPushButton:hover { background: rgba(79,195,247,40); color: #fff; }"
                )
                btn_add.clicked.connect(lambda _=False: self._show_layer_add_fx_menu())
                self.chain.addWidget(btn_add)
            except Exception:
                pass

            self.chain.addStretch(1)
            self._zone_layout_meta = {}
            self._sync_chain_host_size()
            self._hide_zone_visuals()
            self._update_batch_action_button_state()
        except Exception:
            import traceback
            traceback.print_exc()
            self.chain.addWidget(QLabel("Fehler beim FX-Layer-Rendering"))
            self.chain.addStretch(1)
            self._sync_chain_host_size()

    def _render_chain_zoom(self, ctx: dict) -> None:
        """Render Chain zoom — shows all FX devices in serial chain."""
        try:
            track_id = str(ctx.get("track_id") or "")
            device_id = str(ctx.get("device_id") or "")

            proj, project_obj, trk = self._get_project_track(track_id)
            if trk is None:
                self.chain.addWidget(QLabel("Track nicht gefunden"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            chain = getattr(trk, "audio_fx_chain", None)
            if not isinstance(chain, dict):
                self.chain.addWidget(QLabel("Keine Audio-FX-Chain"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            # Find container
            container = None
            for dev in (chain.get("devices") or []):
                if isinstance(dev, dict) and (str(dev.get("id") or "") == device_id or
                   str(dev.get("plugin_id") or "") == "chrono.container.chain"):
                    container = dev
                    break
            if container is None:
                self.chain.addWidget(QLabel("Chain Container nicht gefunden"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            # Render all devices in the chain
            chain_devs = [d for d in (container.get("devices") or []) if isinstance(d, dict)]
            for j, dev in enumerate(chain_devs):
                did = str(dev.get("id") or f"chain_{j}")
                title = str(dev.get("name") or dev.get("plugin_id") or "FX")
                enabled = bool(dev.get("enabled", True))
                inner = make_audio_fx_widget(self._services, track_id, dev) or QLabel("No UI")

                card = _DeviceCard(
                    title, inner, enabled=enabled,
                    can_up=j > 0, can_down=j < len(chain_devs) - 1,
                    on_up=lambda _tid=track_id, _did=device_id, _j=j:
                        self._chain_move_fx(_tid, _did, _j, -1),
                    on_down=lambda _tid=track_id, _did=device_id, _j=j:
                        self._chain_move_fx(_tid, _did, _j, +1),
                    on_power=lambda checked, _tid=track_id, _did=device_id, _j=j:
                        self._chain_toggle_fx(_tid, _did, _j),
                    on_remove=lambda _tid=track_id, _did=device_id, _j=j:
                        self._chain_remove_fx(_tid, _did, _j),
                    collapsible=True, collapsed=False, device_id=did,
                    fx_kind="audio_fx",
                    plugin_type_id=str(dev.get("plugin_id") or ""),
                    plugin_name=title, source_track_id=track_id,
                )
                try:
                    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                except Exception:
                    pass
                self._install_drop_filter(card)
                self.chain.addWidget(card)

            if not chain_devs:
                empty = QLabel("Leere Chain — FX über den Button unten hinzufügen")
                empty.setStyleSheet("color: #888; font-size: 11px; padding: 20px; "
                                    "border: 2px dashed #ffb74d; border-radius: 6px;")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.chain.addWidget(empty)

            # + FX button
            try:
                btn_add = QPushButton("+ Audio-FX → Chain")
                btn_add.setFixedHeight(28)
                btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_add.setStyleSheet(
                    "QPushButton { font-size: 10px; color: #ffb74d; "
                    "padding: 4px 12px; border: 1px dashed #ffb74d; border-radius: 4px; }"
                    "QPushButton:hover { background: rgba(255,183,77,40); color: #fff; }"
                )
                btn_add.clicked.connect(lambda _=False: self._show_chain_add_fx_menu())
                self.chain.addWidget(btn_add)
            except Exception:
                pass

            self.chain.addStretch(1)
            self._zone_layout_meta = {}
            self._sync_chain_host_size()
            self._hide_zone_visuals()
            self._update_batch_action_button_state()
        except Exception:
            import traceback
            traceback.print_exc()
            self.chain.addWidget(QLabel("Fehler beim Chain-Rendering"))
            self.chain.addStretch(1)
            self._sync_chain_host_size()

    def _render_instrument_layer_zoom(self, ctx: dict) -> None:
        """Render instrument layer zoom — original implementation."""
        try:
            track_id = str(ctx.get("track_id") or "")
            device_id = str(ctx.get("device_id") or "")
            layer_index = int(ctx.get("layer_index", 0))
            layer_name = str(ctx.get("layer_name") or f"Layer {layer_index + 1}")

            # Find the layer data
            proj, project_obj, trk = self._get_project_track(track_id)
            if trk is None:
                self.chain.addWidget(QLabel("Track nicht gefunden"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            chain = getattr(trk, "audio_fx_chain", None)
            if not isinstance(chain, dict):
                self.chain.addWidget(QLabel("Keine Audio-FX-Chain"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            # Find the container device
            devices = chain.get("devices") or []
            container = None
            for dev in devices:
                if isinstance(dev, dict) and str(dev.get("id") or "") == device_id:
                    container = dev
                    break
            if container is None:
                # Fallback: find by plugin_id
                for dev in devices:
                    if isinstance(dev, dict) and str(dev.get("plugin_id") or "") == "chrono.container.instrument_layer":
                        container = dev
                        break
            if container is None:
                self.chain.addWidget(QLabel("Container nicht gefunden"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            layers = container.get("layers") or []
            if layer_index < 0 or layer_index >= len(layers):
                self.chain.addWidget(QLabel(f"Layer {layer_index} nicht gefunden"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            layer = layers[layer_index]
            if not isinstance(layer, dict):
                self.chain.addWidget(QLabel("Layer-Daten ungültig"))
                self.chain.addStretch(1)
                self._sync_chain_host_size()
                return

            # -- Render the layer's instrument as a device card --
            inst_pid = str(layer.get("instrument") or "")
            inst_name = str(layer.get("instrument_name") or inst_pid or "(kein Instrument)")

            if inst_pid:
                # Create instrument widget using the same factory as normal instruments
                inst_widget = self._make_layer_instrument_widget(
                    track_id, layer_index, layer, inst_pid, inst_name
                )
                inst_card = _DeviceCard(
                    f"🎹 {inst_name}",
                    inst_widget,
                    enabled=True,
                    can_up=False, can_down=False,
                    collapsible=True,
                    collapsed=False,
                    device_id=f"layer_inst_{layer_index}",
                    fx_kind="instrument",
                    plugin_type_id=inst_pid,
                    plugin_name=inst_name,
                    source_track_id=track_id,
                )
                try:
                    inst_card.setStyleSheet(
                        "QFrame { border: 2px solid #7e57c2; border-radius: 6px; }"
                    )
                    # v0.0.20.559: Make instrument card fill viewport in zoom mode
                    inst_card.setMinimumWidth(max(700, self.scroll.viewport().width() - 40))
                    inst_card.setSizePolicy(
                        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
                    )
                except Exception:
                    pass
                self._install_drop_filter(inst_card)
                self.chain.addWidget(inst_card)
            else:
                empty_inst = QLabel(
                    f"🎹 {layer_name}: Kein Instrument\n\n"
                    "← Zurück drücken und ein Instrument\n"
                    "über den Picker-Button auswählen."
                )
                empty_inst.setStyleSheet(
                    "color: #999; font-size: 11px; padding: 20px; "
                    "border: 2px dashed #7e57c2; border-radius: 6px;"
                )
                empty_inst.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.chain.addWidget(empty_inst)

            # -- Render per-layer FX devices --
            layer_devs = layer.get("devices") or []
            _valid_devs = [d for d in layer_devs if isinstance(d, dict)]
            for j, dev in enumerate(_valid_devs):
                did = str(dev.get("id") or f"layerfx_{j}")
                title = str(dev.get("name") or dev.get("plugin_id") or "FX")
                enabled = bool(dev.get("enabled", True))
                inner = make_audio_fx_widget(self._services, track_id, dev) or QLabel("No UI")

                # v0.0.20.561: Full FX management in layer zoom
                card = _DeviceCard(
                    title,
                    inner,
                    enabled=enabled,
                    can_up=j > 0,
                    can_down=j < len(_valid_devs) - 1,
                    on_up=lambda _tid=track_id, _did=device_id, _li=layer_index, _j=j:
                        self._layer_move_fx(_tid, _did, _li, _j, -1),
                    on_down=lambda _tid=track_id, _did=device_id, _li=layer_index, _j=j:
                        self._layer_move_fx(_tid, _did, _li, _j, +1),
                    on_power=lambda checked, _tid=track_id, _did=device_id, _li=layer_index, _j=j:
                        self._layer_toggle_fx(_tid, _did, _li, _j),
                    on_remove=lambda _tid=track_id, _did=device_id, _li=layer_index, _j=j:
                        self._layer_remove_fx(_tid, _did, _li, _j),
                    collapsible=True,
                    collapsed=False,
                    device_id=did,
                    fx_kind="audio_fx",
                    plugin_type_id=str(dev.get("plugin_id") or ""),
                    plugin_name=title,
                    source_track_id=track_id,
                )
                # v0.0.20.560: Consistent sizing in zoom mode
                try:
                    card.setSizePolicy(
                        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
                    )
                except Exception:
                    pass
                self._install_drop_filter(card)
                self.chain.addWidget(card)

            # v0.0.20.559: "+ FX" button to add effects inside the layer
            try:
                _ctx = self._get_layer_context()
                if _ctx is not None:
                    btn_add_fx = QPushButton("+ Audio-FX → Layer")
                    btn_add_fx.setFixedHeight(28)
                    btn_add_fx.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_add_fx.setStyleSheet(
                        "QPushButton { font-size: 10px; color: #b39ddb; "
                        "padding: 4px 12px; border: 1px dashed #7e57c2; border-radius: 4px; }"
                        "QPushButton:hover { background: rgba(126,87,194,40); color: #fff; }"
                    )
                    btn_add_fx.setToolTip("Audio-FX zu diesem Layer hinzufügen\n(wird innerhalb der Layer-Chain platziert)")
                    # Show context menu with available FX
                    btn_add_fx.clicked.connect(lambda _=False: self._show_layer_add_fx_menu())
                    self.chain.addWidget(btn_add_fx)
            except Exception:
                pass

            self.chain.addStretch(1)
            self._zone_layout_meta = {}
            self._sync_chain_host_size()
            self._hide_zone_visuals()
            self._update_batch_action_button_state()

        except Exception:
            import traceback
            traceback.print_exc()
            self.chain.addWidget(QLabel("Fehler beim Layer-Rendering"))
            self.chain.addStretch(1)
            self._sync_chain_host_size()

    def _make_layer_instrument_widget(self, track_id: str, layer_index: int,
                                       layer: dict, plugin_id: str,
                                       plugin_name: str) -> QWidget:
        """Create an instrument widget for a layer instrument.

        v0.0.20.559: CRITICAL FIX — Built-in instruments get correct constructor args
        and are connected to the EXISTING layer engine (not their own copy).
        External plugins use make_audio_fx_widget factory with engine-compatible IDs.
        """
        try:
            # Get services for correct constructor calls
            proj_svc = getattr(self._services, "project", None)
            ae = getattr(self._services, "audio_engine", None)
            am = getattr(self._services, "automation_manager", None)
            layer_engine_key = f"{track_id}:ilayer:{layer_index}"

            # Find the EXISTING layer engine in the audio engine
            existing_engine = None
            try:
                inst_engines = getattr(ae, "_vst_instrument_engines", None)
                if isinstance(inst_engines, dict):
                    existing_engine = inst_engines.get(layer_engine_key)
            except Exception:
                pass

            # --- Built-in instruments (own widget classes) ---
            widget = None
            if plugin_id == "chrono.aeterna":
                try:
                    from pydaw.plugins.aeterna.aeterna_widget import AeternaWidget
                    widget = AeternaWidget(
                        project_service=proj_svc, audio_engine=ae,
                        automation_manager=am, parent=self
                    )
                except Exception:
                    import traceback; traceback.print_exc()
            elif plugin_id == "chrono.bach_orgel":
                try:
                    from pydaw.plugins.bach_orgel.bach_orgel_widget import BachOrgelWidget
                    widget = BachOrgelWidget(
                        project_service=proj_svc, audio_engine=ae,
                        automation_manager=am, parent=self
                    )
                except Exception:
                    import traceback; traceback.print_exc()
            elif plugin_id == "chrono.sampler":
                try:
                    from pydaw.plugins.sampler.sampler_widget import SamplerWidget
                    widget = SamplerWidget(
                        project_service=proj_svc, audio_engine=ae,
                        automation_manager=am, parent=self
                    )
                except Exception:
                    import traceback; traceback.print_exc()
            elif plugin_id == "chrono.drum_machine":
                try:
                    from pydaw.plugins.drum_machine.drum_widget import DrumMachineWidget
                    widget = DrumMachineWidget(
                        project_service=proj_svc, audio_engine=ae,
                        automation_manager=am, parent=self
                    )
                except Exception:
                    import traceback; traceback.print_exc()
            elif plugin_id == "chrono.fusion":
                # v0.0.20.574: Fusion semi-modular synthesizer
                try:
                    from pydaw.plugins.fusion.fusion_widget import FusionWidget
                    widget = FusionWidget(
                        project_service=proj_svc, audio_engine=ae,
                        automation_manager=am, parent=self
                    )
                except Exception:
                    import traceback; traceback.print_exc()
            elif plugin_id == "chrono.sf2":
                # v0.0.20.566: Inline SF2 widget with bank/preset selector
                try:
                    sf2_path = str(layer.get("sf2_path") or "")
                    sf2_bank = int(layer.get("bank", 0) or 0)
                    sf2_preset = int(layer.get("preset", 0) or 0)
                    sf2_name = os.path.basename(sf2_path) if sf2_path else "(kein SF2)"

                    sf2_w = QWidget(self)
                    sf2_lay = QVBoxLayout(sf2_w)
                    sf2_lay.setContentsMargins(8, 8, 8, 8)
                    sf2_lay.setSpacing(6)

                    # File label + Load button
                    file_row = QHBoxLayout()
                    lbl_file = QLabel(f"🎹 SF2: {sf2_name}")
                    lbl_file.setStyleSheet("font-size: 12px; color: #ce93d8; font-weight: bold;")
                    file_row.addWidget(lbl_file, 1)
                    btn_load = QPushButton("SF2 laden…")
                    btn_load.setFixedHeight(26)
                    btn_load.setStyleSheet(
                        "QPushButton { font-size: 10px; padding: 4px 10px; "
                        "border: 1px solid #ce93d8; border-radius: 3px; color: #ce93d8; }"
                        "QPushButton:hover { background: rgba(206,147,216,40); color: #fff; }"
                    )

                    def _load_sf2(_=False, _layer=layer, _lbl=lbl_file):
                        from PySide6.QtWidgets import QFileDialog
                        path, _ = QFileDialog.getOpenFileName(
                            self, "SF2 Datei wählen", "",
                            "SoundFont (*.sf2 *.SF2);;Alle (*)"
                        )
                        if path:
                            _layer["sf2_path"] = path
                            _lbl.setText(f"🎹 SF2: {os.path.basename(path)}")
                            self._emit_layer_update()
                    btn_load.clicked.connect(_load_sf2)
                    file_row.addWidget(btn_load)
                    sf2_lay.addLayout(file_row)

                    # Bank / Preset row
                    bp_row = QHBoxLayout()
                    bp_row.addWidget(QLabel("Bank:"))
                    spin_bank = QSpinBox()
                    spin_bank.setRange(0, 127)
                    spin_bank.setValue(sf2_bank)
                    spin_bank.setFixedWidth(70)
                    bp_row.addWidget(spin_bank)
                    bp_row.addSpacing(12)
                    bp_row.addWidget(QLabel("Preset:"))
                    spin_preset = QSpinBox()
                    spin_preset.setRange(0, 127)
                    spin_preset.setValue(sf2_preset)
                    spin_preset.setFixedWidth(70)
                    bp_row.addWidget(spin_preset)
                    bp_row.addStretch(1)

                    def _on_bp_changed(_val=0, _layer=layer, _sb=spin_bank, _sp=spin_preset):
                        _layer["bank"] = _sb.value()
                        _layer["preset"] = _sp.value()
                        # Apply to running engine
                        try:
                            if existing_engine is not None and hasattr(existing_engine, "set_program"):
                                existing_engine.set_program(_sb.value(), _sp.value())
                        except Exception:
                            pass
                        self._emit_layer_update()
                    spin_bank.valueChanged.connect(_on_bp_changed)
                    spin_preset.valueChanged.connect(_on_bp_changed)
                    sf2_lay.addLayout(bp_row)

                    # Path info
                    if sf2_path:
                        lbl_path = QLabel(sf2_path)
                        lbl_path.setStyleSheet("font-size: 9px; color: #888;")
                        lbl_path.setWordWrap(True)
                        sf2_lay.addWidget(lbl_path)

                    widget = sf2_w
                except Exception:
                    import traceback; traceback.print_exc()

            if widget is not None:
                # v0.0.20.559: Connect widget to EXISTING layer engine
                # instead of its own newly-created copy.
                if existing_engine is not None and hasattr(widget, "engine"):
                    widget.engine = existing_engine
                    # Update the pull function to use the real engine
                    if hasattr(widget, "_pull_fn"):
                        def _real_pull(frames, sr, _e=existing_engine):
                            return _e.pull(frames, sr)
                        _real_pull._pydaw_track_id = lambda _t=track_id: _t
                        widget._pull_fn = _real_pull
                    # v0.0.20.564: Unregister widget's OWN pull source
                    # (it registered one in __init__ that conflicts)
                    try:
                        if ae is not None and hasattr(widget, "_pull_name") and widget._pull_name:
                            ae.unregister_pull_source(widget._pull_name)
                            widget._pull_name = None
                    except Exception:
                        pass
                    print(f"[LAYER-ZOOM] Connected widget to existing engine: {layer_engine_key}",
                          flush=True)

                # Set track context carefully — DON'T let it re-register in
                # SamplerRegistry (dispatcher is already there) or create
                # a duplicate pull source.
                # v0.0.20.564: Some widgets (SamplerWidget) have a track_id property
                # setter that auto-registers in SamplerRegistry → bypass it
                if hasattr(widget, '_track_id'):
                    widget._track_id = track_id
                else:
                    widget.track_id = track_id
                # Restore instrument state from project without re-registering
                try:
                    if hasattr(widget, "_restore_instrument_state"):
                        widget._restore_instrument_state()
                except Exception:
                    pass
                # v0.0.20.560: Setup automation (Rechtsklick → "Show Automation",
                # MIDI Learn, etc.) — requires track_id + automation_manager
                try:
                    if hasattr(widget, "_setup_automation"):
                        widget._setup_automation()
                except Exception:
                    pass
                # v0.0.20.563: Einheitliche Widget-Größe — alle Built-in
                # Instrumente füllen die volle Breite im Layer-Zoom
                try:
                    widget.setSizePolicy(
                        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
                    )
                    widget.setMinimumWidth(0)  # Remove any hard minimum
                    widget.setMaximumWidth(16777215)  # Remove any hard maximum (Qt default)
                except Exception:
                    pass
                return widget

            # --- External plugins: use universal widget factory ---
            if plugin_id.startswith("ext."):
                virtual_device = {
                    "id": layer_engine_key,
                    "plugin_id": plugin_id,
                    "name": plugin_name,
                    "enabled": True,
                    "params": dict(layer.get("params") or {}),
                }
                params = virtual_device["params"]
                ref = plugin_id.split(":", 1)[1] if ":" in plugin_id else ""
                params.setdefault("__ext_ref", ref)
                params.setdefault("__ext_plugin_name", plugin_name)

                ext_widget = make_audio_fx_widget(self._services, track_id, virtual_device)
                if ext_widget is not None:
                    # v0.0.20.563: Einheitliche Größe auch für externe Plugins
                    try:
                        ext_widget.setSizePolicy(
                            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
                        )
                        ext_widget.setMaximumWidth(16777215)
                    except Exception:
                        pass
                    return ext_widget

        except Exception:
            import traceback
            traceback.print_exc()

        # Fallback
        fallback = QLabel(f"🎹 {plugin_name}\n\n(Widget nicht verfügbar)")
        fallback.setStyleSheet("color: #999; font-size: 11px; padding: 16px;")
        fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return fallback

    # --------------------------------------------------------------------------

    def _safe_render_current_track(self) -> None:
        try:
            self._render_current_track()
        except Exception:
            # never crash Qt thread
            return

    def _render_current_track(self) -> None:
        # clear layout
        self._clear_chain()
        self._rendered_fx_cards = {}

        # v0.0.20.554: Check if we're zoomed into a layer — render layer content
        layer_ctx = self._get_layer_context()
        if layer_ctx is not None and self._current_track:
            self._render_layer_zoom(layer_ctx)
            return

        if not self._current_track:
            self.chain.addWidget(self.empty_label)
            self.chain.addStretch(1)
            self._zone_layout_meta = {}
            self._sync_chain_host_size()
            self._hide_zone_visuals()
            self._update_group_strip()
            self._update_scope_strip(None)
            self._update_batch_action_button_state()
            return

        proj, project_obj, trk = self._get_project_track(self._current_track)
        if proj is None or project_obj is None or trk is None:
            self.chain.addWidget(self.empty_label)
            self.chain.addStretch(1)
            self._zone_layout_meta = {}
            self._sync_chain_host_size()
            self._hide_zone_visuals()
            self._update_group_strip()
            self._update_scope_strip(None)
            self._update_batch_action_button_state()
            return

        # NOTE-FX (left)
        note_chain = getattr(trk, "note_fx_chain", None)
        note_devs = note_chain.get("devices", []) if isinstance(note_chain, dict) else []
        note_devs = [d for d in (note_devs or []) if isinstance(d, dict)]

        for i, dev in enumerate(note_devs):
            did = str(dev.get("id") or "")
            title = str(dev.get("name") or dev.get("plugin_id") or "Note-FX")
            enabled = bool(dev.get("enabled", True))
            inner = make_note_fx_widget(self._services, self._current_track, dev) or QLabel("No UI")
            self._install_drop_filter(inner)

            card = _DeviceCard(
                title,
                inner,
                enabled=enabled,
                can_up=i > 0,
                can_down=i < (len(note_devs) - 1),
                on_up=lambda tid=self._current_track, d=did: self._move_fx(tid, "note_fx", d, -1),
                on_down=lambda tid=self._current_track, d=did: self._move_fx(tid, "note_fx", d, +1),
                on_power=lambda checked, tid=self._current_track, d=did: self._set_fx_enabled(tid, "note_fx", d, bool(checked)),
                on_remove=lambda tid=self._current_track, d=did: self.remove_note_fx_device(tid, d),
                on_focus=lambda k="note_fx", d=did: self._focus_fx_card(k, d, ensure_visible=False),
                on_toggle_collapse=self._make_card_collapse_callback("note_fx", did),
                collapsed=self._is_card_collapsed("note_fx", did),
                collapsible=True,
                device_id=did,
                fx_kind="note_fx",
                plugin_type_id=str(dev.get("plugin_id") or dev.get("plugin_type") or ""),
                plugin_name=title,
                source_track_id=self._current_track,
            )
            try:
                card._collapse_state_kind = "note_fx"
                card._collapse_state_device_id = did
            except Exception:
                pass
            self._install_drop_filter(card)
            self.chain.addWidget(card)
            self._rendered_fx_cards[("note_fx", did)] = card
            if self._selected_fx_kind == "note_fx" and self._selected_fx_device_id == did:
                self._focus_fx_card("note_fx", did, ensure_visible=False)
            if self._pending_focus_kind == "note_fx" and self._pending_focus_device_id == did:
                self._focus_fx_card("note_fx", did, ensure_visible=True)
                self._pending_focus_kind = ""
                self._pending_focus_device_id = ""

        # INSTRUMENT (anchor, fixed)
        inst_card = self._make_instrument_anchor_card(project_obj, trk)
        self._install_drop_filter(inst_card)
        self.chain.addWidget(inst_card)
        self._zone_layout_meta = {"n_note": len(note_devs), "n_audio": 0, "inst_card": inst_card}

        # AUDIO-FX (right)
        audio_chain = getattr(trk, "audio_fx_chain", None)
        audio_devs = audio_chain.get("devices", []) if isinstance(audio_chain, dict) else []
        audio_devs = [d for d in (audio_devs or []) if isinstance(d, dict)]

        for i, dev in enumerate(audio_devs):
            did = str(dev.get("id") or "")
            title = str(dev.get("name") or dev.get("plugin_id") or "Audio-FX")
            enabled = bool(dev.get("enabled", True))
            inner = make_audio_fx_widget(self._services, self._current_track, dev) or QLabel("No UI")
            self._install_drop_filter(inner)

            card = _DeviceCard(
                title,
                inner,
                enabled=enabled,
                can_up=i > 0,
                can_down=i < (len(audio_devs) - 1),
                on_up=lambda tid=self._current_track, d=did: self._move_fx(tid, "audio_fx", d, -1),
                on_down=lambda tid=self._current_track, d=did: self._move_fx(tid, "audio_fx", d, +1),
                on_power=lambda checked, tid=self._current_track, d=did: self._set_fx_enabled(tid, "audio_fx", d, bool(checked)),
                on_remove=lambda tid=self._current_track, d=did: self.remove_audio_fx_device(tid, d),
                on_focus=lambda k="audio_fx", d=did: self._focus_fx_card(k, d, ensure_visible=False),
                on_toggle_collapse=self._make_card_collapse_callback("audio_fx", did),
                collapsed=self._is_card_collapsed("audio_fx", did),
                collapsible=True,
                device_id=did,
                fx_kind="audio_fx",
                plugin_type_id=str(dev.get("plugin_id") or dev.get("plugin_type") or ""),
                plugin_name=title,
                source_track_id=self._current_track,
            )
            try:
                card._collapse_state_kind = "audio_fx"
                card._collapse_state_device_id = did
            except Exception:
                pass
            self._install_drop_filter(card)
            self.chain.addWidget(card)
            self._rendered_fx_cards[("audio_fx", did)] = card
            if self._selected_fx_kind == "audio_fx" and self._selected_fx_device_id == did:
                self._focus_fx_card("audio_fx", did, ensure_visible=False)
            if self._pending_focus_kind == "audio_fx" and self._pending_focus_device_id == did:
                self._focus_fx_card("audio_fx", did, ensure_visible=True)
                self._pending_focus_kind = ""
                self._pending_focus_device_id = ""

        self.chain.addStretch(1)
        try:
            self._zone_layout_meta = {"n_note": len(note_devs), "n_audio": len(audio_devs), "inst_card": inst_card}
        except Exception:
            self._zone_layout_meta = {}
        self._sync_chain_host_size()
        try:
            QTimer.singleShot(0, self._update_zone_visuals)
        except Exception:
            self._update_zone_visuals()
        self._update_group_strip()
        self._update_scope_strip(trk)
        self._update_batch_action_button_state()

    def _make_instrument_anchor_card(self, project_obj: Any, trk: Any) -> QWidget:
        tid = str(getattr(trk, "id", "") or "")
        plugin_id = str(getattr(trk, "plugin_type", "") or "")

        # legacy SF2 info
        sf2_path = str(getattr(trk, "sf2_path", "") or "")
        sf2_bank = getattr(trk, "sf2_bank", 0)
        sf2_preset = getattr(trk, "sf2_preset", 0)

        # SF2 ist aktuell kein Qt-Instrument-Plugin aus der Registry.
        # Trotzdem ist plugin_type == "sf2" ein valider Instrument-Anker (Engine render...)
        if plugin_id == "sf2" or (not plugin_id and sf2_path):
            w = _Sf2InstrumentWidget(self, tid, sf2_path=sf2_path, bank=int(sf2_bank or 0), preset=int(sf2_preset or 0))
            self._install_drop_filter(w)
            inst_enabled = bool(getattr(trk, "instrument_enabled", True))
            card = _DeviceCard(
                "Instrument — SF2",
                w,
                enabled=inst_enabled,
                can_up=False,
                can_down=False,
                on_up=None,
                on_down=None,
                on_power=lambda checked, tid=tid: self._set_instrument_enabled(tid, bool(checked)),
                on_remove=lambda tid=tid: self._remove_instrument(tid),
                on_toggle_collapse=self._make_card_collapse_callback("instrument", tid),
                collapsed=self._is_card_collapsed("instrument", tid),
                collapsible=True,
                device_id=tid,
                fx_kind="instrument",
                plugin_type_id="sf2",
                plugin_name="SF2",
                source_track_id=tid,
            )
            try:
                card._collapse_state_kind = "instrument"
                card._collapse_state_device_id = tid
            except Exception:
                pass
            try:
                card.setMinimumWidth(max(card.minimumWidth(), 340))
            except Exception:
                pass
            return card

        if plugin_id:
            # Ensure widget exists for this plugin id
            if tid not in self._track_instruments or self._track_instruments[tid].get("plugin_id") != plugin_id:
                instruments = {i.plugin_id: i for i in get_instruments()}
                spec = instruments.get(plugin_id)
                if spec is not None:
                    self._create_or_replace_instrument_widget(tid, plugin_id, spec)

            w = self._track_instruments.get(tid, {}).get("widget")
            if w is None:
                w = QLabel("Instrument failed to load.")
            else:
                # ensure track context
                try:
                    if hasattr(w, "set_track_context"):
                        w.set_track_context(tid)
                except Exception:
                    pass
                # If the widget was temporarily stashed during a rebuild, ensure it is visible again.
                try:
                    w.setVisible(True)
                except Exception:
                    pass

            self._install_drop_filter(w)
            inst_enabled = bool(getattr(trk, "instrument_enabled", True))
            card = _DeviceCard(
                f"Instrument — {plugin_id.split('.')[-1]}",
                w,
                enabled=inst_enabled,
                can_up=False,
                can_down=False,
                on_up=None,
                on_down=None,
                on_power=lambda checked, tid=tid: self._set_instrument_enabled(tid, bool(checked)),
                on_remove=lambda tid=tid: self._remove_instrument(tid),
                on_toggle_collapse=self._make_card_collapse_callback("instrument", tid),
                collapsed=self._is_card_collapsed("instrument", tid),
                collapsible=True,
                device_id=tid,
                fx_kind="instrument",
                plugin_type_id=plugin_id,
                plugin_name=plugin_id.split(".")[-1] if plugin_id else "Instrument",
                source_track_id=tid,
            )
            try:
                card._collapse_state_kind = "instrument"
                card._collapse_state_device_id = tid
            except Exception:
                pass
            try:
                card.setMinimumWidth(max(card.minimumWidth(), 340))
                # Breite aus Instrument-Widget ableiten (z. B. Bachs Orgel mit mehreren Sektionen),
                # damit die UI nicht unleserlich zusammengequetscht wird.
                _iw_hint = 0
                try:
                    _iw_hint = int(w.minimumSizeHint().width()) if hasattr(w, 'minimumSizeHint') else 0
                except Exception:
                    _iw_hint = 0
                if _iw_hint <= 0:
                    try:
                        _iw_hint = int(w.sizeHint().width()) if hasattr(w, 'sizeHint') else 0
                    except Exception:
                        _iw_hint = 0
                if _iw_hint > 0:
                    _desired = max(340, min(2200, _iw_hint + 48))
                    card.setMinimumWidth(max(card.minimumWidth(), _desired))
                    card.setMaximumWidth(max(int(card.maximumWidth()), _desired))
            except Exception:
                pass
            return card

        # No plugin instrument: show placeholder (anchor)
        if str(getattr(trk, "kind", "") or "") == "master":
            lab = QLabel("Master Bus\nDrop Audio-FX here or add them from the Browser / Track-Menü.")
        else:
            lab = QLabel("Instrument (Anchor)\nDrop an Instrument here or double‑click in Browser.")
        lab.setStyleSheet("color:#9a9a9a;")
        lab.setWordWrap(True)

        if sf2_path:
            try:
                import os
                name = os.path.basename(sf2_path)
            except Exception:
                name = sf2_path
            lab.setText(
                f"Instrument (Anchor)\nSF2: {name} (Bank {sf2_bank}, Preset {sf2_preset})\n"
                "Drop an Instrument plugin here to replace."
            )

        card = _DeviceCard(
            "Instrument — (empty)",
            lab,
            enabled=True,
            can_up=False,
            can_down=False,
            on_up=None,
            on_down=None,
            on_power=None,
            on_remove=None,
            on_toggle_collapse=self._make_card_collapse_callback("instrument", tid or self._current_track),
            collapsed=self._is_card_collapsed("instrument", tid or self._current_track),
            collapsible=True,
        )
        try:
            card.setMinimumWidth(max(card.minimumWidth(), 340))
        except Exception:
            pass
        return card

    # ----------------- model mutations -----------------

    def _move_fx(self, track_id: str, kind: str, device_id: str, delta: int) -> None:
        track_id = str(track_id or "")
        device_id = str(device_id or "")
        delta = int(delta)
        if not track_id or not device_id or delta == 0:
            return
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or project_obj is None or trk is None:
            return

        chain = getattr(trk, "note_fx_chain" if kind == "note_fx" else "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return
        devs = chain.get("devices", []) or []
        devs = [d for d in devs if isinstance(d, dict)]
        idx = next((i for i, d in enumerate(devs) if str(d.get("id","")) == device_id), None)
        if idx is None:
            return
        j = idx + delta
        if j < 0 or j >= len(devs):
            return
        devs[idx], devs[j] = devs[j], devs[idx]
        chain["devices"] = devs

        if kind == "audio_fx":
            self._rebuild_audio_fx(project_obj)

        self._set_pending_fx_focus(kind, device_id)
        self._emit_project_updated()

    def _set_fx_enabled(self, track_id: str, kind: str, device_id: str, enabled: bool) -> None:
        track_id = str(track_id or "")
        device_id = str(device_id or "")
        enabled = bool(enabled)
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or project_obj is None or trk is None:
            return
        chain = getattr(trk, "note_fx_chain" if kind == "note_fx" else "audio_fx_chain", None)
        if not isinstance(chain, dict):
            return
        devs = chain.get("devices", []) or []
        for d in devs:
            if isinstance(d, dict) and str(d.get("id","")) == device_id:
                d["enabled"] = bool(enabled)
                break
        if kind == "audio_fx":
            self._rebuild_audio_fx(project_obj)
        self._set_pending_fx_focus(kind, device_id)
        self._emit_project_updated()

    def _set_instrument_enabled(self, track_id: str, enabled: bool) -> None:
        """Toggle Instrument Power/Bypass for a track.

        When disabled (bypassed):
        - No MIDI events are dispatched to the instrument engine
        - No SF2 rendering occurs
        - Pull-sources for this track are silenced
        The track remains visible and its FX chain stays intact.
        """
        track_id = str(track_id or "")
        enabled = bool(enabled)
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or project_obj is None or trk is None:
            return
        try:
            trk.instrument_enabled = enabled
        except Exception:
            return
        self._restart_if_playing()
        self._emit_project_updated()

    def _remove_instrument(self, track_id: str) -> None:
        track_id = str(track_id or "")
        proj, project_obj, trk = self._get_project_track(track_id)
        if proj is None or trk is None:
            return
        try:
            trk.plugin_type = None
        except Exception:
            pass
        # SF2 cleanup (falls Track zuvor als SF2-Instrument geroutet war)
        try:
            if hasattr(trk, "sf2_path"):
                trk.sf2_path = ""
            if hasattr(trk, "sf2_bank"):
                trk.sf2_bank = 0
            if hasattr(trk, "sf2_preset"):
                trk.sf2_preset = 0
        except Exception:
            pass
        ent = self._track_instruments.pop(track_id, None)
        if ent and ent.get("widget") is not None:
            try:
                self._stash_widget(ent["widget"], delete=True)
            except Exception:
                pass
        self._emit_project_updated()

    def _create_or_replace_instrument_widget(self, track_id: str, plugin_id: str, spec) -> None:  # noqa: ANN001
        track_id = str(track_id or "")
        if not track_id:
            return
        proj = getattr(self._services, "project", None) if self._services else None
        ae = getattr(self._services, "audio_engine", None) if self._services else None

        # Remove old widget if any
        old = self._track_instruments.get(track_id)
        if old and old.get("widget") is not None:
            try:
                # Replacing the instrument: old widget is not reused -> delete safely.
                self._stash_widget(old["widget"], delete=True)
            except Exception:
                pass
        am = getattr(self._services, "automation_manager", None) if self._services else None

        try:
            w = spec.factory(project_service=proj, audio_engine=ae, automation_manager=am)
        except Exception as e:
            w = QLabel(f"Instrument error: {e}")

        try:
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        except Exception:
            pass

        # Track context (important for pull-source routing)
        try:
            if hasattr(w, "set_track_context"):
                w.set_track_context(track_id)
        except Exception:
            pass
        try:
            if hasattr(w, "track_id"):
                w.track_id = track_id
        except Exception:
            pass

        self._install_drop_filter(w)
        self._track_instruments[track_id] = {"plugin_id": plugin_id, "widget": w}

    # ----------------- helpers -----------------

    def _install_drop_filter(self, w: QWidget) -> None:
        try:
            if w is None:
                return
            w.installEventFilter(self._drop_filter)
            # Also install for children to avoid drops "verpuffen"
            for ch in w.findChildren(QWidget):
                try:
                    ch.installEventFilter(self._drop_filter)
                except Exception:
                    pass
        except Exception:
            pass

    def _stash_widget(self, w: QWidget, *, delete: bool = False) -> None:
        """Reparent a widget into an invisible stash (prevents zombie top-level windows).

        Qt behavior: A visible QWidget becomes a top-level window when its parent is set to None.
        During device-panel rebuilds we frequently need to detach persistent widgets (instruments)
        or remove cards. We MUST never do setParent(None) here.
        """
        if w is None:
            return
        try:
            w.setVisible(False)
        except Exception:
            pass
        try:
            stash = getattr(self, "_widget_stash", None)
            if stash is not None:
                w.setParent(stash)
            else:
                w.setParent(self)
        except Exception:
            pass
        if delete:
            # IMPORTANT (v0.0.20.191):
            # Never call deleteLater() *immediately* if there are pending 0ms
            # singleShot callbacks that might still touch this widget.
            # Schedule the deleteLater one tick later and guard against SIP-deleted.
            try:
                wr = weakref.ref(w)

                def _do_delete() -> None:
                    obj = wr()
                    if obj is None or _qt_is_deleted(obj):
                        return
                    try:
                        obj.deleteLater()
                    except Exception:
                        pass

                QTimer.singleShot(0, _do_delete)
            except Exception:
                try:
                    w.deleteLater()
                except Exception:
                    pass

    def _clear_chain(self) -> None:
        try:
            self._hide_drop_indicator()
        except Exception:
            pass
        try:
            self._zone_layout_meta = {}
            self._hide_zone_visuals()
        except Exception:
            pass
        try:
            persistent = set()
            try:
                for ent in (self._track_instruments or {}).values():
                    w0 = ent.get("widget") if isinstance(ent, dict) else None
                    if w0 is not None:
                        persistent.add(w0)
            except Exception:
                persistent = set()

            while self.chain.count():
                it = self.chain.takeAt(0)
                w = it.widget()
                if w is None:
                    continue

                # Hide early to avoid flicker.
                try:
                    w.setVisible(False)
                except Exception:
                    pass

                # If this is a card wrapping a persistent instrument widget, detach it first.
                try:
                    inner = getattr(w, "inner_widget", None)
                    if inner is not None and inner in persistent:
                        # Keep persistent instrument widgets alive without ever becoming top-level.
                        self._stash_widget(inner, delete=False)
                except Exception:
                    pass

                # Cards themselves are not reused -> delete safely.
                self._stash_widget(w, delete=True)
        except Exception:
            pass

    def _emit_project_updated(self) -> None:
        try:
            proj = getattr(self._services, "project", None) if self._services else None
            if proj is not None and hasattr(proj, "project_updated"):
                proj.project_updated.emit()
        except Exception:
            pass

    def _get_project_track(self, track_id: str) -> Tuple[Any, Any, Any]:
        proj = getattr(self._services, "project", None) if self._services else None
        if proj is None:
            return None, None, None
        ctx = getattr(proj, "ctx", None)
        project_obj = getattr(ctx, "project", None) if ctx is not None else None
        if project_obj is None:
            return proj, None, None
        trk = _find_track(project_obj, track_id)
        return proj, project_obj, trk

    def _rebuild_audio_fx(self, project_obj: Any) -> None:
        ae = getattr(self._services, "audio_engine", None) if self._services else None
        try:
            if ae is not None and hasattr(ae, "rebuild_fx_maps"):
                ae.rebuild_fx_maps(project_obj)
        except Exception:
            pass

    def _restart_if_playing(self) -> None:
        try:
            transport = getattr(self._services, "transport", None) if self._services else None
            ae = getattr(self._services, "audio_engine", None) if self._services else None
            if transport is None or ae is None:
                return
            playing = bool(getattr(transport, "is_playing", False) or getattr(transport, "playing", False))
            if not playing:
                return
            try:
                ae.stop()
            except Exception:
                pass
            try:
                ae.start_arrangement_playback()
            except Exception:
                pass
        except Exception:
            pass
