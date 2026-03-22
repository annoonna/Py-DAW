"""Ghost Notes / Layered Editing Data Model.

This module provides the data structures for managing multiple MIDI layers
in Piano Roll and Notation editors, similar to Pro-DAW's layered editing.

Key Features:
- Multi-clip visualization
- Lock/Unlock layers
- Focus management (only focused layer accepts new notes)
- Ghost note rendering (30% opacity for inactive layers)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor


class LayerState(Enum):
    """State of a ghost layer."""
    
    ACTIVE = "active"      # Visible, focused (accepts edits)
    LOCKED = "locked"      # Visible, not editable
    HIDDEN = "hidden"      # Not visible


@dataclass
class GhostLayer:
    """Represents a single MIDI clip layer in ghost notes view.
    
    Attributes:
        clip_id: Unique clip identifier
        track_name: Display name of the track
        state: Current layer state (active/locked/hidden)
        opacity: Rendering opacity (0.0-1.0), default 0.3 for ghost notes
        color: Layer color for visual distinction
        is_focused: True if this is the active editing layer
        z_order: Rendering order (higher = on top)
    """
    
    clip_id: str
    track_name: str
    state: LayerState = LayerState.LOCKED
    opacity: float = 0.3
    color: QColor = field(default_factory=lambda: QColor(128, 128, 128))
    is_focused: bool = False
    z_order: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize layer to JSON-safe dict."""
        try:
            r, g, b, a = self.color.getRgb()
            color = [int(r), int(g), int(b), int(a)]
        except Exception:
            color = [128, 128, 128, 255]
        return {
            'clip_id': str(self.clip_id),
            'track_name': str(self.track_name),
            'state': str(getattr(self.state, 'value', self.state)),
            'opacity': float(self.opacity),
            'color': color,
            'is_focused': bool(self.is_focused),
            'z_order': int(self.z_order),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'GhostLayer':
        """Deserialize layer from JSON-safe dict."""
        # state
        raw_state = d.get('state', LayerState.LOCKED.value)
        try:
            state = LayerState(str(raw_state))
        except Exception:
            state = LayerState.LOCKED
        # color
        raw_color = d.get('color', [128, 128, 128, 255])
        try:
            if isinstance(raw_color, (list, tuple)) and len(raw_color) >= 3:
                r = int(raw_color[0]); g = int(raw_color[1]); b = int(raw_color[2])
                a = int(raw_color[3]) if len(raw_color) >= 4 else 255
                color = QColor(r, g, b, a)
            else:
                color = QColor(128, 128, 128)
        except Exception:
            color = QColor(128, 128, 128)
        return cls(
            clip_id=str(d.get('clip_id', '')),
            track_name=str(d.get('track_name', 'Layer')),
            state=state,
            opacity=float(d.get('opacity', 0.3) or 0.3),
            color=color,
            is_focused=bool(d.get('is_focused', False)),
            z_order=int(d.get('z_order', 0) or 0),
        )

    def is_editable(self) -> bool:
        """Check if layer can be edited."""
        return self.state == LayerState.ACTIVE and self.is_focused
    
    def is_visible(self) -> bool:
        """Check if layer should be rendered."""
        return self.state != LayerState.HIDDEN


class LayerManager(QObject):
    """Manages ghost layers for Piano Roll and Notation editors.
    
    Signals:
        layers_changed: Emitted when layer configuration changes
        focused_layer_changed: Emitted when active editing layer changes
    
    Example:
        >>> manager = LayerManager()
        >>> manager.add_layer("clip1", "Piano", is_focused=True)
        >>> manager.add_layer("clip2", "Strings", opacity=0.3)
        >>> manager.set_focused_layer("clip1")
        >>> for layer in manager.get_visible_layers():
        ...     print(f"{layer.track_name}: opacity={layer.opacity}")
    """
    
    # Signals
    layers_changed = pyqtSignal()
    focused_layer_changed = pyqtSignal(str)  # clip_id
    
    def __init__(self):
        super().__init__()
        self._layers: dict[str, GhostLayer] = {}
        self._focused_clip_id: Optional[str] = None


    def to_dict(self) -> dict[str, Any]:
        """Serialize full layer manager state (JSON-safe)."""
        return {
            "focused_clip_id": str(self._focused_clip_id) if self._focused_clip_id else "",
            "layers": [l.to_dict() for l in self._layers.values()],
        }

    def load_state(self, data: dict[str, Any] | None, *, emit: bool = True) -> None:
        """Load layer manager state from dict.

        Args:
            data: dict from `to_dict()` (or compatible)
            emit: whether to emit signals after loading
        """
        if not isinstance(data, dict):
            data = {}

        self._layers.clear()
        self._focused_clip_id = None

        raw_layers = data.get("layers", [])
        layers: list[GhostLayer] = []
        if isinstance(raw_layers, list):
            for item in raw_layers:
                if isinstance(item, dict):
                    try:
                        layers.append(GhostLayer.from_dict(item))
                    except Exception:
                        pass

        # Stable order: by z_order
        layers.sort(key=lambda x: int(getattr(x, "z_order", 0) or 0))

        for idx, layer in enumerate(layers):
            cid = str(getattr(layer, "clip_id", "") or "")
            if not cid or cid in self._layers:
                continue
            # normalize z_order in case it's missing/invalid
            try:
                layer.z_order = int(getattr(layer, "z_order", idx) or idx)
            except Exception:
                layer.z_order = idx
            self._layers[cid] = layer

        focused = data.get("focused_clip_id", "")
        if isinstance(focused, str) and focused and focused in self._layers:
            self._focused_clip_id = focused
            for l in self._layers.values():
                l.is_focused = False
            self._layers[focused].is_focused = True

        if emit:
            try:
                if self._focused_clip_id:
                    self.focused_layer_changed.emit(self._focused_clip_id)
            except Exception:
                pass
            self.layers_changed.emit()

    def add_layer(
        self,
        clip_id: str,
        track_name: str,
        *,
        state: LayerState = LayerState.LOCKED,
        opacity: float = 0.3,
        color: Optional[QColor] = None,
        is_focused: bool = False,
    ) -> GhostLayer:
        """Add a new ghost layer.
        
        Args:
            clip_id: Unique clip identifier
            track_name: Display name
            state: Initial state
            opacity: Rendering opacity (0.0-1.0)
            color: Optional layer color
            is_focused: Set as focused layer
        
        Returns:
            Created GhostLayer instance
        """
        if color is None:
            color = self._generate_layer_color(len(self._layers))
        
        layer = GhostLayer(
            clip_id=clip_id,
            track_name=track_name,
            state=state,
            opacity=opacity,
            color=color,
            is_focused=is_focused,
            z_order=len(self._layers),
        )
        
        self._layers[clip_id] = layer
        
        if is_focused:
            self.set_focused_layer(clip_id)
        
        self.layers_changed.emit()
        return layer
    
    def remove_layer(self, clip_id: str) -> bool:
        """Remove a ghost layer.
        
        Args:
            clip_id: Clip to remove
        
        Returns:
            True if layer was removed, False if not found
        """
        if clip_id not in self._layers:
            return False
        
        was_focused = self._layers[clip_id].is_focused
        del self._layers[clip_id]
        
        # If we removed the focused layer, focus the first available
        if was_focused and self._layers:
            first_clip = next(iter(self._layers))
            self.set_focused_layer(first_clip)
        
        self.layers_changed.emit()
        return True
    
    def set_focused_layer(self, clip_id: str) -> bool:
        """Set which layer accepts editing operations.
        
        Args:
            clip_id: Clip to focus
        
        Returns:
            True if focus changed, False if clip not found
        """
        if clip_id not in self._layers:
            return False
        
        # Unfocus all layers
        for layer in self._layers.values():
            layer.is_focused = False
        
        # Focus selected layer and make it active
        focused_layer = self._layers[clip_id]
        focused_layer.is_focused = True
        focused_layer.state = LayerState.ACTIVE
        focused_layer.opacity = 1.0  # Full opacity for focused layer
        
        self._focused_clip_id = clip_id
        self.focused_layer_changed.emit(clip_id)
        self.layers_changed.emit()
        return True
    
    def set_layer_state(self, clip_id: str, state: LayerState) -> bool:
        """Change layer state (active/locked/hidden).
        
        Args:
            clip_id: Clip to modify
            state: New state
        
        Returns:
            True if state changed, False if clip not found
        """
        if clip_id not in self._layers:
            return False
        
        layer = self._layers[clip_id]
        layer.state = state
        
        # Adjust opacity based on state
        if state == LayerState.ACTIVE:
            layer.opacity = 1.0 if layer.is_focused else 0.5
        elif state == LayerState.LOCKED:
            layer.opacity = 0.3
        
        self.layers_changed.emit()
        return True
    
    def set_layer_opacity(self, clip_id: str, opacity: float) -> bool:
        """Set layer rendering opacity.
        
        Args:
            clip_id: Clip to modify
            opacity: Opacity value (0.0-1.0)
        
        Returns:
            True if opacity changed, False if clip not found
        """
        if clip_id not in self._layers:
            return False
        
        opacity = max(0.0, min(1.0, opacity))  # Clamp to valid range
        self._layers[clip_id].opacity = opacity
        self.layers_changed.emit()
        return True
    
    def get_layer(self, clip_id: str) -> Optional[GhostLayer]:
        """Get layer by clip ID.
        
        Args:
            clip_id: Clip identifier
        
        Returns:
            GhostLayer if found, None otherwise
        """
        return self._layers.get(clip_id)
    
    def get_visible_layers(self) -> list[GhostLayer]:
        """Get all visible layers, sorted by z_order.
        
        Returns:
            List of visible layers
        """
        layers = [
            layer for layer in self._layers.values()
            if layer.is_visible()
        ]
        return sorted(layers, key=lambda l: l.z_order)
    
    def get_focused_layer(self) -> Optional[GhostLayer]:
        """Get the currently focused editing layer.
        
        Returns:
            Focused GhostLayer or None
        """
        if self._focused_clip_id:
            return self._layers.get(self._focused_clip_id)
        return None
    
    def clear_layers(self) -> None:
        """Remove all layers."""
        self._layers.clear()
        self._focused_clip_id = None
        self.layers_changed.emit()
    
    def has_layers(self) -> bool:
        """Check if any layers exist.
        
        Returns:
            True if at least one layer exists
        """
        return len(self._layers) > 0
    
    @staticmethod
    def _generate_layer_color(index: int) -> QColor:
        """Generate a distinct color for a layer based on index.
        
        Args:
            index: Layer index
        
        Returns:
            Generated QColor
        """
        # Predefined color palette for layers
        colors = [
            QColor(70, 130, 180),   # Steel Blue
            QColor(144, 238, 144),  # Light Green
            QColor(255, 182, 193),  # Light Pink
            QColor(255, 215, 0),    # Gold
            QColor(138, 43, 226),   # Blue Violet
            QColor(255, 127, 80),   # Coral
            QColor(100, 149, 237),  # Cornflower Blue
            QColor(255, 160, 122),  # Light Salmon
        ]
        return colors[index % len(colors)]


# Example usage for testing
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # Create manager
    manager = LayerManager()
    
    # Add layers
    layer1 = manager.add_layer("clip1", "Piano", is_focused=True)
    layer2 = manager.add_layer("clip2", "Strings", opacity=0.3)
    layer3 = manager.add_layer("clip3", "Bass", opacity=0.2)
    
    print("Visible layers:")
    for layer in manager.get_visible_layers():
        print(f"  {layer.track_name}: "
              f"focused={layer.is_focused}, "
              f"editable={layer.is_editable()}, "
              f"opacity={layer.opacity:.1f}")
    
    # Change focus
    print("\nChanging focus to clip2...")
    manager.set_focused_layer("clip2")
    
    focused = manager.get_focused_layer()
    if focused:
        print(f"Focused layer: {focused.track_name}")
    
    # Lock a layer
    print("\nLocking clip3...")
    manager.set_layer_state("clip3", LayerState.LOCKED)
    
    layer = manager.get_layer("clip3")
    if layer:
        print(f"clip3 editable: {layer.is_editable()}")
    
    print("\nTest completed!")
