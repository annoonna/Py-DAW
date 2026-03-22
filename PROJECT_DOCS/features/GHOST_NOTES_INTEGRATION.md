# Ghost Notes / Layered Editing - Integration Guide

**Version:** v0.0.19.3.7.15  
**Feature:** Multi-layer MIDI visualization (Ghost Notes)  
**Status:** Ready for Integration  
**Author:** Claude-Sonnet-4.5  
**Date:** 2026-02-01

---

## 📋 Feature-Übersicht

Das Ghost Notes / Layered Editing Feature ermöglicht es, MIDI-Noten aus mehreren Clips/Tracks gleichzeitig im Piano Roll und Notation Editor zu visualisieren.

### Kernfunktionen

✅ **Multi-Track-Visualisierung**: Zeige Noten von mehreren Clips gleichzeitig  
✅ **Ghost Notes**: Inaktive Noten mit 30% Deckkraft  
✅ **Clip-Sperre**: Schloss-Symbol - gesperrte Noten nicht editierbar  
✅ **Fokus-Management**: Nur fokussierter Layer nimmt neue Noten auf  
✅ **Farb-Kodierung**: Jeder Layer hat eigene Farbe  
✅ **Opacity-Control**: Individueller Opacity-Slider pro Layer

### Referenz

Ähnlich zu **Pro-DAW - Layered Editing**

---

## 📦 Neue Dateien

```
pydaw/
├── model/
│   └── ghost_notes.py                    # Datenmodell (LayerManager, GhostLayer)
├── ui/
│   ├── layer_panel.py                    # Layer Management Panel UI
│   ├── pianoroll_ghost_notes.py         # Piano Roll Ghost Rendering
│   └── notation/
│       └── notation_ghost_notes.py      # Notation Ghost Rendering
```

---

## 🔧 Integration Steps

### 1. Piano Roll Integration

**Datei:** `pydaw/ui/pianoroll_canvas.py`

#### Schritt 1.1: Imports hinzufügen

```python
from pydaw.model.ghost_notes import LayerManager
from pydaw.ui.pianoroll_ghost_notes import GhostNotesRenderer
```

#### Schritt 1.2: In `__init__` erweitern

```python
def __init__(self, project: ProjectService, transport=None, parent=None):
    super().__init__(parent)
    # ... existing code ...
    
    # Ghost Notes Support
    self.layer_manager = LayerManager()
    self.ghost_renderer = GhostNotesRenderer(self)
```

#### Schritt 1.3: `paintEvent` erweitern

```python
def paintEvent(self, event):
    p = QPainter(self)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    
    # ... existing background/grid rendering ...
    
    # ★ GHOST NOTES RENDERING (before main notes!)
    if hasattr(self, 'ghost_renderer') and hasattr(self, 'layer_manager'):
        self.ghost_renderer.render_ghost_notes(p, self.layer_manager)
    
    # ... existing notes rendering ...
    # notes rendering code here
    
    p.end()
```

**Position:** Ghost Notes MÜSSEN **VOR** den normalen Noten gerendert werden!

---

### 2. Notation View Integration

**Datei:** `pydaw/ui/notation/notation_view.py`

#### Schritt 2.1: Imports hinzufügen

```python
from pydaw.model.ghost_notes import LayerManager
from pydaw.ui.notation.notation_ghost_notes import NotationGhostRenderer
```

#### Schritt 2.2: In `__init__` erweitern

```python
def __init__(self, project, parent=None):
    super().__init__(parent)
    # ... existing code ...
    
    # Ghost Notes Support
    self.layer_manager = LayerManager()
    self.ghost_renderer = NotationGhostRenderer(self)
    
    # Connect layer changes to refresh
    self.layer_manager.layers_changed.connect(self._refresh_ghost_notes)
```

#### Schritt 2.3: Refresh-Methode hinzufügen

```python
def _refresh_ghost_notes(self):
    """Refresh ghost notes when layers change."""
    if not hasattr(self, 'ghost_renderer'):
        return
    
    try:
        self.ghost_renderer.render_ghost_layers(
            self.scene(),
            self.layer_manager,
            self._layout,
            self._style,
        )
    except Exception:
        pass
```

#### Schritt 2.4: In `_render_notes` oder scene update

```python
def _render_notes(self, notes):
    # ... existing code ...
    
    # ★ Render ghost notes first
    if hasattr(self, 'ghost_renderer') and hasattr(self, 'layer_manager'):
        self.ghost_renderer.render_ghost_layers(
            self.scene(),
            self.layer_manager,
            self._layout,
            self._style,
        )
    
    # ... continue with main notes ...
```

---

### 3. Piano Roll Editor Integration

**Datei:** `pydaw/ui/pianoroll_editor.py`

#### Schritt 3.1: Import hinzufügen

```python
from pydaw.ui.layer_panel import LayerPanel
```

#### Schritt 3.2: Layer Panel hinzufügen

```python
class PianoRollEditor(QWidget):
    def __init__(self, ...):
        # ... existing code ...
        
        # Create layer panel
        self.layer_panel = LayerPanel(self.canvas.layer_manager)
        self.layer_panel.layer_added.connect(self._on_add_ghost_layer)
        
        # Add to layout (sidebar or dockable)
        # Option A: Add to sidebar
        sidebar_layout.addWidget(self.layer_panel)
        
        # Option B: Add as collapsible panel
        # ...
```

#### Schritt 3.3: Add Layer Handler

```python
def _on_add_ghost_layer(self):
    """Handle add ghost layer request."""
    # Show clip selector dialog
    from PyQt6.QtWidgets import QInputDialog
    
    # Get available MIDI clips from project
    clips = self.project.get_all_midi_clips()  # Implement this
    clip_names = [f"{clip['track_name']}: {clip['clip_name']}" for clip in clips]
    
    if not clip_names:
        return
    
    # Let user select a clip
    clip_name, ok = QInputDialog.getItem(
        self,
        "Add Ghost Layer",
        "Select MIDI Clip:",
        clip_names,
        0,
        False
    )
    
    if ok and clip_name:
        # Get clip ID
        idx = clip_names.index(clip_name)
        clip_id = clips[idx]['clip_id']
        track_name = clips[idx]['track_name']
        
        # Add to layer manager
        self.canvas.layer_manager.add_layer(
            clip_id=clip_id,
            track_name=track_name,
            opacity=0.3,
            state=LayerState.LOCKED,
        )
```

---

### 4. Notation Editor Integration

**Datei:** `pydaw/ui/notation_editor.py`

Identisch zu Piano Roll Editor - siehe Schritt 3.

---

## 🎨 UI Layout Optionen

### Option A: Sidebar Panel

```
┌─────────────────────────────────────┐
│  Piano Roll / Notation              │
│  ┌───────────┬──────────────────┐   │
│  │ Ghost     │                  │   │
│  │ Layers    │   Main Editor    │   │
│  │ Panel     │                  │   │
│  │           │                  │   │
│  │ ✎ Piano   │                  │   │
│  │ 🔒 Strings│                  │   │
│  │ 🔒 Bass   │                  │   │
│  └───────────┴──────────────────┘   │
└─────────────────────────────────────┘
```

### Option B: Collapsible Panel (empfohlen)

```
┌─────────────────────────────────────┐
│  ▼ Ghost Layers (3)                 │
│  ┌─────────────────────────────┐   │
│  │ ✎ Piano      [🎨] ████ 100% │   │
│  │ 🔒 Strings    [🎨] ████  30% │   │
│  │ 🔒 Bass       [🎨] ████  20% │   │
│  └─────────────────────────────┘   │
│                                     │
│  Main Editor Area                   │
└─────────────────────────────────────┘
```

### Option C: Toolbar Integration

```
Toolbar: [✎ Draw] [⬚ Select] [✂ Cut] | [👁 Layers ▼]
                                        └─── Dropdown Menu
```

---

## 🧪 Testing

### Test 1: Grundfunktion

```python
# In Python Console oder Test-Script
from pydaw.model.ghost_notes import LayerManager

manager = LayerManager()

# Add layers
layer1 = manager.add_layer("clip1", "Piano", is_focused=True)
layer2 = manager.add_layer("clip2", "Strings", opacity=0.3)
layer3 = manager.add_layer("clip3", "Bass", opacity=0.2)

# Get visible layers
for layer in manager.get_visible_layers():
    print(f"{layer.track_name}: opacity={layer.opacity:.0%}, focused={layer.is_focused}")

# Change focus
manager.set_focused_layer("clip2")
assert manager.get_focused_layer().track_name == "Strings"

# Lock layer
from pydaw.model.ghost_notes import LayerState
manager.set_layer_state("clip3", LayerState.LOCKED)
assert manager.get_layer("clip3").is_editable() == False

print("✅ Test passed!")
```

### Test 2: UI Panel

```bash
# Standalone test
cd pydaw/ui
python3 layer_panel.py

# Should open window with test layers
```

### Test 3: Rendering (manuell)

1. Öffne DAW
2. Erstelle 2-3 MIDI Clips mit Noten
3. Öffne Piano Roll für Clip 1
4. Füge Clip 2 als Ghost Layer hinzu (+ Button)
5. Verifiziere:
   - Clip 2 Noten sind sichtbar (30% opacity)
   - Clip 2 Noten sind nicht selektierbar
   - Nur Clip 1 (fokussiert) akzeptiert neue Noten
6. Ändere Opacity → Noten sollten sich updaten
7. Ändere Fokus → Noten sollten sich updaten

---

## 📊 Performance-Hinweise

### Optimierungen

✅ **Culling**: Nur sichtbare Noten rendern  
✅ **Caching**: Layer-Farben und Opacity cachen  
✅ **Lazy Rendering**: Nur bei tatsächlichen Änderungen neu rendern  
✅ **Z-Order**: Ghost Notes haben niedrigere Z-Order als Haupt-Noten

### Bei Performance-Problemen

- Max. 5-7 Ghost Layers gleichzeitig
- Opacity < 0.15 → Layer ausblenden
- Große Clips (>1000 Noten) → Warnung zeigen

---

## 🐛 Troubleshooting

### Problem: Ghost Notes werden nicht angezeigt

**Check 1:** Layer Manager initialisiert?
```python
assert hasattr(canvas, 'layer_manager')
assert hasattr(canvas, 'ghost_renderer')
```

**Check 2:** Layers hinzugefügt?
```python
assert canvas.layer_manager.has_layers()
```

**Check 3:** paintEvent ruft Renderer auf?
```python
# In paintEvent sollte stehen:
self.ghost_renderer.render_ghost_notes(p, self.layer_manager)
```

### Problem: Noten sind nicht durchsichtig

**Check:** Opacity-Wert korrekt?
```python
layer = manager.get_layer("clip_id")
assert layer.opacity == 0.3  # Should be 0.0-1.0
```

### Problem: Ghost Notes sind editierbar

**Check:** Layer State auf LOCKED?
```python
layer = manager.get_layer("clip_id")
assert layer.state == LayerState.LOCKED
assert not layer.is_editable()
```

---

## 📚 API Referenz

### LayerManager

```python
# Add layer
layer = manager.add_layer(clip_id, track_name, opacity=0.3, is_focused=False)

# Set focus
manager.set_focused_layer(clip_id)

# Lock/Unlock
manager.set_layer_state(clip_id, LayerState.LOCKED)
manager.set_layer_state(clip_id, LayerState.ACTIVE)

# Hide
manager.set_layer_state(clip_id, LayerState.HIDDEN)

# Change opacity
manager.set_layer_opacity(clip_id, 0.5)

# Get layers
layers = manager.get_visible_layers()  # sorted by z_order
focused = manager.get_focused_layer()
layer = manager.get_layer(clip_id)

# Remove
manager.remove_layer(clip_id)
manager.clear_layers()
```

### Signals

```python
# LayerManager signals
manager.layers_changed.connect(callback)           # Any layer change
manager.focused_layer_changed.connect(callback)    # Focus change (clip_id)

# LayerPanel signals
panel.layer_added.connect(callback)                # User clicked Add button
```

---

## ✅ Checkliste für Integration

- [ ] `pydaw/model/ghost_notes.py` existiert
- [ ] `pydaw/ui/layer_panel.py` existiert
- [ ] `pydaw/ui/pianoroll_ghost_notes.py` existiert
- [ ] `pydaw/ui/notation/notation_ghost_notes.py` existiert
- [ ] Piano Roll Canvas hat `layer_manager` + `ghost_renderer`
- [ ] Notation View hat `layer_manager` + `ghost_renderer`
- [ ] Piano Roll Editor hat Layer Panel
- [ ] Notation Editor hat Layer Panel
- [ ] paintEvent ruft `render_ghost_notes()` auf
- [ ] Ghost Notes rendern BEFORE main notes
- [ ] Standalone Tests laufen
- [ ] UI Tests (manuell) durchgeführt
- [ ] Performance getestet (5+ layers)
- [ ] Dokumentation aktualisiert

---

## 📝 Nächste Schritte (Optional)

### Erweiterungen

1. **Persistenz**: Layers im Projekt speichern (JSON)
2. **Keyboard Shortcuts**: `Alt+1-9` für Layer-Fokus
3. **Layer Groups**: Layers gruppieren (Strings, Brass, etc.)
4. **Color Themes**: Vordefinierte Layer-Farb-Paletten
5. **Sync Mode**: Ghost Notes folgen Transport-Playhead
6. **Note Filtering**: Filter nach Velocity/Pitch Range
7. **Layer Templates**: "String Section", "Rhythm Section" Templates
8. **MIDI Merge**: Layers zu einem Clip zusammenführen

### UI Verbesserungen

- Drag & Drop zum Reordering
- Layer Solo (alle anderen ausblenden)
- Layer Mute (alternative zu Hidden)
- Minimap mit Layer-Übersicht

---

**Status:** ✅ Feature komplett implementiert, bereit für Integration!  
**Bei Fragen:** Siehe Session Log oder Code-Kommentare
