"""Device Browser with Tabs for PyDAW.

Tabs:
- Samples (functional)
- Instruments (internal Python instruments)
- Effects (placeholder)
- Plugins (placeholder)
- Presets (placeholder)
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel
from PySide6.QtWidgets import QSizePolicy

from .sample_browser import SampleBrowserWidget
from .instrument_browser import InstrumentBrowserWidget
from .effects_browser import EffectsBrowserWidget
from .device_quicklist_tab import DeviceQuickListWidget
from .plugins_browser import PluginsBrowserWidget
from .browser_places_tab import BrowserPlacesTab


class DeviceBrowser(QWidget):
    def __init__(self, on_add_instrument: Optional[Callable[[str], None]] = None,
                 on_add_note_fx: Optional[Callable[[str], None]] = None,
                 on_add_audio_fx: Optional[Callable[[str], None]] = None,
                 get_add_scope: Optional[Callable[[str], tuple[str, str]]] = None,
                 audio_engine=None, transport=None, project_service=None, parent=None):
        super().__init__(parent)
        self._on_add_instrument = on_add_instrument
        self._on_add_note_fx = on_add_note_fx
        self._on_add_audio_fx = on_add_audio_fx
        self._get_add_scope = get_add_scope
        self._audio_engine = audio_engine
        self._transport = transport
        self._project_service = project_service
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Important for the main window: let this panel be shrunk "almost closed"
        # when the user drags the right dock separator.
        try:
            self.setMinimumWidth(0)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        except Exception:
            pass

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        try:
            self.tabs.setMinimumWidth(0)
            self.tabs.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        except Exception:
            pass

        # Critical for "fast schließen": QTabWidget's internal tab bar can
        # enforce a large minimum width (sum of all tab labels) when it expands.
        # We must allow scrolling tabs so the whole right dock can collapse.
        try:
            tb = self.tabs.tabBar()
            tb.setUsesScrollButtons(True)
            tb.setExpanding(False)
            try:
                tb.setElideMode(Qt.TextElideMode.ElideRight)
            except Exception:
                pass
            tb.setMinimumWidth(0)
            tb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        # Samples / Files
        self.samples_tab = SampleBrowserWidget(audio_engine=self._audio_engine, transport=self._transport, project_service=self._project_service)
        self.tabs.addTab(self.samples_tab, "🎵 Samples")

        # Visible Places/Favorites tab for fast access (Bitwig-style, UI-only)
        self.places_tab = BrowserPlacesTab(
            get_quick_dirs=lambda: getattr(self.samples_tab, "_quick_dirs", {}) or {},
            get_current_path=lambda: self.samples_tab.current_root_path(),
            on_open_path=self._open_samples_path,
        )
        self.tabs.addTab(self.places_tab, "⭐ Orte")

        # Instruments
        self.instruments_tab = InstrumentBrowserWidget(on_add_instrument=self._on_add_instrument, get_add_scope=self._get_add_scope)
        self.tabs.addTab(self.instruments_tab, "🎹 Instruments")

        # Effects (Bitwig/Ableton style Browser → Drag into Device Chain)
        self.effects_tab = EffectsBrowserWidget(
            on_add_note_fx=self._on_add_note_fx,
            on_add_audio_fx=self._on_add_audio_fx,
            get_add_scope=self._get_add_scope,
        )
        self.tabs.addTab(self.effects_tab, "🎚️ Effects")

        # Phase 4: Favorites/Recents visible inside Browser (additiv)
        self.favorites_tab = DeviceQuickListWidget(
            mode="favorites",
            on_add_instrument=self._on_add_instrument,
            on_add_note_fx=self._on_add_note_fx,
            on_add_audio_fx=self._on_add_audio_fx,
            get_add_scope=self._get_add_scope,
        )
        self.tabs.addTab(self.favorites_tab, "⭐ Favorites")

        self.recents_tab = DeviceQuickListWidget(
            mode="recents",
            on_add_instrument=self._on_add_instrument,
            on_add_note_fx=self._on_add_note_fx,
            on_add_audio_fx=self._on_add_audio_fx,
            get_add_scope=self._get_add_scope,
        )
        self.tabs.addTab(self.recents_tab, "🕘 Recents")

        # Plugins (LV2/LADSPA/DSSI/VST) — safe scanner/list + placeholder insert
        # (real hosting comes later, separate / risky task)
        self.plugins_tab = PluginsBrowserWidget(on_add_audio_fx=self._on_add_audio_fx, get_add_scope=self._get_add_scope)
        self.tabs.addTab(self.plugins_tab, "🔌 Plugins")

        # Presets placeholder
        self.presets_tab = self._placeholder(
            "📦 Presets\n\n"
            "Später: Preset-Browser für Devices/Instruments/FX.\n\n"
            "Status: PLACEHOLDER"
        )
        self.tabs.addTab(self.presets_tab, "📦 Presets")

        # Keep Favorites/Recents in sync (best-effort, no hard dependency)
        try:
            self.tabs.currentChanged.connect(lambda _i: self._refresh_quick_tabs())
        except Exception:
            pass
        try:
            self.tabs.currentChanged.connect(lambda _i: self._refresh_scope_badges())
        except Exception:
            pass
        try:
            self.instruments_tab.prefs_changed.connect(lambda: self._refresh_quick_tabs())
        except Exception:
            pass
        try:
            self.effects_tab.prefs_changed.connect(lambda: self._refresh_quick_tabs())
        except Exception:
            pass
        try:
            self.favorites_tab.prefs_changed.connect(lambda: self._refresh_quick_tabs())
        except Exception:
            pass
        try:
            self.recents_tab.prefs_changed.connect(lambda: self._refresh_quick_tabs())
        except Exception:
            pass

        layout.addWidget(self.tabs)

    def _open_samples_path(self, path_str: str) -> None:
        try:
            if hasattr(self, "samples_tab"):
                self.samples_tab.open_path(path_str)
            idx = self.tabs.indexOf(self.samples_tab)
            if idx >= 0:
                self.tabs.setCurrentIndex(idx)
        except Exception:
            pass



    def _refresh_scope_badges(self) -> None:
        for attr in ("instruments_tab", "effects_tab", "favorites_tab", "recents_tab", "plugins_tab"):
            try:
                w = getattr(self, attr, None)
                if w is not None and hasattr(w, "refresh_scope_badge"):
                    w.refresh_scope_badge()
            except Exception:
                pass

    def _refresh_quick_tabs(self) -> None:
        """Reload Favorites/Recents tabs (safe)."""
        try:
            if hasattr(self, "favorites_tab"):
                self.favorites_tab.reload()
        except Exception:
            pass
        try:
            if hasattr(self, "recents_tab"):
                self.recents_tab.reload()
        except Exception:
            pass
        try:
            if hasattr(self, "places_tab"):
                self.places_tab.reload()
        except Exception:
            pass

    def _placeholder(self, text: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lab = QLabel(text)
        lab.setWordWrap(True)
        lay.addWidget(lab)
        lay.addStretch(1)
        return w


    def set_selected_track(self, track_id: str) -> None:
        """Refresh track-aware browser hints/badges."""
        try:
            self._refresh_scope_badges()
        except Exception:
            pass
        return

        try:
            self.audio_fx_editor.set_track(track_id)
        except Exception:
            pass
