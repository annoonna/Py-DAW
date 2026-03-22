# 🎭 GHOST NOTES - COMPLETION ROADMAP

**Status:** In Arbeit - bis zur 100% Fertigstellung  
**Dann:** Zurück zu Notation Tasks (Multi-Track, Chords, Lyrics)  
**Version:** v0.0.19.3.7.16 → v0.0.19.3.7.X

---

## ✅ WAS IST FERTIG

- [x] Datenmodell (LayerManager, GhostLayer)
- [x] Layer Panel UI (vollständig)
- [x] Piano Roll Ghost Rendering
- [x] Notation Ghost Rendering
- [x] Integration in Piano Roll Canvas
- [x] Integration in Notation View
- [x] Integration in Editoren (Layer Panel sichtbar)
- [x] Dokumentation (komplett)

---

## 🔧 WAS FEHLT NOCH (BIS 100%)

### 1. Clip-Auswahl-Dialog ⏳ JETZT
**Priority:** CRITICAL  
**Aufwand:** 30min  
**Status:** In Arbeit

**Was:**
- Dialog beim Klick auf "+ Add Layer" Button
- Zeige alle verfügbaren MIDI-Clips
- User wählt Clip aus
- Clip wird als Ghost Layer hinzugefügt

**Files zu ändern:**
- `pydaw/ui/layer_panel.py` (Signal-Handler erweitern)
- `pydaw/ui/pianoroll_editor.py` (Dialog implementieren)
- `pydaw/ui/notation/notation_view.py` (Dialog implementieren)

**Blocker:** Aktuell kann man Ghost Layers nicht wirklich nutzen!

---

### 2. Bugfixes & Polish ⏳ DANACH
**Priority:** HIGH  
**Aufwand:** 1-2h

**2.1 Canvas C8-C9 unsichtbar**
- Problem: Hohe Noten (C8-C9) werden abgeschnitten
- Fix: Erhöhe MinimumHeight in Piano Roll Canvas
- File: `pydaw/ui/pianoroll_canvas.py`

**2.2 Auto-Scroll buggy**
- Problem: Scroll-Verhalten beim Note-Hinzufügen nicht smooth
- Fix: Scroll-Logik in Piano Roll + Notation verbessern
- Files: `pydaw/ui/pianoroll_canvas.py`, `pydaw/ui/notation/notation_view.py`

**2.3 Farben nicht identisch**
- Problem: Piano Roll vs Notation haben unterschiedliche Farben
- Fix: Velocity-Color-Mapping angleichen
- Files: `pydaw/ui/notation/colors.py`

**2.4 Glow-Effect in Notation**
- Problem: Selektierte Noten in Notation haben keinen Glow wie Piano Roll
- Fix: Glow-Rendering für selektierte Noten hinzufügen
- File: `pydaw/ui/notation/notation_view.py`

---

### 3. Testing & Validation ⏳ DANN
**Priority:** MEDIUM  
**Aufwand:** 1h

**3.1 Integration Tests**
- [ ] Piano Roll mit 3+ Ghost Layers testen
- [ ] Notation mit 3+ Ghost Layers testen
- [ ] Layer Lock verhindert Editing (verifizieren)
- [ ] Fokus-Wechsel funktioniert korrekt
- [ ] Opacity-Änderung updates Rendering
- [ ] Performance mit 5+ Layers (Benchmark)

**3.2 Edge Cases**
- [ ] Ghost Layer von gelöschtem Clip (sollte graceful fail)
- [ ] Ghost Layer vom gleichen Clip (sollte verhindern)
- [ ] Leere Clips als Ghost Layer (sollte funktionieren)
- [ ] Sehr viele Noten (Performance-Check)

---

### 4. Optional Enhancements ⏳ OPTIONAL
**Priority:** LOW  
**Aufwand:** 2-3h

**4.1 Layer Persistenz**
- Ghost Layers im Projekt speichern (JSON)
- Beim Projekt-Laden wiederherstellen
- Files: `pydaw/services/project_service.py`

**4.2 Keyboard Shortcuts**
- `Alt+1-9` für schnellen Layer-Fokus-Wechsel
- `Ctrl+Shift+L` für Layer Panel toggle
- File: `pydaw/ui/pianoroll_editor.py`, `pydaw/ui/notation/notation_view.py`

**4.3 Layer Solo/Mute**
- Solo: Alle anderen ausblenden
- Mute: Layer temporär verstecken (wie Hidden aber schneller)
- File: `pydaw/model/ghost_notes.py`, `pydaw/ui/layer_panel.py`

**4.4 Workbook Dialog Integration**
- Ghost Notes Status im Workbook anzeigen
- File: `pydaw/ui/workbook_dialog.py`

---

## 🎯 WORKFLOW BIS 100% COMPLETION

```
Phase 1: CRITICAL (JETZT!)
├── 1. Clip-Auswahl-Dialog implementieren (30min)
└── Status: Ghost Notes ist voll nutzbar ✅

Phase 2: BUGFIXES & POLISH (DANACH)
├── 2.1 Canvas C8-C9 Fix (15min)
├── 2.2 Auto-Scroll Fix (30min)
├── 2.3 Farben angleichen (20min)
└── 2.4 Glow-Effect Notation (20min)
└── Status: DAW ist stabil und polished ✅

Phase 3: TESTING (DANN)
├── 3.1 Integration Tests (30min)
├── 3.2 Edge Cases (30min)
└── Status: Alles getestet und validiert ✅

Phase 4: OPTIONAL (Wenn du willst)
├── 4.1 Persistenz (1h)
├── 4.2 Shortcuts (30min)
├── 4.3 Solo/Mute (1h)
└── 4.4 Workbook Integration (30min)
└── Status: Extra Features für Power-User ✅
```

---

## 🔄 DANACH: ZURÜCK ZU NOTATION

**Nach Ghost Notes Completion (100%):**

→ **Zurück zu Notation-Entwicklung:**
- Task 12: Multi-Track Notation (4h)
- Task 13: Chord-Symbols (2h)
- Task 14: Lyrics-Support (3h)

**Dokumentiert in:** `TODO.md` (Priorität nach Ghost Notes)

---

## ⚠️ KONFLIKT-VERMEIDUNG

**Ghost Notes berührt NICHT:**
- Notation Core-Rendering (nur Layer darüber)
- Piano Roll Core-Rendering (nur Layer darunter)
- Project Service MIDI-Noten (nur Read-Access)
- Andere Features

**Sicher weil:**
- Separate Module (`ghost_notes.py`, `layer_panel.py`, etc.)
- Nur Rendering-Layer (kein Core-Logic Change)
- Observer Pattern (kein direktes Coupling)
- Z-Order getrennt (Ghost unter Main)

**Keine Crashes weil:**
- Try-Except bei allen Ghost Rendering Calls
- Graceful Degradation (wenn Ghost fehlt, funktioniert Rest trotzdem)
- Keine Breaking Changes in existierenden Modulen

---

## 📊 PROGRESS TRACKING

```
Ghost Notes Completion: ██████░░░░ 60%

✅ Implementation: 100%
✅ Integration: 100%
⏳ Clip-Dialog: 0%   ← JETZT HIER
⏳ Bugfixes: 0%
⏳ Testing: 0%
⏳ Optional: 0%
```

---

## 🎯 NEXT SESSION

**Start:** Clip-Auswahl-Dialog  
**Dann:** Bugfixes (Canvas, Scroll, Farben, Glow)  
**Dann:** Testing  
**Dann:** Optional Features (wenn gewünscht)  
**Dann:** ✅ Ghost Notes 100% DONE → Zurück zu Notation!

---

**DIESER WORKFLOW IST VERANKERT!**  
Alle weiteren Sessions arbeiten diese Liste ab, bis Ghost Notes 100% ist.  
Dann geht es weiter mit Notation Multi-Track/Chords/Lyrics.
