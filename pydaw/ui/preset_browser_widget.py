# -*- coding: utf-8 -*-
"""Preset Browser Widget — reusable QWidget for plugin preset management.

Embeds into any Device-Widget (VST3, CLAP, LV2, built-in) and provides:
- Preset dropdown with search
- Category filter (All / Factory / User / Favorites)
- Save / Delete / Rename
- Favorite toggle (⭐)
- A/B comparison (two slots for instant switching)
- Undo/Redo for parameter changes

Design goals:
- SAFE: Never crashes the host. All callbacks wrapped in try/except.
- Decoupled: Communicates with the plugin via callbacks (get_state, set_state).
- Compact: Fits into a single row when collapsed, expandable for full browser.

v0.0.20.652 — AP4 Phase 4B: Preset Browser Widget
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QMenu,
    QInputDialog,
    QMessageBox,
    QToolButton,
    QSizePolicy,
)

from pydaw.services.preset_browser_service import (
    PresetInfo,
    get_preset_browser_service,
    get_plugin_state_manager,
)

log = logging.getLogger(__name__)


def _qt_is_deleted(obj: Any) -> bool:
    """Best-effort check whether a PyQt wrapper's underlying QObject is deleted."""
    if obj is None:
        return True
    try:
        from PySide6 import sip  # type: ignore
        return bool(sip.isdeleted(obj))
    except Exception:
        try:
            import sip  # type: ignore
            return bool(sip.isdeleted(obj))
        except Exception:
            return False


class PresetBrowserWidget(QWidget):
    """Compact preset browser widget for embedding in device panels.

    Usage:
        browser = PresetBrowserWidget(
            plugin_type="vst3",
            plugin_id="ext.vst3:/usr/lib/vst3/MyPlugin.vst3",
            device_id="dev_abc123",
            get_state_fn=lambda: plugin.get_raw_state_b64(),
            set_state_fn=lambda b64: plugin.set_state_from_b64(b64),
            get_params_fn=lambda: plugin.get_current_values(),
            vst3_path="/usr/lib/vst3/MyPlugin.vst3",
        )
        layout.addWidget(browser)

    Signals:
        preset_loaded(str): Emitted when a preset is loaded (name).
        state_changed(): Emitted when state was modified (for auto-save triggers).
    """

    preset_loaded = Signal(str)
    state_changed = Signal()

    def __init__(
        self,
        plugin_type: str = "vst3",
        plugin_id: str = "",
        device_id: str = "",
        track_id: str = "",
        get_state_fn: Optional[Callable[[], str]] = None,     # returns Base64 state
        set_state_fn: Optional[Callable[[str], bool]] = None,  # accepts Base64, returns success
        get_params_fn: Optional[Callable[[], Dict[str, float]]] = None,
        set_params_fn: Optional[Callable[[Dict[str, float]], None]] = None,
        vst3_path: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._plugin_type = str(plugin_type or "")
        self._plugin_id = str(plugin_id or "")
        self._device_id = str(device_id or "")
        self._track_id = str(track_id or "")
        self._get_state_fn = get_state_fn
        self._set_state_fn = set_state_fn
        self._get_params_fn = get_params_fn
        self._set_params_fn = set_params_fn
        self._vst3_path = str(vst3_path or "")
        self._all_presets: List[PresetInfo] = []
        self._filtered_presets: List[PresetInfo] = []
        self._current_category = "All"
        self._block_combo_signal = False

        self._svc = get_preset_browser_service()
        self._state_mgr = get_plugin_state_manager()

        self._build_ui()

        # Deferred initial scan
        QTimer.singleShot(80, self._refresh_presets)

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the compact preset browser UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        # ── Row 1: Preset selector + A/B ──
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(3)

        # Category filter
        self._cmb_category = QComboBox()
        self._cmb_category.setFixedWidth(75)
        self._cmb_category.setFixedHeight(22)
        self._cmb_category.setToolTip("Preset-Kategorie filtern")
        self._cmb_category.setStyleSheet("QComboBox { font-size: 9px; }")
        self._cmb_category.addItems(["All", "Favorites", "Factory", "User"])
        self._cmb_category.currentTextChanged.connect(self._on_category_changed)
        row1.addWidget(self._cmb_category)

        # Preset combo
        self._cmb_preset = QComboBox()
        self._cmb_preset.setFixedHeight(22)
        self._cmb_preset.setMinimumWidth(120)
        self._cmb_preset.setToolTip("Preset auswählen")
        self._cmb_preset.setStyleSheet("QComboBox { font-size: 10px; }")
        self._cmb_preset.currentIndexChanged.connect(self._on_preset_selected)
        row1.addWidget(self._cmb_preset, 1)

        # Prev / Next buttons
        btn_prev = QPushButton("◀")
        btn_prev.setFixedSize(22, 22)
        btn_prev.setToolTip("Vorheriges Preset")
        btn_prev.clicked.connect(self._prev_preset)
        row1.addWidget(btn_prev)

        btn_next = QPushButton("▶")
        btn_next.setFixedSize(22, 22)
        btn_next.setToolTip("Nächstes Preset")
        btn_next.clicked.connect(self._next_preset)
        row1.addWidget(btn_next)

        # Favorite toggle
        self._btn_fav = QPushButton("☆")
        self._btn_fav.setFixedSize(22, 22)
        self._btn_fav.setToolTip("Als Favorit markieren")
        self._btn_fav.setStyleSheet("QPushButton { font-size: 12px; }")
        self._btn_fav.clicked.connect(self._toggle_favorite)
        row1.addWidget(self._btn_fav)

        # A/B toggle
        self._btn_ab = QPushButton("A")
        self._btn_ab.setFixedSize(28, 22)
        self._btn_ab.setToolTip("A/B Vergleich — Klick zum Wechseln")
        self._btn_ab.setStyleSheet(
            "QPushButton { font-weight: bold; font-size: 10px; "
            "background-color: #2d5a27; color: #7bd389; border-radius: 3px; }"
        )
        self._btn_ab.clicked.connect(self._toggle_ab)
        row1.addWidget(self._btn_ab)

        main_layout.addLayout(row1)

        # ── Row 2: Search + actions ──
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(3)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Presets suchen…")
        self._search.setFixedHeight(20)
        self._search.setStyleSheet("QLineEdit { font-size: 9px; }")
        self._search.textChanged.connect(self._on_search_changed)
        row2.addWidget(self._search, 1)

        # Save button
        btn_save = QPushButton("💾")
        btn_save.setFixedSize(24, 20)
        btn_save.setToolTip("Aktuellen Zustand als Preset speichern")
        btn_save.clicked.connect(self._save_preset)
        row2.addWidget(btn_save)

        # More actions menu
        self._btn_menu = QPushButton("⋯")
        self._btn_menu.setFixedSize(24, 20)
        self._btn_menu.setToolTip("Weitere Aktionen")
        self._btn_menu.clicked.connect(self._show_actions_menu)
        row2.addWidget(self._btn_menu)

        # Undo / Redo
        self._btn_undo = QPushButton("↩")
        self._btn_undo.setFixedSize(24, 20)
        self._btn_undo.setToolTip("Undo (Parameter-Änderung rückgängig)")
        self._btn_undo.setEnabled(False)
        self._btn_undo.clicked.connect(self._on_undo)
        row2.addWidget(self._btn_undo)

        self._btn_redo = QPushButton("↪")
        self._btn_redo.setFixedSize(24, 20)
        self._btn_redo.setToolTip("Redo")
        self._btn_redo.setEnabled(False)
        self._btn_redo.clicked.connect(self._on_redo)
        row2.addWidget(self._btn_redo)

        main_layout.addLayout(row2)

        # Status label (optional)
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("font-size: 9px; color: #888; font-style: italic;")
        self._lbl_status.setVisible(False)
        main_layout.addWidget(self._lbl_status)

        # Undo button state refresh timer
        self._undo_refresh = QTimer(self)
        self._undo_refresh.setInterval(1000)
        self._undo_refresh.timeout.connect(self._refresh_undo_buttons)
        self._undo_refresh.start()

    # ── Preset scanning ───────────────────────────────────────────────────

    def _refresh_presets(self) -> None:
        """Rescan presets and update the combo box."""
        try:
            if _qt_is_deleted(self):
                return
            self._all_presets = self._svc.scan_all_presets(
                self._plugin_type, self._plugin_id, self._vst3_path,
            )
            self._apply_filter()
            self._update_category_combo()
        except Exception as e:
            log.debug("_refresh_presets error: %s", e)

    def _update_category_combo(self) -> None:
        """Update the category dropdown based on available presets."""
        try:
            if _qt_is_deleted(self._cmb_category):
                return
            cats = self._svc.get_categories(self._all_presets)
            current = self._cmb_category.currentText()
            self._cmb_category.blockSignals(True)
            self._cmb_category.clear()
            self._cmb_category.addItems(cats)
            idx = self._cmb_category.findText(current)
            if idx >= 0:
                self._cmb_category.setCurrentIndex(idx)
            self._cmb_category.blockSignals(False)
        except Exception:
            pass

    def _apply_filter(self) -> None:
        """Filter presets by current category and search text, update combo."""
        try:
            if _qt_is_deleted(self._cmb_preset):
                return
            search = self._search.text() if not _qt_is_deleted(self._search) else ""
            cat = self._current_category if self._current_category != "All" else ""
            self._filtered_presets = self._svc.filter_presets(
                self._all_presets, search=search, category=cat,
            )
            # Remember current selection
            current_text = self._cmb_preset.currentText()
            self._block_combo_signal = True
            self._cmb_preset.clear()
            self._cmb_preset.addItem("(kein Preset)")
            for p in self._filtered_presets:
                prefix = "⭐ " if p.is_favorite else ""
                factory_tag = " [F]" if p.is_factory else ""
                self._cmb_preset.addItem(f"{prefix}{p.name}{factory_tag}")
            # Restore selection
            idx = self._cmb_preset.findText(current_text)
            if idx >= 0:
                self._cmb_preset.setCurrentIndex(idx)
            self._block_combo_signal = False
        except Exception:
            self._block_combo_signal = False

    # ── Event handlers ────────────────────────────────────────────────────

    def _on_category_changed(self, category: str) -> None:
        try:
            self._current_category = str(category or "All")
            self._apply_filter()
        except Exception:
            pass

    def _on_search_changed(self, text: str) -> None:
        try:
            self._apply_filter()
        except Exception:
            pass

    def _on_preset_selected(self, index: int) -> None:
        """Load the selected preset into the plugin."""
        if self._block_combo_signal:
            return
        if index <= 0:
            return
        try:
            preset_idx = index - 1  # -1 because of "(kein Preset)" item
            if preset_idx < 0 or preset_idx >= len(self._filtered_presets):
                return
            preset = self._filtered_presets[preset_idx]
            self._load_preset_into_plugin(preset)
        except Exception as e:
            self._show_status(f"Fehler: {e}")

    def _load_preset_into_plugin(self, preset: PresetInfo) -> None:
        """Load a preset's state into the running plugin."""
        try:
            # Push current state to undo before loading new preset
            self._push_current_to_undo("Vor Preset-Wechsel")

            data_b64 = self._svc.load_preset_b64(preset)
            if not data_b64:
                self._show_status(f"Preset '{preset.name}': keine Daten")
                return

            if self._set_state_fn is not None:
                ok = self._set_state_fn(data_b64)
                if ok:
                    self._show_status(f"✓ {preset.name}")
                    self._update_fav_button(preset.name)
                    self.preset_loaded.emit(preset.name)
                else:
                    self._show_status(f"Fehler beim Laden: {preset.name}")
            else:
                self._show_status("Kein set_state callback")
        except Exception as e:
            self._show_status(f"Fehler: {e}")

    def _prev_preset(self) -> None:
        """Navigate to previous preset."""
        try:
            idx = self._cmb_preset.currentIndex()
            if idx > 1:  # > 1 because index 0 is "(kein Preset)"
                self._cmb_preset.setCurrentIndex(idx - 1)
            elif len(self._filtered_presets) > 0:
                self._cmb_preset.setCurrentIndex(self._cmb_preset.count() - 1)
        except Exception:
            pass

    def _next_preset(self) -> None:
        """Navigate to next preset."""
        try:
            idx = self._cmb_preset.currentIndex()
            if idx < self._cmb_preset.count() - 1:
                self._cmb_preset.setCurrentIndex(idx + 1)
            elif len(self._filtered_presets) > 0:
                self._cmb_preset.setCurrentIndex(1)
        except Exception:
            pass

    def _toggle_favorite(self) -> None:
        """Toggle favorite status for the current preset."""
        try:
            idx = self._cmb_preset.currentIndex() - 1
            if idx < 0 or idx >= len(self._filtered_presets):
                return
            preset = self._filtered_presets[idx]
            is_fav = self._svc.toggle_favorite(
                self._plugin_type, self._plugin_id, preset.name,
            )
            preset.is_favorite = is_fav
            self._update_fav_button(preset.name)
            self._show_status(f"{'⭐ Favorit' if is_fav else '☆ Kein Favorit'}: {preset.name}")
            # Refresh display
            self._refresh_presets()
        except Exception as e:
            self._show_status(f"Fehler: {e}")

    def _update_fav_button(self, preset_name: str = "") -> None:
        """Update the favorite button appearance."""
        try:
            if not preset_name:
                self._btn_fav.setText("☆")
                return
            is_fav = self._svc.is_favorite(self._plugin_type, self._plugin_id, preset_name)
            self._btn_fav.setText("⭐" if is_fav else "☆")
        except Exception:
            pass

    # ── A/B Comparison ────────────────────────────────────────────────────

    def _toggle_ab(self) -> None:
        """Switch between A and B comparison slots."""
        try:
            # Store current state into the active slot before switching
            active = self._svc.get_active_ab_slot_name(
                self._plugin_type, self._plugin_id, self._device_id,
            )
            current_b64 = ""
            current_params: Dict[str, float] = {}
            if self._get_state_fn is not None:
                try:
                    current_b64 = self._get_state_fn()
                except Exception:
                    pass
            if self._get_params_fn is not None:
                try:
                    current_params = self._get_params_fn()
                except Exception:
                    pass
            self._svc.store_ab_snapshot(
                self._plugin_type, self._plugin_id, self._device_id,
                active, current_b64, current_params,
            )

            # Switch to other slot
            new_slot = self._svc.switch_ab(
                self._plugin_type, self._plugin_id, self._device_id,
            )
            if new_slot is None:
                return

            new_name = self._svc.get_active_ab_slot_name(
                self._plugin_type, self._plugin_id, self._device_id,
            )

            # Restore new slot's state
            if new_slot.state_blob and self._set_state_fn is not None:
                try:
                    self._set_state_fn(new_slot.state_blob)
                except Exception:
                    pass
            elif new_slot.param_values and self._set_params_fn is not None:
                try:
                    self._set_params_fn(new_slot.param_values)
                except Exception:
                    pass

            # Update button
            self._btn_ab.setText(new_name)
            color_a = "#2d5a27"
            color_b = "#5a2d27"
            bg = color_a if new_name == "A" else color_b
            fg = "#7bd389" if new_name == "A" else "#d38989"
            self._btn_ab.setStyleSheet(
                f"QPushButton {{ font-weight: bold; font-size: 10px; "
                f"background-color: {bg}; color: {fg}; border-radius: 3px; }}"
            )
            self._show_status(f"A/B → Slot {new_name}")
            self.state_changed.emit()
        except Exception as e:
            self._show_status(f"A/B Fehler: {e}")

    # ── Save / Delete / Rename ────────────────────────────────────────────

    def _save_preset(self) -> None:
        """Save current plugin state as a user preset."""
        try:
            if self._get_state_fn is None:
                self._show_status("Kein get_state callback — Speichern nicht möglich")
                return
            state_b64 = self._get_state_fn()
            if not state_b64:
                self._show_status("Kein State zum Speichern")
                return

            import base64
            state_data = base64.b64decode(state_b64)

            name, ok = QInputDialog.getText(
                self, "Preset speichern",
                "Preset-Name:",
                text=f"Preset {len(self._all_presets) + 1}",
            )
            if not ok or not name.strip():
                return

            result = self._svc.save_preset(
                self._plugin_type, self._plugin_id,
                name.strip(), state_data,
            )
            if result is not None:
                self._show_status(f"✓ Gespeichert: {result.name}")
                self._refresh_presets()
                # Select the new preset
                for i, p in enumerate(self._filtered_presets):
                    if p.name == result.name:
                        self._block_combo_signal = True
                        self._cmb_preset.setCurrentIndex(i + 1)
                        self._block_combo_signal = False
                        break
            else:
                self._show_status("Speichern fehlgeschlagen")
        except Exception as e:
            self._show_status(f"Fehler: {e}")

    def _delete_preset(self) -> None:
        """Delete the currently selected user preset."""
        try:
            idx = self._cmb_preset.currentIndex() - 1
            if idx < 0 or idx >= len(self._filtered_presets):
                return
            preset = self._filtered_presets[idx]
            if preset.is_factory:
                self._show_status("Factory-Presets können nicht gelöscht werden")
                return
            reply = QMessageBox.question(
                self, "Preset löschen",
                f"Preset '{preset.name}' wirklich löschen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            if self._svc.delete_preset(preset):
                self._show_status(f"Gelöscht: {preset.name}")
                self._refresh_presets()
            else:
                self._show_status("Löschen fehlgeschlagen")
        except Exception as e:
            self._show_status(f"Fehler: {e}")

    def _rename_preset(self) -> None:
        """Rename the currently selected user preset."""
        try:
            idx = self._cmb_preset.currentIndex() - 1
            if idx < 0 or idx >= len(self._filtered_presets):
                return
            preset = self._filtered_presets[idx]
            if preset.is_factory:
                self._show_status("Factory-Presets können nicht umbenannt werden")
                return
            new_name, ok = QInputDialog.getText(
                self, "Preset umbenennen",
                "Neuer Name:",
                text=preset.name,
            )
            if not ok or not new_name.strip():
                return
            result = self._svc.rename_preset(preset, new_name.strip())
            if result is not None:
                self._show_status(f"Umbenannt: {result.name}")
                self._refresh_presets()
            else:
                self._show_status("Umbenennen fehlgeschlagen (Name existiert?)")
        except Exception as e:
            self._show_status(f"Fehler: {e}")

    # ── Actions menu ──────────────────────────────────────────────────────

    def _show_actions_menu(self) -> None:
        """Show context menu with additional preset actions."""
        try:
            menu = QMenu(self)
            menu.addAction("🗑 Preset löschen", self._delete_preset)
            menu.addAction("✏️ Preset umbenennen", self._rename_preset)
            menu.addSeparator()
            menu.addAction("🔄 Preset-Liste aktualisieren", self._refresh_presets)
            menu.addSeparator()

            # Show preset directory
            preset_dir = str(self._svc.preset_dir(self._plugin_type, self._plugin_id))
            menu.addAction(
                f"📂 Preset-Ordner öffnen",
                lambda d=preset_dir: self._open_directory(d),
            )

            menu.exec(self._btn_menu.mapToGlobal(self._btn_menu.rect().bottomLeft()))
        except Exception:
            pass

    @staticmethod
    def _open_directory(path: str) -> None:
        """Open a directory in the system file manager."""
        try:
            import subprocess
            if os.path.isdir(path):
                subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    # ── Undo / Redo ───────────────────────────────────────────────────────

    def _push_current_to_undo(self, description: str = "") -> None:
        """Capture current plugin state and push to undo stack."""
        try:
            state_b64 = ""
            params: Dict[str, float] = {}
            if self._get_state_fn is not None:
                try:
                    state_b64 = self._get_state_fn()
                except Exception:
                    pass
            if self._get_params_fn is not None:
                try:
                    params = self._get_params_fn()
                except Exception:
                    pass
            if state_b64 or params:
                self._state_mgr.push_undo(
                    self._track_id, self._device_id,
                    state_b64, params, description,
                )
        except Exception:
            pass

    def notify_param_changed(self, description: str = "Parameter geändert") -> None:
        """Call this from the host widget when a parameter value changes.

        Pushes state to undo if enough time has passed (auto-save interval).
        """
        try:
            if self._state_mgr.should_auto_save(self._track_id, self._device_id):
                self._push_current_to_undo(description)
                self._state_mgr.mark_auto_saved(self._track_id, self._device_id)
        except Exception:
            pass

    def _on_undo(self) -> None:
        """Undo the last parameter change."""
        try:
            snapshot = self._state_mgr.undo(self._track_id, self._device_id)
            if snapshot is None:
                self._show_status("Nichts zum Rückgängigmachen")
                return
            self._apply_snapshot(snapshot)
            self._show_status("↩ Undo")
            self._refresh_undo_buttons()
        except Exception as e:
            self._show_status(f"Undo Fehler: {e}")

    def _on_redo(self) -> None:
        """Redo the last undone change."""
        try:
            snapshot = self._state_mgr.redo(self._track_id, self._device_id)
            if snapshot is None:
                self._show_status("Nichts zum Wiederholen")
                return
            self._apply_snapshot(snapshot)
            self._show_status("↪ Redo")
            self._refresh_undo_buttons()
        except Exception as e:
            self._show_status(f"Redo Fehler: {e}")

    def _apply_snapshot(self, snapshot: Dict) -> None:
        """Restore a state snapshot to the plugin."""
        try:
            b64 = str(snapshot.get("state_b64") or "")
            params = snapshot.get("params", {})
            if b64 and self._set_state_fn is not None:
                self._set_state_fn(b64)
            elif params and self._set_params_fn is not None:
                self._set_params_fn(params)
            self.state_changed.emit()
        except Exception:
            pass

    def _refresh_undo_buttons(self) -> None:
        """Update enabled state of undo/redo buttons."""
        try:
            if _qt_is_deleted(self._btn_undo) or _qt_is_deleted(self._btn_redo):
                return
            self._btn_undo.setEnabled(
                self._state_mgr.can_undo(self._track_id, self._device_id)
            )
            self._btn_redo.setEnabled(
                self._state_mgr.can_redo(self._track_id, self._device_id)
            )
        except Exception:
            pass

    # ── Status display ────────────────────────────────────────────────────

    def _show_status(self, text: str, duration_ms: int = 3000) -> None:
        """Show a status message for a short time."""
        try:
            if _qt_is_deleted(self._lbl_status):
                return
            self._lbl_status.setText(text)
            self._lbl_status.setVisible(True)
            QTimer.singleShot(duration_ms, self._hide_status)
        except Exception:
            pass

    def _hide_status(self) -> None:
        try:
            if not _qt_is_deleted(self._lbl_status):
                self._lbl_status.setVisible(False)
        except Exception:
            pass
