"""Pro-DAW-like Scale selector button (minimal).

This is intentionally small but practical:

- Shows the *currently selected* scale (e.g. "C Major")
- Provides a menu to select:
    - enable/disable scale constraint
    - root note (C..B)
    - scale (grouped by category)
    - mode: Snap or Reject

The selection is persisted via :mod:`pydaw.core.settings_store`.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, QSize, QRectF, QPointF, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QPainter, QPen, QPolygonF, QFontMetrics
from PySide6.QtWidgets import QMenu, QToolButton, QStyle, QStyleOptionToolButton
from pydaw.core.settings import SettingsKeys
from pydaw.core.settings_store import get_value, set_value
from pydaw.music.scales import (
    list_scale_categories,
    list_scales_in_category,
    pc_name,
)


class ScaleMenuButton(QToolButton):
    """A small toolbar button showing current scale, with dropdown menu."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keys = SettingsKeys()

        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip("Skalen-Menü (Scale Lock)")

        # Pro-DAW-ish visual hint (cyan accent, dark background)
        self.setStyleSheet(
            "QToolButton{padding:4px 8px;border-radius:6px;"
            "background:#1f252b;color:#e8f8ff;border:1px solid #2c3942;}"
            "QToolButton:hover{border:1px solid #00bcd4;color:#00e5ff;}"
        )

        self._rebuild_menu()
        self._refresh_text()

    # ------------------------------------------------------------------
    # Pro-DAW-like 12-dot scale badge rendering (requested)
    # ------------------------------------------------------------------
    def _scale_state(self):
        """Return (enabled, allowed_pcs_set, root_pc, label)."""
        self._defaults()
        enabled = bool(get_value(self._keys.scale_enabled, False))
        cat = str(get_value(self._keys.scale_category, "Keine Einschränkung"))
        name = str(get_value(self._keys.scale_name, "Alle Noten"))
        root = int(get_value(self._keys.scale_root_pc, 0) or 0) % 12
        allowed = None
        try:
            from pydaw.music.scales import allowed_pitch_classes
            if enabled and cat != "Keine Einschränkung":
                allowed = set(
                    allowed_pitch_classes(category=cat, name=name, root_pc=root)
                )
        except Exception:
            allowed = None
        label = self._current_label()
        return enabled, (allowed if allowed is not None else set(range(12))), root, label

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        fm = QFontMetrics(self.font())
        text = self._current_label()
        text_w = fm.horizontalAdvance(text)
        text_h = fm.height()
        # 2 rows of dots (piano layout: white keys bottom, black keys top)
        dot_r = 3
        # Width: 7 white keys (widest row)
        dots_w = 7 * (dot_r * 2) + 6 * 3
        w = max(text_w, dots_w) + 34  # padding + arrow
        # Height: text + gap + black row + gap + white row + padding
        # Black row: 6px, gap: 7px, white row: 6px, top padding: 3px, bottom padding: 4px
        h = text_h + 3 + 6 + 7 + 6 + 4
        return QSize(int(w), int(h))

    def paintEvent(self, _ev):  # noqa: N802 (Qt API)
        """Custom paint: dark pill + label + 12 dots, root highlighted."""
        opt = QStyleOptionToolButton()
        opt.initFrom(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        enabled, allowed, root, label = self._scale_state()

        # Colors (match our UI vibe: dark + cyan accents)
        bg = QColor("#1f252b")
        border = QColor("#2c3942")
        if opt.state & QStyle.StateFlag.State_MouseOver:
            border = QColor("#00bcd4")
        txt = QColor("#e8f8ff")

        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 7, 7)

        # Text
        fm = QFontMetrics(self.font())
        pad_x = 10
        pad_top = 6
        text_h = fm.height()
        text_rect = QRectF(r.left() + pad_x, r.top() + pad_top, r.width() - 26, text_h + 2)
        p.setPen(QPen(txt))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

        # Dropdown arrow (right)
        ax = r.right() - 14
        ay = r.top() + pad_top + (text_h / 2.0) + 1
        tri = QPolygonF(
            [QPointF(ax - 4, ay - 1), QPointF(ax + 4, ay - 1), QPointF(ax, ay + 4)]
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#7b8a95"))
        p.drawPolygon(tri)

        # Dots in piano-key layout (2 rows: white keys bottom, black keys top)
        # White keys (7): C(0), D(2), E(4), F(5), G(7), A(9), B(11)
        # Black keys (5): C#(1), D#(3), F#(6), G#(8), A#(10)
        dot_r = 3
        gap = 3
        
        # White keys layout (bottom row)
        white_keys = [0, 2, 4, 5, 7, 9, 11]
        white_w = 7 * (dot_r * 2) + 6 * gap
        
        dx0 = r.left() + pad_x
        # Center white keys row
        avail_w = r.width() - (pad_x * 2) - 16
        if avail_w > white_w:
            dx0 = r.left() + pad_x + (avail_w - white_w) / 2.0
        
        dy_white = r.top() + pad_top + text_h + 10  # Bottom row
        dy_black = r.top() + pad_top + text_h + 3   # Top row (higher)
        
        # Dot colors
        on = QColor("#00e5ff")    # cyan
        off = QColor("#3b4752")   # dark gray
        root_outline = QColor("#00bcd4") if enabled else QColor("#667782")
        
        # Draw white keys (bottom row)
        for idx, pc in enumerate(white_keys):
            x = dx0 + idx * (dot_r * 2 + gap)
            cy = dy_white + dot_r
            center = QPointF(x + dot_r, cy)
            in_scale = (pc in allowed) if enabled else False
            
            fill = on if in_scale else off
            if pc == root:
                p.setPen(QPen(root_outline, 1.6))
                p.setBrush(fill if enabled else QColor("#55626d"))
                p.drawEllipse(center, dot_r + 1, dot_r + 1)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(fill)
                p.drawEllipse(center, dot_r, dot_r)
        
        # Draw black keys (top row) - positioned between white keys
        # C# between C-D, D# between D-E, F# between F-G, G# between G-A, A# between A-B
        black_keys = [1, 3, 6, 8, 10]
        black_positions = [0.5, 1.5, 3.5, 4.5, 5.5]  # Between white key positions
        
        for pc, pos in zip(black_keys, black_positions):
            x = dx0 + pos * (dot_r * 2 + gap)
            cy = dy_black + dot_r
            center = QPointF(x + dot_r, cy)
            in_scale = (pc in allowed) if enabled else False
            
            fill = on if in_scale else off
            if pc == root:
                p.setPen(QPen(root_outline, 1.6))
                p.setBrush(fill if enabled else QColor("#55626d"))
                p.drawEllipse(center, dot_r + 1, dot_r + 1)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(fill)
                p.drawEllipse(center, dot_r, dot_r)

        p.end()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._refresh_text()
        self._rebuild_menu()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _defaults(self) -> None:
        if get_value(self._keys.scale_root_pc, None) is None:
            set_value(self._keys.scale_root_pc, 0)
        if get_value(self._keys.scale_category, None) is None:
            set_value(self._keys.scale_category, "Keine Einschränkung")
        if get_value(self._keys.scale_name, None) is None:
            set_value(self._keys.scale_name, "Alle Noten")
        if get_value(self._keys.scale_mode, None) is None:
            set_value(self._keys.scale_mode, "snap")
        if get_value(self._keys.scale_enabled, None) is None:
            set_value(self._keys.scale_enabled, False)
        if get_value(self._keys.scale_visualize, None) is None:
            set_value(self._keys.scale_visualize, True)

    def _current_label(self) -> str:
        self._defaults()
        enabled = bool(get_value(self._keys.scale_enabled, False))
        cat = str(get_value(self._keys.scale_category, "Keine Einschränkung"))
        name = str(get_value(self._keys.scale_name, "Alle Noten"))
        root = int(get_value(self._keys.scale_root_pc, 0) or 0)
        mode = str(get_value(self._keys.scale_mode, "snap") or "snap")
        if not enabled or cat == "Keine Einschränkung":
            return "Scale: Off"
        mm = "Snap" if mode.lower().strip() != "reject" else "Reject"
        return f"{pc_name(root)} {name} ({mm})"

    def _refresh_text(self) -> None:
        self.setText(self._current_label())

    def _set_and_emit(self, **kv) -> None:
        for k, v in kv.items():
            set_value(k, v)
        self._refresh_text()
        # Ensure checkmarks update immediately (Mode/Root/Scale).
        # Without this, Qt may keep the previous checked-state until the menu
        # is opened again, which looks like both Snap/Reject are active.
        try:
            self._rebuild_menu()
        except Exception:
            pass
        self.changed.emit()

    def _rebuild_menu(self) -> None:
        self._defaults()

        m = QMenu(self)

        # Enable toggle
        enabled = bool(get_value(self._keys.scale_enabled, False))
        act_enable = QAction("Scale Lock aktiv", self)
        act_enable.setCheckable(True)
        act_enable.setChecked(enabled)
        act_enable.triggered.connect(lambda chk: self._set_and_emit(**{self._keys.scale_enabled: bool(chk)}))
        m.addAction(act_enable)

        # Visual hints (Pro-DAW-like cyan dots)
        act_vis = QAction("Scale-Hints (Cyan Dots)", self)
        act_vis.setCheckable(True)
        act_vis.setChecked(bool(get_value(self._keys.scale_visualize, True)))
        act_vis.triggered.connect(lambda chk: self._set_and_emit(**{self._keys.scale_visualize: bool(chk)}))
        m.addAction(act_vis)


        # Mode
        m.addSeparator()
        mode_menu = m.addMenu("Mode")
        cur_mode = str(get_value(self._keys.scale_mode, "snap") or "snap").lower().strip()

        # Exclusive action group to avoid both being checked at once.
        g_mode = QActionGroup(self)
        g_mode.setExclusive(True)

        act_snap = QAction("Snap (zur nächstgelegenen Note)", self)
        act_snap.setCheckable(True)
        act_snap.setChecked(cur_mode != "reject")
        act_snap.setActionGroup(g_mode)
        act_snap.triggered.connect(lambda: self._set_and_emit(**{self._keys.scale_mode: "snap"}))

        act_rej = QAction("Reject (nur erlaubte Noten)", self)
        act_rej.setCheckable(True)
        act_rej.setChecked(cur_mode == "reject")
        act_rej.setActionGroup(g_mode)
        act_rej.triggered.connect(lambda: self._set_and_emit(**{self._keys.scale_mode: "reject"}))

        mode_menu.addAction(act_snap)
        mode_menu.addAction(act_rej)

        # Root note
        m.addSeparator()
        root_menu = m.addMenu("Root")
        cur_root = int(get_value(self._keys.scale_root_pc, 0) or 0)
        for pc in range(12):
            a = QAction(pc_name(pc), self)
            a.setCheckable(True)
            a.setChecked(pc == (cur_root % 12))
            a.triggered.connect(lambda _=False, pc=pc: self._set_and_emit(**{self._keys.scale_root_pc: int(pc)}))
            root_menu.addAction(a)

        # Scales grouped by category
        m.addSeparator()
        cur_cat = str(get_value(self._keys.scale_category, "Keine Einschränkung"))
        cur_name = str(get_value(self._keys.scale_name, "Alle Noten"))

        scales_menu = m.addMenu("Scale")
        for cat in list_scale_categories():
            sub = scales_menu.addMenu(str(cat))
            for name in list_scales_in_category(str(cat)):
                a = QAction(str(name), self)
                a.setCheckable(True)
                a.setChecked((str(cat) == cur_cat) and (str(name) == cur_name))
                a.triggered.connect(
                    lambda _=False, cat=str(cat), name=str(name): self._set_and_emit(
                        **{self._keys.scale_category: cat, self._keys.scale_name: name}
                    )
                )
                sub.addAction(a)

        self.setMenu(m)
