"""Screen Layout Manager + Detachable Panel System (v0.0.20.444).

Bitwig-Studio-style multi-monitor layout system:
- Any panel (Automation, Editor, Mixer, Device, Browser) can be detached
  as a free-floating window and placed on any monitor.
- Layout presets for 1, 2, and 3 monitors.
- State is persisted via SettingsStore.

Architecture:
- DetachablePanel: wraps a QWidget; can toggle between docked (inside the
  main window) and floating (separate top-level window).
- ScreenLayoutManager: orchestrates all detachable panels and applies
  preset layouts based on available screens.
- LayoutPreset: data class describing which panels go on which screen.

Safety:
- All Qt operations are wrapped in try/except to never crash the main app.
- Re-docking always returns widgets to their original parent/position.
- Panels that fail to detach silently stay docked.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QRect, Signal as Signal
from PySide6.QtGui import QGuiApplication, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pydaw.core.settings_store import get_value, set_value


# ---------------------------------------------------------------------------
# Panel ID enum — canonical names for all detachable panels
# ---------------------------------------------------------------------------

class PanelId(str, Enum):
    ARRANGER = "arranger"
    EDITOR = "editor"
    MIXER = "mixer"
    DEVICE = "device"
    BROWSER = "browser"
    CLIP_LAUNCHER = "clip_launcher"
    AUTOMATION = "automation"


# ---------------------------------------------------------------------------
# DetachablePanel — wraps a widget for dock ↔ float toggling
# ---------------------------------------------------------------------------

class _FloatingWindow(QWidget):
    """Top-level window that hosts a detached panel.

    When the user closes this window (X button or Alt+F4), we emit
    ``close_requested`` so the panel can re-dock instead of being destroyed.
    """

    close_requested = Signal()

    def __init__(self, title: str, parent: QWidget | None = None):
        # Use Qt.WindowType.Window so it's a real top-level window
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(title)
        self.setMinimumSize(400, 250)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def set_content(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        # Don't actually close — re-dock instead
        event.ignore()
        self.close_requested.emit()


class DetachablePanel:
    """Manages dock/float state for a single panel.

    Usage::

        panel = DetachablePanel(
            panel_id=PanelId.AUTOMATION,
            title="Automation",
            widget=my_automation_widget,
            dock_parent=some_splitter_or_layout,
            dock_restore_cb=lambda w: splitter.insertWidget(1, w),
        )
        panel.toggle()  # detach or re-dock
    """

    def __init__(
        self,
        panel_id: PanelId,
        title: str,
        widget: QWidget,
        dock_parent: QWidget | None = None,
        dock_restore_cb: Callable[[QWidget], None] | None = None,
        main_window: QMainWindow | None = None,
    ):
        self.panel_id = panel_id
        self.title = title
        self.widget = widget
        self._dock_parent = dock_parent
        self._dock_restore_cb = dock_restore_cb
        self._main_window = main_window
        self._floating_window: _FloatingWindow | None = None
        self._is_detached = False
        # Remember the widget's visibility before detaching
        self._was_visible = True

    @property
    def is_detached(self) -> bool:
        return self._is_detached

    def detach(self, geometry: QRect | None = None) -> bool:
        """Pop the widget out as a floating window.

        Returns True on success.
        """
        if self._is_detached:
            return True
        try:
            self._was_visible = self.widget.isVisible()

            # Create floating window
            self._floating_window = _FloatingWindow(
                f"{self.title} — Py_DAW",
                parent=None,
            )
            self._floating_window.close_requested.connect(self.dock)

            # Reparent widget into floating window
            self.widget.setParent(self._floating_window)
            self._floating_window.set_content(self.widget)
            self.widget.setVisible(True)

            # Position
            if geometry and geometry.isValid():
                self._floating_window.setGeometry(geometry)
            else:
                self._floating_window.resize(800, 400)
                # Center on current screen
                try:
                    screen = QGuiApplication.primaryScreen()
                    if self._main_window:
                        screen = self._main_window.screen() or screen
                    if screen:
                        sg = screen.availableGeometry()
                        fg = self._floating_window.frameGeometry()
                        fg.moveCenter(sg.center())
                        self._floating_window.move(fg.topLeft())
                except Exception:
                    pass

            self._floating_window.show()
            self._floating_window.raise_()
            self._floating_window.activateWindow()
            self._is_detached = True

            # Persist state
            try:
                set_value(f"screen_layout.{self.panel_id.value}.detached", True)
                g = self._floating_window.geometry()
                set_value(
                    f"screen_layout.{self.panel_id.value}.geometry",
                    f"{g.x()},{g.y()},{g.width()},{g.height()}",
                )
            except Exception:
                pass

            return True
        except Exception:
            traceback.print_exc()
            self._is_detached = False
            return False

    def dock(self) -> bool:
        """Re-dock the widget back into the main window.

        Returns True on success.
        """
        if not self._is_detached:
            return True
        try:
            # Reparent back
            if self._dock_restore_cb:
                self.widget.setParent(self._dock_parent)
                self._dock_restore_cb(self.widget)
            elif self._dock_parent:
                self.widget.setParent(self._dock_parent)

            self.widget.setVisible(self._was_visible)

            # Destroy floating window
            if self._floating_window:
                try:
                    self._floating_window.close_requested.disconnect()
                except Exception:
                    pass
                self._floating_window.hide()
                self._floating_window.deleteLater()
                self._floating_window = None

            self._is_detached = False

            # Persist state
            try:
                set_value(f"screen_layout.{self.panel_id.value}.detached", False)
            except Exception:
                pass

            return True
        except Exception:
            traceback.print_exc()
            return False

    def toggle(self) -> None:
        """Toggle between docked and floating."""
        if self._is_detached:
            self.dock()
        else:
            self.detach()

    def move_to_screen(self, screen_index: int) -> None:
        """Move floating window to a specific screen."""
        if not self._is_detached or not self._floating_window:
            return
        try:
            screens = QGuiApplication.screens()
            if screen_index < 0 or screen_index >= len(screens):
                return
            sg = screens[screen_index].availableGeometry()
            w = self._floating_window.width()
            h = self._floating_window.height()
            x = sg.x() + (sg.width() - w) // 2
            y = sg.y() + (sg.height() - h) // 2
            self._floating_window.move(x, y)
            self._floating_window.resize(w, h)
        except Exception:
            pass

    def save_geometry(self) -> None:
        """Persist current geometry."""
        if self._floating_window and self._is_detached:
            try:
                g = self._floating_window.geometry()
                set_value(
                    f"screen_layout.{self.panel_id.value}.geometry",
                    f"{g.x()},{g.y()},{g.width()},{g.height()}",
                )
            except Exception:
                pass

    def restore_geometry(self) -> QRect | None:
        """Load persisted geometry."""
        try:
            raw = str(get_value(f"screen_layout.{self.panel_id.value}.geometry", ""))
            if not raw:
                return None
            parts = raw.split(",")
            if len(parts) != 4:
                return None
            return QRect(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Layout Presets
# ---------------------------------------------------------------------------

@dataclass
class PanelPlacement:
    """Describes where a panel should appear in a layout."""
    panel_id: PanelId
    screen: int = 0  # 0 = primary, 1 = secondary, 2 = tertiary
    detached: bool = False
    visible: bool = True
    # Relative position on the target screen (0..1)
    rel_x: float = 0.0
    rel_y: float = 0.0
    rel_w: float = 1.0
    rel_h: float = 1.0


@dataclass
class LayoutPreset:
    """A named layout preset."""
    key: str
    label: str  # user-facing German label
    description: str = ""
    min_screens: int = 1
    max_screens: int = 99
    placements: list[PanelPlacement] = field(default_factory=list)


# Pre-defined presets (matching the Bitwig-style menu from the screenshot)
LAYOUT_PRESETS: list[LayoutPreset] = [
    # --- 1 Monitor ---
    LayoutPreset(
        key="1_large",
        label="Ein Bildschirm (Groß)",
        description="Alles auf einem großen Bildschirm. Arranger oben, Editor/Mixer unten.",
        min_screens=1, max_screens=99,
        placements=[
            PanelPlacement(PanelId.ARRANGER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.EDITOR, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.MIXER, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.DEVICE, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.BROWSER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.AUTOMATION, screen=0, detached=False, visible=True),
        ],
    ),
    LayoutPreset(
        key="1_small",
        label="Ein Bildschirm (Klein)",
        description="Kompaktes Layout für kleine Bildschirme. Browser versteckt.",
        min_screens=1, max_screens=99,
        placements=[
            PanelPlacement(PanelId.ARRANGER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.EDITOR, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.MIXER, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.DEVICE, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.BROWSER, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.AUTOMATION, screen=0, detached=False, visible=False),
        ],
    ),
    LayoutPreset(
        key="1_tablet",
        label="Tablet",
        description="Touch-optimiertes Layout. Große Buttons, wenige Panels.",
        min_screens=1, max_screens=1,
        placements=[
            PanelPlacement(PanelId.ARRANGER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.EDITOR, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.MIXER, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.DEVICE, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.BROWSER, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.AUTOMATION, screen=0, detached=False, visible=False),
        ],
    ),
    # --- 2 Monitors ---
    LayoutPreset(
        key="2_studio",
        label="Zwei Bildschirme (Studio)",
        description="Monitor 1: Arranger + Browser. Monitor 2: Editor + Mixer + Device.",
        min_screens=2, max_screens=99,
        placements=[
            PanelPlacement(PanelId.ARRANGER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.BROWSER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.AUTOMATION, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.EDITOR, screen=1, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.0, rel_w=1.0, rel_h=0.5),
            PanelPlacement(PanelId.MIXER, screen=1, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.5, rel_w=1.0, rel_h=0.5),
            PanelPlacement(PanelId.DEVICE, screen=1, detached=False, visible=False),
        ],
    ),
    LayoutPreset(
        key="2_arranger_mixer",
        label="Zwei Bildschirme (Arranger/Mixer)",
        description="Monitor 1: Arranger komplett. Monitor 2: Mixer komplett.",
        min_screens=2, max_screens=99,
        placements=[
            PanelPlacement(PanelId.ARRANGER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.BROWSER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.EDITOR, screen=0, detached=False, visible=False),
            PanelPlacement(PanelId.AUTOMATION, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.MIXER, screen=1, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.0, rel_w=1.0, rel_h=1.0),
            PanelPlacement(PanelId.DEVICE, screen=1, detached=False, visible=False),
        ],
    ),
    LayoutPreset(
        key="2_main_detail",
        label="Zwei Bildschirme (Hauptbildschirm/Detail)",
        description="Monitor 1: Arranger + Automation. Monitor 2: Editor + Device + Browser.",
        min_screens=2, max_screens=99,
        placements=[
            PanelPlacement(PanelId.ARRANGER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.AUTOMATION, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.EDITOR, screen=1, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.0, rel_w=0.7, rel_h=0.5),
            PanelPlacement(PanelId.DEVICE, screen=1, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.5, rel_w=0.7, rel_h=0.5),
            PanelPlacement(PanelId.BROWSER, screen=1, detached=True, visible=True,
                           rel_x=0.7, rel_y=0.0, rel_w=0.3, rel_h=1.0),
            PanelPlacement(PanelId.MIXER, screen=0, detached=False, visible=False),
        ],
    ),
    LayoutPreset(
        key="2_studio_touch",
        label="Zwei Bildschirme (Studio/Touch)",
        description="Monitor 1: Arranger. Monitor 2: Mixer + Device (Touch-optimiert).",
        min_screens=2, max_screens=99,
        placements=[
            PanelPlacement(PanelId.ARRANGER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.BROWSER, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.EDITOR, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.AUTOMATION, screen=0, detached=False, visible=True),
            PanelPlacement(PanelId.MIXER, screen=1, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.0, rel_w=1.0, rel_h=0.6),
            PanelPlacement(PanelId.DEVICE, screen=1, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.6, rel_w=1.0, rel_h=0.4),
        ],
    ),
    # --- 3 Monitors ---
    LayoutPreset(
        key="3_full",
        label="Drei Bildschirme",
        description="Monitor 1: Mixer. Monitor 2: Arranger + Browser. Monitor 3: Editor + Device.",
        min_screens=3, max_screens=99,
        placements=[
            PanelPlacement(PanelId.MIXER, screen=0, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.0, rel_w=1.0, rel_h=1.0),
            PanelPlacement(PanelId.ARRANGER, screen=1, detached=False, visible=True),
            PanelPlacement(PanelId.BROWSER, screen=1, detached=False, visible=True),
            PanelPlacement(PanelId.AUTOMATION, screen=1, detached=False, visible=True),
            PanelPlacement(PanelId.EDITOR, screen=2, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.0, rel_w=1.0, rel_h=0.5),
            PanelPlacement(PanelId.DEVICE, screen=2, detached=True, visible=True,
                           rel_x=0.0, rel_y=0.5, rel_w=1.0, rel_h=0.5),
        ],
    ),
]


# ---------------------------------------------------------------------------
# ScreenLayoutManager
# ---------------------------------------------------------------------------

class ScreenLayoutManager:
    """Orchestrates all detachable panels and applies layout presets.

    Usage::

        mgr = ScreenLayoutManager(main_window)
        mgr.register_panel(PanelId.AUTOMATION, "Automation", widget, ...)
        mgr.apply_preset("2_studio")
    """

    def __init__(self, main_window: QMainWindow):
        self._main_window = main_window
        self._panels: dict[PanelId, DetachablePanel] = {}
        self._active_preset_key: str = ""

    def register_panel(
        self,
        panel_id: PanelId,
        title: str,
        widget: QWidget,
        dock_parent: QWidget | None = None,
        dock_restore_cb: Callable[[QWidget], None] | None = None,
    ) -> DetachablePanel:
        """Register a panel for layout management."""
        dp = DetachablePanel(
            panel_id=panel_id,
            title=title,
            widget=widget,
            dock_parent=dock_parent,
            dock_restore_cb=dock_restore_cb,
            main_window=self._main_window,
        )
        self._panels[panel_id] = dp
        return dp

    def get_panel(self, panel_id: PanelId) -> DetachablePanel | None:
        return self._panels.get(panel_id)

    @property
    def panels(self) -> dict[PanelId, DetachablePanel]:
        return dict(self._panels)

    def available_screens(self) -> int:
        """Return the number of connected screens."""
        try:
            return len(QGuiApplication.screens())
        except Exception:
            return 1

    def available_presets(self) -> list[LayoutPreset]:
        """Return presets that match the current screen count."""
        n = self.available_screens()
        return [p for p in LAYOUT_PRESETS if p.min_screens <= n]

    def apply_preset(self, preset_key: str) -> bool:
        """Apply a layout preset.

        Returns True on success.
        """
        preset = next((p for p in LAYOUT_PRESETS if p.key == preset_key), None)
        if not preset:
            return False

        screens = QGuiApplication.screens()
        n_screens = len(screens)

        # First: dock everything back
        for dp in self._panels.values():
            try:
                dp.dock()
            except Exception:
                pass

        # Apply placements
        for placement in preset.placements:
            dp = self._panels.get(placement.panel_id)
            if dp is None:
                continue

            try:
                if placement.detached and placement.screen < n_screens:
                    # Calculate geometry from relative coords
                    sg = screens[placement.screen].availableGeometry()
                    x = int(sg.x() + placement.rel_x * sg.width())
                    y = int(sg.y() + placement.rel_y * sg.height())
                    w = int(placement.rel_w * sg.width())
                    h = int(placement.rel_h * sg.height())
                    geo = QRect(x, y, max(200, w), max(150, h))
                    dp.detach(geometry=geo)
                elif placement.detached and placement.screen >= n_screens:
                    # Screen not available — keep docked but visible
                    dp.widget.setVisible(placement.visible)
                else:
                    # Stay docked
                    dp.widget.setVisible(placement.visible)
            except Exception:
                traceback.print_exc()

        self._active_preset_key = preset_key

        # Persist active preset
        try:
            set_value("screen_layout.active_preset", preset_key)
        except Exception:
            pass

        return True

    def dock_all(self) -> None:
        """Re-dock all panels."""
        for dp in self._panels.values():
            try:
                dp.dock()
            except Exception:
                pass

    def shutdown(self) -> None:
        """v0.0.20.625: Clean shutdown — dock all + clear references to prevent SIP SEGFAULT."""
        self.dock_all()
        # Destroy any remaining floating windows immediately (not deleteLater)
        for dp in self._panels.values():
            try:
                fw = getattr(dp, '_floating_window', None)
                if fw is not None:
                    try:
                        fw.close()
                    except Exception:
                        pass
                    dp._floating_window = None
                # Clear callbacks that hold closures over QWidgets
                dp._dock_restore_cb = None
                dp._dock_parent = None
            except Exception:
                pass
        self._panels.clear()

    def save_state(self) -> None:
        """Persist geometry of all floating panels."""
        for dp in self._panels.values():
            try:
                dp.save_geometry()
            except Exception:
                pass

    def restore_state(self) -> None:
        """Restore previously detached panels from persisted state."""
        for panel_id, dp in self._panels.items():
            try:
                raw = get_value(f"screen_layout.{panel_id.value}.detached", False)
                was_detached = str(raw).lower() in ("true", "1", "yes")
                if was_detached:
                    geo = dp.restore_geometry()
                    dp.detach(geometry=geo)
            except Exception:
                pass

    @property
    def active_preset_key(self) -> str:
        if not self._active_preset_key:
            try:
                self._active_preset_key = str(
                    get_value("screen_layout.active_preset", "")
                )
            except Exception:
                pass
        return self._active_preset_key
