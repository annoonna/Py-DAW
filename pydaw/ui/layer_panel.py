"""Layer Panel UI for Ghost Notes / Layered Editing.

This module provides a UI panel for managing ghost layers in Piano Roll
and Notation editors.

Features:
- Layer list with visibility controls
- Lock/Unlock toggle per layer
- Focus selection (pencil icon)
- Opacity slider per layer
- Color picker per layer
- Add/Remove layer buttons
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,  # For ScrollMode
)

from pydaw.model.ghost_notes import GhostLayer, LayerManager, LayerState


class LayerItemWidget(QWidget):
    """Widget for a single layer in the layer list.
    
    Displays:
    - Layer name
    - Visibility checkbox (eye icon)
    - Lock button (lock icon)
    - Focus button (pencil icon)
    - Color indicator
    - Opacity slider
    
    Signals:
        focus_requested: User clicked focus button
        lock_toggled: User toggled lock state
        visibility_toggled: User toggled visibility
        opacity_changed: User changed opacity
        color_changed: User changed layer color
    """
    
    focus_requested = Signal(str)  # clip_id
    lock_toggled = Signal(str, bool)  # clip_id, locked
    visibility_toggled = Signal(str, bool)  # clip_id, visible
    opacity_changed = Signal(str, float)  # clip_id, opacity
    color_changed = Signal(str, QColor)  # clip_id, color
    
    def __init__(self, layer: GhostLayer, parent=None):
        super().__init__(parent)
        self.layer = layer
        self._setup_ui()
        self._connect_signals()
        self._update_state()
    
    def _setup_ui(self) -> None:
        """Setup widget layout and controls."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        
        # Focus button (pencil icon)
        self.focus_btn = QToolButton()
        self.focus_btn.setText("✎")
        self.focus_btn.setToolTip("Set as active editing layer")
        self.focus_btn.setCheckable(True)
        self.focus_btn.setFixedSize(24, 24)
        layout.addWidget(self.focus_btn)
        
        # Visibility checkbox (eye icon)
        self.visible_check = QCheckBox()
        self.visible_check.setText("👁")
        self.visible_check.setToolTip("Show/Hide layer")
        self.visible_check.setChecked(self.layer.is_visible())
        layout.addWidget(self.visible_check)
        
        # Lock button
        self.lock_btn = QToolButton()
        self.lock_btn.setText("🔓")
        self.lock_btn.setToolTip("Lock/Unlock layer")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setFixedSize(24, 24)
        layout.addWidget(self.lock_btn)
        
        # Color indicator button
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(24, 24)
        self.color_btn.setToolTip("Change layer color")
        self._update_color_button()
        layout.addWidget(self.color_btn)
        
        # Layer name
        self.name_label = QLabel(self.layer.track_name)
        self.name_label.setMinimumWidth(80)
        layout.addWidget(self.name_label)
        
        # Opacity slider
        opacity_label = QLabel("Opacity:")
        layout.addWidget(opacity_label)
        
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.layer.opacity * 100))
        self.opacity_slider.setToolTip(f"Opacity: {self.layer.opacity:.0%}")
        self.opacity_slider.setFixedWidth(80)
        layout.addWidget(self.opacity_slider)
        
        self.opacity_value_label = QLabel(f"{self.layer.opacity:.0%}")
        self.opacity_value_label.setFixedWidth(35)
        layout.addWidget(self.opacity_value_label)
        
        layout.addStretch()
    
    def _connect_signals(self) -> None:
        """Connect widget signals to handlers."""
        self.focus_btn.clicked.connect(self._on_focus_clicked)
        self.lock_btn.clicked.connect(self._on_lock_toggled)
        self.visible_check.toggled.connect(self._on_visibility_toggled)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.color_btn.clicked.connect(self._on_color_clicked)
    
    def _update_state(self) -> None:
        """Update widget state from layer data."""
        self.focus_btn.setChecked(self.layer.is_focused)
        self.lock_btn.setChecked(self.layer.state == LayerState.LOCKED)
        self.lock_btn.setText("🔒" if self.layer.state == LayerState.LOCKED else "🔓")
        self.visible_check.setChecked(self.layer.is_visible())
        
        # Update opacity slider
        self.opacity_slider.setValue(int(self.layer.opacity * 100))
        self.opacity_value_label.setText(f"{self.layer.opacity:.0%}")
        
        # Highlight focused layer
        if self.layer.is_focused:
            self.setStyleSheet("background-color: #E8F4F8;")
        else:
            self.setStyleSheet("")
    
    def _update_color_button(self) -> None:
        """Update color button appearance."""
        color = self.layer.color
        self.color_btn.setStyleSheet(
            f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); "
            "border: 1px solid #888;"
        )
    
    def _on_focus_clicked(self) -> None:
        """Handle focus button click."""
        self.focus_requested.emit(self.layer.clip_id)
    
    def _on_lock_toggled(self) -> None:
        """Handle lock button toggle."""
        locked = self.lock_btn.isChecked()
        self.lock_toggled.emit(self.layer.clip_id, locked)
    
    def _on_visibility_toggled(self, visible: bool) -> None:
        """Handle visibility checkbox toggle."""
        self.visibility_toggled.emit(self.layer.clip_id, visible)
    
    def _on_opacity_changed(self, value: int) -> None:
        """Handle opacity slider change."""
        opacity = value / 100.0
        self.opacity_value_label.setText(f"{opacity:.0%}")
        self.opacity_changed.emit(self.layer.clip_id, opacity)
    
    def _on_color_clicked(self) -> None:
        """Handle color button click - open color picker."""
        color = QColorDialog.getColor(
            self.layer.color,
            self,
            "Select Layer Color"
        )
        if color.isValid():
            self.color_changed.emit(self.layer.clip_id, color)
            self.layer.color = color
            self._update_color_button()
    
    def update_layer(self, layer: GhostLayer) -> None:
        """Update widget with new layer data.
        
        Args:
            layer: Updated layer data
        """
        self.layer = layer
        self._update_state()
        self._update_color_button()


class LayerPanel(QWidget):
    """Layer management panel for ghost notes.
    
    Provides UI for managing multiple MIDI clip layers in editors.
    
    Signals:
        layer_added: User requested to add a new layer
    """
    
    layer_added = Signal()
    
    def __init__(self, layer_manager: LayerManager, parent=None):
        super().__init__(parent)
        self.layer_manager = layer_manager
        self._layer_widgets: dict[str, LayerItemWidget] = {}
        
        self._setup_ui()
        self._connect_signals()
        self._refresh_layers()
    
    def _setup_ui(self) -> None:
        """Setup panel layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("<b>Ghost Layers</b>")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # FIXED v0.0.19.7.7: Buttons nebeneinander und KLEINER!
        # + Add Layer button
        self.add_btn = QPushButton("+ Add")
        self.add_btn.setToolTip("Add a MIDI clip as ghost layer")
        self.add_btn.setFixedWidth(70)  # KLEINER! ✅
        header_layout.addWidget(self.add_btn)
        
        # − Remove button (now in header, side-by-side!)
        self.remove_btn = QPushButton("− Remove")
        self.remove_btn.setToolTip("Remove selected ghost layer")
        self.remove_btn.setFixedWidth(80)  # KLEINER! ✅
        self.remove_btn.setEnabled(False)
        header_layout.addWidget(self.remove_btn)
        
        layout.addLayout(header_layout)
        
        # Layer list with scrollbar (CORRECTED - smaller min height)
        self.layer_list = QListWidget()
        self.layer_list.setAlternatingRowColors(True)
        self.layer_list.setMinimumHeight(150)  # SMALLER! (was 200)
        self.layer_list.setMaximumHeight(300)  # SMALLER! (was 400)
        # Force scrollbar to be visible when needed
        self.layer_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)  # ALWAYS ON!
        self.layer_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Enable smooth scrolling
        self.layer_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.layer_list)
        
        # Info label
        info_label = QLabel(
            "<i>Ghost layers show MIDI notes from other clips/tracks.<br>"
            "Only the focused layer (✎) accepts new notes.</i>"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(info_label)
    
    def _connect_signals(self) -> None:
        """Connect signals."""
        self.add_btn.clicked.connect(self._on_add_layer)
        self.remove_btn.clicked.connect(self._on_remove_layer)
        self.layer_list.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Connect to layer manager
        self.layer_manager.layers_changed.connect(self._refresh_layers)
    
    def _refresh_layers(self) -> None:
        """Refresh layer list from manager."""
        # Clear current list
        self.layer_list.clear()
        self._layer_widgets.clear()
        
        # Add all visible layers
        for layer in self.layer_manager.get_visible_layers():
            self._add_layer_item(layer)
    
    def _add_layer_item(self, layer: GhostLayer) -> None:
        """Add a layer to the list.
        
        Args:
            layer: Ghost layer to add
        """
        # Create list item
        item = QListWidgetItem(self.layer_list)
        item.setData(Qt.ItemDataRole.UserRole, layer.clip_id)
        
        # Create layer widget
        widget = LayerItemWidget(layer)
        widget.focus_requested.connect(self._on_layer_focus)
        widget.lock_toggled.connect(self._on_layer_lock)
        widget.visibility_toggled.connect(self._on_layer_visibility)
        widget.opacity_changed.connect(self._on_layer_opacity)
        
        # Set widget as item widget
        item.setSizeHint(widget.sizeHint())
        self.layer_list.setItemWidget(item, widget)
        
        self._layer_widgets[layer.clip_id] = widget
    
    def _on_add_layer(self) -> None:
        """Handle add layer button click."""
        # Emit signal - parent should show clip selector dialog
        self.layer_added.emit()
    
    def _on_remove_layer(self) -> None:
        """Handle remove layer button click."""
        current_item = self.layer_list.currentItem()
        if not current_item:
            return
        
        clip_id = current_item.data(Qt.ItemDataRole.UserRole)
        self.layer_manager.remove_layer(clip_id)
    
    def _on_selection_changed(self) -> None:
        """Handle layer list selection change."""
        has_selection = self.layer_list.currentItem() is not None
        self.remove_btn.setEnabled(has_selection)
    
    def _on_layer_focus(self, clip_id: str) -> None:
        """Handle layer focus request.
        
        Args:
            clip_id: Clip to focus
        """
        self.layer_manager.set_focused_layer(clip_id)
    
    def _on_layer_lock(self, clip_id: str, locked: bool) -> None:
        """Handle layer lock toggle.
        
        Args:
            clip_id: Clip to lock/unlock
            locked: Lock state
        """
        state = LayerState.LOCKED if locked else LayerState.ACTIVE
        self.layer_manager.set_layer_state(clip_id, state)
    
    def _on_layer_visibility(self, clip_id: str, visible: bool) -> None:
        """Handle layer visibility toggle.
        
        Args:
            clip_id: Clip to show/hide
            visible: Visibility state
        """
        state = LayerState.ACTIVE if visible else LayerState.HIDDEN
        self.layer_manager.set_layer_state(clip_id, state)
    
    def _on_layer_opacity(self, clip_id: str, opacity: float) -> None:
        """Handle layer opacity change.
        
        Args:
            clip_id: Clip to modify
            opacity: New opacity value
        """
        self.layer_manager.set_layer_opacity(clip_id, opacity)


# Test / Demo
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow
    
    app = QApplication(sys.argv)
    
    # Create layer manager with test data
    manager = LayerManager()
    manager.add_layer("clip1", "Piano", is_focused=True)
    manager.add_layer("clip2", "Strings", opacity=0.3)
    manager.add_layer("clip3", "Bass", opacity=0.2)
    
    # Create panel
    panel = LayerPanel(manager)
    
    # Show in window
    window = QMainWindow()
    window.setCentralWidget(panel)
    window.setWindowTitle("Ghost Layers Panel - Test")
    window.resize(500, 400)
    window.show()
    
    sys.exit(app.exec())
