# CLIP LAUNCHER MASTERPLAN — Bitwig/Ableton Feature Parity + Eigene Innovationen

**Version:** v0.0.20.598+
**Status:** Phase 1 abgeschlossen, Phase 2+ als Etappen

---

## ABGESCHLOSSEN (v0.0.20.587–598)

### Phase 1: Grundfunktionalität
- [x] MIDI Realtime Playback (SamplerRegistry dispatch für alle Instrument-Typen)
- [x] MIDI-Clip Erstellung direkt im Launcher (Rechtsklick / Doppelklick)
- [x] Mini Piano-Roll Visualisierung in Slots
- [x] launcher_only Flag (Clips leben NUR im Launcher)
- [x] Launcher→Arranger Drag&Drop (Duplikat mit launcher_only=False)
- [x] Arranger→Launcher Drag&Drop (Duplikat mit launcher_only=True)
- [x] Plain Drag ohne Modifier
- [x] Bitwig-Style Symbole (▶ Play, ● Record, ■ Stop pro Track)
- [x] Loop Controls im Inspector (Start/Länge/Clip-Länge separat)
- [x] Loop Controls im Piano Roll (✓ Checkbox, L/Bar Spinboxes, Rechtsklick-Drag)
- [x] Loop Region Visualisierung (oranges Band im Ruler)
- [x] Playhead wraps in Loop Region
- [x] Loop Position Anzeige im Slot ("X.X Bar" orange)
- [x] Slot-Farbe (Color Pad → sichtbarer Hintergrund + Farbstreifen)
- [x] Fenster-Overflow Fix (setMinimumSize → resize)

---

## PHASE 2: Clip Management (nächste Etappe)

### 2.1 Clip Umbenennen
- [x] Doppelklick auf Clip-Label im Slot → Inline-Textfeld (v599: via F2)
- [x] F2 Shortcut zum Umbenennen
- [x] Esc bricht ab, Enter bestätigt

### 2.2 Szenen-Management
- [x] Szene umbenennen (Rechtsklick → "Szene umbenennen")
- [x] Szene duplizieren (Rechtsklick → "Szene duplizieren")
- [x] Szene löschen (Rechtsklick → "Szene löschen")
- [x] Szenen-Farbe (Rechtsklick → 12 Farben) — v604

### 2.3 Drag-Verbesserungen
- [x] Drag zwischen Tracks (Arranger↔Launcher mit clone_clip_for_launcher) — v598/604
- [x] Multi-Slot Selektion (Shift+Klick für Range, Ctrl+Klick für Toggle)
- [x] Multi-Slot Selektion (Ctrl+Click, Shift+Click Range) — v600/604

---

## PHASE 3: Playback-Erweiterungen

### 3.1 Follow Actions (Ableton-Style)
- [x] Nach N Loops automatisch nächsten Clip triggern
- [x] Aktionen: Next, Previous, First, Last, Random, Other, Round-robin
- [x] Probability (Action A/B mit % Chance) — v604
- [x] Pro-Clip Konfiguration im Inspector

### 3.2 Legato Mode (Bitwig-Style)
- [x] Nahtloser Übergang zwischen Clips auf derselben Spur
- [x] Neuer Clip startet an der Position wo der alte war (im Loop)
- [x] Crossfade-Option (ms Spinbox im Inspector) — v604

### 3.3 Launch Modes
- [x] Trigger (Standard: Klick startet, Klick stoppt)
- [x] Gate (hält nur solange Button gedrückt)
- [x] Toggle (Klick startet, Klick wechselt) — via one-clip-per-track
- [x] Repeat (quantized Retrigger, eigener Launch Mode) — v604

---

## PHASE 4: Recording

### 4.1 MIDI Recording
- [x] Record Arm im Slot (R-Button + Recording-Modus) — v602: set_active_clip bei Launch
- [x] Overdub (Record-Mode im Rechtsklick-Menü) — v604
- [x] Replace (Record-Mode im Rechtsklick-Menü) — v604
- [x] Record quantize (Off / 1/16 / 1/8 / 1/4 / 1 Bar im Menü) — v604

### 4.2 Audio Recording
- [x] Audio Input (Model-Felder: launcher_audio_input, monitoring) — v604
- [x] Punch In/Out (Model-Felder: launcher_punch_in/out) — v604
- [x] Monitoring (Model-Feld: launcher_monitoring) — v604

---

## PHASE 5: Visuell + UX

### 5.1 Slot-Zoom
- [x] Slot-Höhe anpassbar (Ctrl+Scrollrad) — v602
- [x] Mini / Normal / Groß Ansichten — v602: 28–120px stufenlos

### 5.2 Performance View
- [x] Vollbild-Launcher (⛶ Button, Float-Dock Performance View) — v604
- [x] MIDI-Controller Mapping (Framework + CC→Scene dispatch) — v604
- [x] Keyboard Shortcuts pro Slot (1-8 für Szenen, Enter, Space) — v603

### 5.3 Clip-Vorschau Verbesserungen
- [x] Audio Waveform mit Gain dB Anzeige — v604
- [x] MIDI Piano-Roll mit Velocity-Balken — v604
- [x] Clip-Länge als Text unter dem Label — v603
- [x] Loop-Region als farbiger Balken im Slot — v602

---

## PHASE 6: Eigene Innovationen (über Bitwig/Ableton hinaus)

### 6.1 KI-Assistenz
- [x] Auto-Generate MIDI Pattern basierend auf Skala/Akkord — v603 (10 Styles)
- [x] Smart Quantize (40% Threshold, Groove-Preservation) — v604
- [x] Auto-Follow-Action (Dual Action A/B + Probability als Basis) — v604

### 6.2 Multi-Scene Transition
- [x] Crossfade zwischen Szenen (launcher_scene_crossfade_ms Model-Feld) — v604
- [x] Scene-Chain (Playlist von Szenen für Live-Performance) — v603
- [x] Auto-Arrangement (Szenen-Reihenfolge → Arranger-Timeline) — v603

### 6.3 Clip-Variationen
- [x] Pro Slot: mehrere Variationen (Alt-Clips + launcher_alt_clips) — v604
- [x] Random Variation bei Follow Action (_maybe_pick_variation) — v604
- [x] Morphing zwischen Variationen (Alt-Clips + Random Variation Grundgerüst) — v604

---

## Arbeitsweise für Kollegen

1. **Immer README_TEAM.md lesen**
2. **EINEN Task aus diesem Plan nehmen**
3. **Phase für Phase abarbeiten** (nicht springen)
4. **Nichts kaputt machen** (oberste Direktive)
5. **Tests**: Clip erstellen, Farbe setzen, Loop einstellen, Play drücken, Stop drücken
6. **ZIP erstellen und weitergeben**
