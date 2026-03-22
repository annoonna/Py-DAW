# 🎭 Ghost Notes / Layered Editing - Quick Start

**Feature:** Multi-Layer MIDI Visualization  
**Version:** v0.0.19.3.7.15  
**Status:** ✅ Ready for Integration  
**Developer:** Claude-Sonnet-4.5  
**Date:** 2026-02-01

---

## 📋 Was ist Ghost Notes?

Ghost Notes ermöglicht es, **MIDI-Noten aus mehreren Clips/Tracks gleichzeitig** im Piano Roll und Notation Editor zu visualisieren - ähnlich wie in **Pro-DAW**.

### Use Cases

✅ **Harmonien erstellen**: Sieh Bass-Noten während du Melodie schreibst  
✅ **Orchestration**: Vergleiche String-Parts während du Brass arrangierst  
✅ **Rhythmus-Koordination**: Bass + Drums gleichzeitig sehen  
✅ **Referenz**: Ursprüngliche MIDI als Vorlage nutzen  
✅ **Multi-Part Editing**: Zwischen Clips wechseln ohne Kontext zu verlieren

---

## 🎯 Kernfunktionen

| Feature | Beschreibung |
|---------|--------------|
| **Multi-Layer** | Zeige bis zu 7 MIDI-Clips gleichzeitig |
| **Ghost Notes** | Inaktive Noten mit 30% Deckkraft |
| **Lock Mode** | Gesperrte Layers sind sichtbar aber nicht editierbar |
| **Focus Mode** | Nur fokussierter Layer akzeptiert neue Noten (✎) |
| **Color Coding** | Jeder Layer hat eigene Farbe |
| **Opacity Control** | Individueller Opacity-Slider pro Layer |

---

## 🚀 Quick Demo

### Standalone Test (ohne DAW)

```bash
cd pydaw/ui
python3 layer_panel.py
```

→ Öffnet Fenster mit Test-Layers  
→ Teste alle Controls (Focus, Lock, Opacity, Color)

### In DAW (nach Integration)

1. Öffne Piano Roll für Clip 1 (z.B. Piano)
2. Klicke **"+ Add Layer"** Button
3. Wähle Clip 2 (z.B. Strings) aus Dialog
4. Clip 2 Noten erscheinen transparent (30% Opacity)
5. Nur Clip 1 (fokussiert ✎) akzeptiert neue Noten
6. Clip 2 Noten können **nicht** selektiert/gelöscht werden (locked 🔒)

---

## 📦 Dateien

```
Neue Files:
pydaw/
├── model/
│   └── ghost_notes.py               # Datenmodell (LayerManager)
├── ui/
│   ├── layer_panel.py               # Layer Management UI
│   ├── pianoroll_ghost_notes.py    # Piano Roll Rendering
│   └── notation/
│       └── notation_ghost_notes.py  # Notation Rendering

Documentation:
PROJECT_DOCS/
├── features/
│   └── GHOST_NOTES_INTEGRATION.md   # Integration Guide
└── sessions/
    └── 2026-02-01_SESSION_GHOST_NOTES.md  # Session Log
```

---

## 🔧 Integration (Simplified)

### Step 1: Piano Roll

**File:** `pydaw/ui/pianoroll_canvas.py`

```python
# Add to imports
from pydaw.model.ghost_notes import LayerManager
from pydaw.ui.pianoroll_ghost_notes import GhostNotesRenderer

# Add to __init__
self.layer_manager = LayerManager()
self.ghost_renderer = GhostNotesRenderer(self)

# Add to paintEvent (BEFORE main notes!)
self.ghost_renderer.render_ghost_notes(p, self.layer_manager)
```

### Step 2: Notation View

**File:** `pydaw/ui/notation/notation_view.py`

```python
# Add to imports
from pydaw.model.ghost_notes import LayerManager
from pydaw.ui.notation.notation_ghost_notes import NotationGhostRenderer

# Add to __init__
self.layer_manager = LayerManager()
self.ghost_renderer = NotationGhostRenderer(self)

# Add refresh call
self.ghost_renderer.render_ghost_layers(
    self.scene(), self.layer_manager, self._layout, self._style
)
```

### Step 3: Layer Panel

**File:** `pydaw/ui/pianoroll_editor.py`

```python
# Add to imports
from pydaw.ui.layer_panel import LayerPanel

# Add to layout
self.layer_panel = LayerPanel(self.canvas.layer_manager)
sidebar_layout.addWidget(self.layer_panel)
```

**Detaillierte Anleitung:** Siehe `GHOST_NOTES_INTEGRATION.md`

---

## 🧪 Testing

### Unit Tests

```bash
# Test LayerManager
python3 -m pydaw.model.ghost_notes

# Test Layer Panel UI
python3 -m pydaw.ui.layer_panel
```

### Integration Tests (nach Integration)

1. ✅ Erstelle 3 MIDI Clips mit Noten
2. ✅ Öffne Piano Roll für Clip 1
3. ✅ Füge Clip 2 + 3 als Ghost Layers hinzu
4. ✅ Verifiziere: Ghost Notes sind transparent
5. ✅ Verifiziere: Ghost Notes sind nicht selektierbar
6. ✅ Verifiziere: Nur Clip 1 akzeptiert neue Noten
7. ✅ Ändere Opacity → Updates sofort
8. ✅ Ändere Focus → Nur neuer Layer editierbar

---

## 📚 API Quick Reference

```python
from pydaw.model.ghost_notes import LayerManager, LayerState

# Create manager
manager = LayerManager()

# Add layer
layer = manager.add_layer(
    clip_id="clip_123",
    track_name="Piano",
    opacity=0.3,
    is_focused=False
)

# Set focus (only focused layer accepts edits)
manager.set_focused_layer("clip_123")

# Lock layer (visible but not editable)
manager.set_layer_state("clip_123", LayerState.LOCKED)

# Change opacity
manager.set_layer_opacity("clip_123", 0.5)

# Get layers
visible_layers = manager.get_visible_layers()
focused_layer = manager.get_focused_layer()

# Signals
manager.layers_changed.connect(callback)
manager.focused_layer_changed.connect(callback)
```

---

## ❓ FAQ

### Q: Kann ich mehr als 7 Layers haben?

**A:** Technisch ja, aber Performance kann leiden. Empfohlen: max 5-7 Layers.

### Q: Werden Layers im Projekt gespeichert?

**A:** Aktuell NEIN (v0.0.19.3.7.15). Optional für spätere Version.

### Q: Kann ich Ghost Notes bearbeiten?

**A:** Nein (wenn locked). Das ist by design - nur der fokussierte Layer ist editierbar.

### Q: Wie ändere ich den fokussierten Layer?

**A:** Klicke auf das Pencil-Icon (✎) im Layer Panel.

### Q: Wie verstecke ich einen Layer?

**A:** Deaktiviere das Eye-Icon (👁) im Layer Panel.

---

## 🎨 UI Controls

### Layer Panel

```
┌─────────────────────────────────────┐
│ Ghost Layers                   [+ ] │ ← Add Layer
├─────────────────────────────────────┤
│ ✎ 👁 🔓 [🎨] Piano    ████ 100%   │ ← Focused (editable)
│   👁 🔒 [🎨] Strings  ████  30%   │ ← Locked (visible)
│   👁 🔒 [🎨] Bass     ████  20%   │ ← Locked (visible)
└─────────────────────────────────────┘
  │  │  │   │           └─ Opacity Slider
  │  │  │   └─ Color Picker
  │  │  └─ Lock/Unlock Toggle
  │  └─ Visibility Toggle
  └─ Focus (only one can be focused)
```

### Icons

- **✎** = Focused Layer (accepts new notes)
- **👁** = Visible
- **🔒** = Locked (not editable)
- **🔓** = Unlocked (editable if focused)
- **🎨** = Color Picker

---

## 📊 Performance

### Optimizations

✅ Culling - nur sichtbare Noten rendern  
✅ Z-Order - Ghost Notes unter Main Notes  
✅ Lazy Rendering - nur bei Changes  
✅ Color/Opacity Caching

### Benchmarks (geschätzt)

| Layers | Notes/Layer | Performance |
|--------|-------------|-------------|
| 1-3    | <1000       | Excellent   |
| 4-5    | <1000       | Good        |
| 6-7    | <1000       | Ok          |
| 8+     | <1000       | Slow        |

---

## 🐛 Troubleshooting

### Ghost Notes werden nicht angezeigt

```python
# Check 1: Manager initialized?
assert hasattr(canvas, 'layer_manager')
assert hasattr(canvas, 'ghost_renderer')

# Check 2: Layers added?
assert canvas.layer_manager.has_layers()

# Check 3: Rendering called?
# In paintEvent should be:
self.ghost_renderer.render_ghost_notes(p, self.layer_manager)
```

### Ghost Notes sind nicht transparent

```python
# Check opacity value
layer = manager.get_layer("clip_id")
print(f"Opacity: {layer.opacity}")  # Should be 0.0-1.0
```

---

## 📖 Weitere Dokumentation

- **Detaillierte Integration:** `PROJECT_DOCS/features/GHOST_NOTES_INTEGRATION.md`
- **Session Log:** `PROJECT_DOCS/sessions/2026-02-01_SESSION_GHOST_NOTES.md`
- **API Referenz:** In den Docstrings der Module
- **Examples:** In jedem Modul unter `if __name__ == "__main__"`

---

## ✅ Status Checklist

**Implementation:**
- [x] Datenmodell (ghost_notes.py)
- [x] Layer Panel UI (layer_panel.py)
- [x] Piano Roll Rendering (pianoroll_ghost_notes.py)
- [x] Notation Rendering (notation_ghost_notes.py)
- [x] Dokumentation (GHOST_NOTES_INTEGRATION.md)
- [x] Tests (Standalone)

**Integration:**
- [ ] Piano Roll Canvas erweitert
- [ ] Notation View erweitert
- [ ] Layer Panel in Editors eingebunden
- [ ] Integration Tests durchgeführt
- [ ] User Testing

**Status:** ✅ Ready for Integration  
**Next:** Follow `GHOST_NOTES_INTEGRATION.md` for step-by-step guide

---

**Bei Fragen:** Siehe Integration Guide oder Code-Kommentare  
**Support:** Session Log enthält alle Design-Entscheidungen
