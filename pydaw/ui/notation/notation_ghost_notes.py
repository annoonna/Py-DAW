"""Ghost Notes extension for NotationView.

This module provides ghost notes rendering capabilities for the Notation Editor.
It extends the existing NotationView with methods to render MIDI notes
from multiple clips/tracks simultaneously in staff notation.

Usage:
    Add this import to notation_view.py:
        from pydaw.ui.notation.notation_ghost_notes import NotationGhostRenderer
    
    In NotationView.__init__, add:
        self.ghost_renderer = NotationGhostRenderer(self)
        self.layer_manager = LayerManager()
    
    In _render_notes or scene update, call:
        self.ghost_renderer.render_ghost_layers(self.scene, self.layer_manager, ...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

if TYPE_CHECKING:
    from pydaw.ui.notation.notation_view import NotationView
    from pydaw.model.ghost_notes import LayerManager, GhostLayer


logger = logging.getLogger(__name__)


class _GhostNoteItem(QGraphicsItem):
    """A single ghost note rendered in notation view.
    
    Similar to _NoteItem but with opacity and lock indicators.
    """
    
    def __init__(
        self,
        note,  # MidiNote
        *,
        x_center: float,
        staff_line: int,
        y_offset: int,
        style,  # StaffStyle
        layer_color: QColor,
        opacity: float,
        is_locked: bool,
    ):
        super().__init__()
        self.note = note
        self._x = float(x_center)
        self._line = int(staff_line)
        self._y_offset = int(y_offset)
        self._style = style
        self._layer_color = layer_color
        self._opacity = opacity
        self._locked = is_locked
        
        # Ghost notes don't respond to mouse
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        
        # Set lower z-value so main notes appear on top
        self.setZValue(-10.0)
    
    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt API)
        """Return bounding rectangle."""
        w = self._style.note_head_w * 4
        h = self._style.stem_len + self._style.note_head_h * 4
        return QRectF(self._x - w, self._y_offset - h, w * 2, h * 2)
    
    def paint(self, painter: QPainter, _opt, _widget=None):  # noqa: N802 (Qt API)
        """Render the ghost note."""
        # IMPORTANT: Exceptions inside QGraphicsItem.paint can abort the whole
        # process in PyQt6 (Qt treats it as fatal). Therefore we must never let
        # an exception escape this method.
        saved = False
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Determine accidental
            try:
                _ = self.note.to_staff_position()
            except Exception:
                pass
            acc = int(getattr(self.note, "accidental", 0))

            # Geometry (same coordinate system as StaffRenderer: bottom line = 0)
            from pydaw.ui.notation.staff_renderer import StaffRenderer

            style = self._style
            bottom_line_y = StaffRenderer.line_y(self._y_offset, style.lines - 1, style)
            half_step = float(style.line_distance) / 2.0
            y = float(bottom_line_y) - (float(self._line) * half_step)

            # Apply opacity and tint
            painter.save()
            saved = True
            painter.setOpacity(float(self._opacity))

            note_color = QColor(self._layer_color)
            note_color.setAlpha(int(255 * float(self._opacity)))

            outline_color = QColor(self._layer_color).darker(120)
            outline_color.setAlpha(int(200 * float(self._opacity)))

            # Accidental (unicode glyph; minimal dependency)
            if acc != 0:
                glyph = "♯" if acc > 0 else "♭"
                if acc == 2:
                    glyph = "♮"
                from PySide6.QtGui import QFont
                from PySide6.QtCore import QPointF

                font = QFont()
                try:
                    font.setPointSize(int(getattr(style, "accidental_font_pt", 14)))
                except Exception:
                    font.setPointSize(14)
                painter.setFont(font)
                painter.setPen(QPen(outline_color, 1))
                painter.drawText(
                    QPointF(self._x - float(style.note_head_w) * 1.6, y + float(style.note_head_h) / 2.0),
                    glyph,
                )

            # Note head
            painter.setPen(QPen(outline_color, 1))
            painter.setBrush(QBrush(note_color))
            head_rect = QRectF(
                float(self._x - float(style.note_head_w) / 2.0),
                float(y - float(style.note_head_h) / 2.0),
                float(style.note_head_w),
                float(style.note_head_h),
            )
            painter.drawEllipse(head_rect)

            # Stem
            stem_up = self._line < 4
            painter.setPen(QPen(outline_color, 1.5))
            if stem_up:
                x0 = self._x + float(style.note_head_w) / 2.0
                painter.drawLine(int(x0), int(y), int(x0), int(y - float(style.stem_len)))
            else:
                x0 = self._x - float(style.note_head_w) / 2.0
                painter.drawLine(int(x0), int(y), int(x0), int(y + float(style.stem_len)))

            # Lock indicator
            if self._locked:
                self._draw_lock_indicator(painter, head_rect)

            painter.restore()
            saved = False

        except Exception:
            # Never crash the app due to a render exception.
            logger.exception("Ghost note paint failed")
            try:
                if saved:
                    painter.restore()
            except Exception:
                pass
            try:
                painter.setOpacity(1.0)
            except Exception:
                pass
    
    def _draw_lock_indicator(self, painter: QPainter, head_rect: QRectF) -> None:
        """Draw small lock icon next to note head.
        
        Args:
            painter: QPainter to use
            head_rect: Note head rectangle
        """
        lock_size = 6
        lock_x = head_rect.right() + 4
        lock_y = head_rect.center().y() - lock_size / 2
        
        lock_color = QColor(255, 255, 255)
        lock_color.setAlpha(int(150 * self._opacity))
        
        painter.setPen(QPen(lock_color, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Lock body
        lock_rect = QRectF(lock_x, lock_y + lock_size * 0.3, lock_size * 0.6, lock_size * 0.7)
        painter.drawRect(lock_rect)
        
        # Lock shackle
        arc_rect = QRectF(lock_x - lock_size * 0.1, lock_y, lock_size * 0.8, lock_size * 0.6)
        painter.drawArc(arc_rect, 0, 180 * 16)


class NotationGhostRenderer:
    """Renders ghost notes from multiple MIDI clips in Notation View.
    
    Features:
    - Multi-layer visualization in staff notation
    - Opacity-based rendering
    - Color-coded layers
    - Lock indicators
    - Respects layer visibility
    """
    
    def __init__(self, notation_view: NotationView):
        """Initialize ghost notes renderer.
        
        Args:
            notation_view: Parent notation view
        """
        self.notation_view = notation_view
        self._ghost_items: dict[str, list[_GhostNoteItem]] = {}
    
    def render_ghost_layers(
        self,
        scene: QGraphicsScene,
        layer_manager: LayerManager,
        layout,  # NotationLayout
        style,  # StaffStyle
    ) -> None:
        """Render all visible ghost note layers to the scene.
        
        Args:
            scene: Graphics scene to render to
            layer_manager: Layer manager with ghost layers
            layout: Notation layout configuration
            style: Staff style configuration
        """
        # Clear previous ghost items
        self.clear_ghost_items(scene)
        
        # Get all visible layers (sorted by z_order, back to front)
        layers = layer_manager.get_visible_layers()
        
        # Render each layer
        for layer in layers:
            # Skip the focused layer - it will be rendered normally
            if layer.is_focused:
                continue
            
            self._render_layer_notes(scene, layer, layout, style)
    
    def _render_layer_notes(
        self,
        scene: QGraphicsScene,
        layer: GhostLayer,
        layout,  # NotationLayout
        style,  # StaffStyle
    ) -> None:
        """Render notes from a single ghost layer.
        
        Args:
            scene: Graphics scene
            layer: Ghost layer to render
            layout: Notation layout
            style: Staff style
        """
        try:
            # Get notes from this layer's clip
            notes = self.notation_view._project_service.get_midi_notes(layer.clip_id)
            if not notes:
                return
            
            ghost_items = []
            
            # Render each note
            for note in notes:
                try:
                    # Convert to staff position
                    staff_line, accidental = note.to_staff_position()
                    
                    # Calculate x position
                    x_center = (
                        layout.left_margin
                        + float(note.start_beats) * layout.pixels_per_beat
                    )
                    
                    # Create ghost note item
                    ghost_item = _GhostNoteItem(
                        note,
                        x_center=x_center,
                        staff_line=staff_line,
                        y_offset=layout.y_offset,
                        style=style,
                        layer_color=layer.color,
                        opacity=layer.opacity,
                        is_locked=(layer.state.value == "locked"),
                    )
                    
                    scene.addItem(ghost_item)
                    ghost_items.append(ghost_item)
                
                except Exception:
                    continue
            
            # Store items for this layer
            self._ghost_items[layer.clip_id] = ghost_items
        
        except Exception:
            # Silently handle missing clips or errors
            pass
    
    def clear_ghost_items(self, scene: QGraphicsScene) -> None:
        """Remove all ghost note items from the scene.
        
        Args:
            scene: Graphics scene to clear
        """
        for clip_id, items in self._ghost_items.items():
            for item in items:
                try:
                    scene.removeItem(item)
                except Exception:
                    pass
        
        self._ghost_items.clear()
    
    def update_ghost_layer(
        self,
        scene: QGraphicsScene,
        clip_id: str,
        layer_manager: LayerManager,
        layout,  # NotationLayout
        style,  # StaffStyle
    ) -> None:
        """Update a specific ghost layer (after opacity/color change).
        
        Args:
            scene: Graphics scene
            clip_id: Clip ID to update
            layer_manager: Layer manager
            layout: Notation layout
            style: Staff style
        """
        # Remove old items for this layer
        if clip_id in self._ghost_items:
            for item in self._ghost_items[clip_id]:
                try:
                    scene.removeItem(item)
                except Exception:
                    pass
            del self._ghost_items[clip_id]
        
        # Get layer
        layer = layer_manager.get_layer(clip_id)
        if layer and layer.is_visible() and not layer.is_focused:
            self._render_layer_notes(scene, layer, layout, style)


# Helper functions to integrate into existing NotationView

def integrate_ghost_notes_notation(notation_view_instance):
    """Helper to integrate ghost notes into existing NotationView.
    
    Call this in NotationView.__init__:
        integrate_ghost_notes_notation(self)
    
    Args:
        notation_view_instance: NotationView instance
    """
    from pydaw.model.ghost_notes import LayerManager
    
    # Add layer manager and renderer
    notation_view_instance.layer_manager = LayerManager()
    notation_view_instance.ghost_renderer = NotationGhostRenderer(notation_view_instance)
    
    # Connect to layer changes
    notation_view_instance.layer_manager.layers_changed.connect(
        lambda: _refresh_ghost_notes(notation_view_instance)
    )


def _refresh_ghost_notes(notation_view):
    """Refresh ghost notes rendering.
    
    Args:
        notation_view: NotationView instance
    """
    if not hasattr(notation_view, 'ghost_renderer'):
        return
    
    if not hasattr(notation_view, '_layout') or not hasattr(notation_view, '_style'):
        return
    
    try:
        notation_view.ghost_renderer.render_ghost_layers(
            notation_view.scene(),
            notation_view.layer_manager,
            notation_view._layout,
            notation_view._style,
        )
    except Exception:
        pass


# Example test
if __name__ == "__main__":
    print("Notation Ghost Notes Renderer - Test Mode")
    print("This module extends NotationView with ghost notes rendering.")
    print("\nIntegration steps:")
    print("1. Import: from pydaw.ui.notation.notation_ghost_notes import NotationGhostRenderer")
    print("2. In __init__: self.ghost_renderer = NotationGhostRenderer(self)")
    print("3. In scene update: self.ghost_renderer.render_ghost_layers(...)")
    print("\nGhost notes will be rendered in staff notation with layer colors and opacity.")
