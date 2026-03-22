# 📋 PyDAW - MASTER ARBEITSPLAN

**Projekt:** Py DAW Digital Audio Workstation  
**Aktuell:** v0.0.19.3.7.2 → v0.0.20.0  
**Erstellt:** 2026-01-31  
**Team:** Kollaborativ

---

## 🎯 PROJEKTSTRUKTUR

### Dokumentations-Ordner
```
Py_DAW_v0.0.19.3.7.2/
├── PROJECT_DOCS/                   # ← HAUPT-DOKUMENTATION
│   ├── plans/
│   │   ├── MASTER_PLAN.md         # Diese Datei - Gesamt-Übersicht
│   │   ├── ROADMAP.md             # Version Roadmap
│   │   └── ARCHITECTURE.md        # System-Architektur
│   │
│   ├── progress/
│   │   ├── TODO.md                # Globale TODO-Liste
│   │   ├── DONE.md                # Erledigte Tasks
│   │   └── BUGS.md                # Bug-Tracking
│   │
│   └── sessions/
│       ├── 2026-01-31_SESSION_1.md
│       ├── 2026-02-01_SESSION_2.md
│       └── ...
│
├── pydaw/                          # Source Code
├── VERSION                         # Versions-File
└── README.md                       # Haupt-README
```

---

## 📊 AKTUELLER STATUS

### Version: v0.0.19.3.7.2
**Datum:** 2026-01-31  
**Status:** Stabil, Notation-System fehlerhaft

### Was funktioniert ✅
- Audio-Engine (JACK/PipeWire)
- Arranger + Timeline
- Piano Roll Editor
- Mixer + Effects
- Transport + Recording
- Projekt speichern/laden

### Was NICHT funktioniert ❌
- Notation → MIDI Sync
- Notation → Arranger Sync
- Notation Context-Menu (crasht)
- Notation Tastenkombinationen
- Notation Canvas (C8-C9 unsichtbar)

---

## 🚀 NÄCHSTE PHASE: v0.0.20.0 - Notation Neuaufbau

### Ziel
Notation-System komplett neu in Qt6-nativ implementieren

### Aufwand
- **Total:** 11h
- **Phase 1 (MVP):** 4h
- **Phase 2 (Usable):** 3h  
- **Phase 3 (Polish):** 4h

### Start
**Nächste Session!** Siehe `PROJECT_DOCS/sessions/`

---

## 👥 FÜR NEUE ENTWICKLER

### 1. Projekt-Übersicht verstehen
**Lies in dieser Reihenfolge:**
1. Diese Datei (`PROJECT_DOCS/plans/MASTER_PLAN.md`)
2. `PROJECT_DOCS/plans/ARCHITECTURE.md` - System-Aufbau
3. `PROJECT_DOCS/progress/TODO.md` - Was zu tun ist
4. Neueste Session in `PROJECT_DOCS/sessions/` - Letzter Stand

### 2. Task auswählen
```bash
# Öffne TODO-Liste
cat PROJECT_DOCS/progress/TODO.md

# Suche Task mit Status: [ ] AVAILABLE
# Markiere ihn: [x] (Dein Name, Datum)
```

### 3. An Task arbeiten
```bash
# Erstelle Session-Log
touch PROJECT_DOCS/sessions/$(date +%Y-%m-%d)_SESSION_X.md

# Dokumentiere:
# - Was machst du?
# - Welche Files änderst du?
# - Probleme & Lösungen
```

### 4. Nach Fertigstellung
```bash
# 1. Update TODO.md - Task als [x] DONE
# 2. Update DONE.md - Task eintragen
# 3. Update Session-Log
# 4. Commit + Push (falls Git)
```

---

## 📋 ARBEITSABLAUF

### Workflow für jeden Task

```
1. CHECK TODO.md
   ↓
2. Task auswählen & markieren
   ↓
3. Session-Log erstellen
   ↓
4. Code schreiben
   ↓
5. Dokumentieren im Session-Log
   ↓
6. TODO.md & DONE.md updaten
   ↓
7. Commit (optional)
```

### Session-Log Template
```markdown
# Session: DATUM

## Task
- [x] Task-Name (aus TODO.md)

## Änderungen
- File X: Funktion Y hinzugefügt
- File Z: Bug gefixt

## Probleme
- Problem A → Lösung B

## Nächster Schritt
- Task C steht an
```

---

## 🔧 DEVELOPMENT GUIDELINES

### Code-Standards
- **Python:** PEP 8, Type Hints
- **Qt6:** Signals statt direct calls
- **Kommentare:** Deutsch oder Englisch konsistent
- **Tests:** Unit-Tests für Core-Logic

### File-Organisation
```python
# Jede neue Feature-Komponente:
pydaw/ui/feature_name/
├── __init__.py
├── main_widget.py      # Haupt-Widget
├── sub_component.py    # Sub-Komponenten
└── utils.py            # Helper-Funktionen
```

### Git Commit Messages (falls verwendet)
```
feat(notation): Staff-Renderer implementiert
fix(arranger): Clip-Erweiterung repariert
docs: Session-Log für 2026-01-31 hinzugefügt
```

---

## 📅 VERSIONS-ROADMAP

### v0.0.20.0 (MVP) - 4h
**Ziel:** Noten werden angezeigt
- [ ] Daten-Model erweitert
- [ ] Staff-Renderer
- [ ] NotationView Widget
- [ ] Basis-Rendering funktioniert

### v0.0.20.1 (Usable) - 3h
**Ziel:** Interaktive Bearbeitung
- [ ] Draw-Tool
- [ ] Erase-Tool
- [ ] Select-Tool
- [ ] MIDI ↔ Notation Sync

### v0.0.20.2 (Polished) - 4h
**Ziel:** Production-Ready
- [ ] Keyboard-Shortcuts
- [ ] Clip-Auto-Erweiterung
- [ ] Farb-System
- [ ] Context-Menu

### v0.0.21.0 (Future)
**Geplant:** Erweiterte Features
- [ ] Multi-Track Notation
- [ ] Chord-Symbols
- [ ] Lyrics
- [ ] Print-Layout

---

## 🐛 BUG-TRACKING

**Siehe:** `PROJECT_DOCS/progress/BUGS.md`

### Critical Bugs
- Notation Context-Menu crasht → v0.0.20.0
- Notation → Arranger Sync fehlt → v0.0.20.1

### High Priority
- Canvas C8-C9 unsichtbar → v0.0.20.0
- Auto-Scroll buggy → v0.0.20.1

---

## 📊 ERFOLGS-KRITERIEN

### Definition of Done (DoD)
Ein Task ist "DONE" wenn:
- [x] Code funktioniert (getestet)
- [x] Dokumentiert (Docstrings)
- [x] Session-Log geschrieben
- [x] TODO.md updated
- [x] DONE.md updated
- [x] Keine neuen Bugs eingeführt

---

## 📞 KOMMUNIKATION

### Fragen?
1. **Architektur:** Siehe `PROJECT_DOCS/plans/ARCHITECTURE.md`
2. **API:** Siehe Code-Docstrings
3. **Bugs:** Siehe `PROJECT_DOCS/progress/BUGS.md`
4. **TODO:** Siehe `PROJECT_DOCS/progress/TODO.md`

### Probleme melden
```markdown
# In SESSION_LOG.md:

## Problem
Beschreibung des Problems

## Versucht
- Lösung A (hat nicht funktioniert)
- Lösung B (hat nicht funktioniert)

## Benötigt
Hilfe bei X
```

---

## 📚 RESSOURCEN

### Dokumentation
- Qt6: https://doc.qt.io/qt-6/
- PyQt6: https://www.riverbankcomputing.com/
- Python: https://docs.python.org/3/

### Projekt-Files
- `pydaw/services/project_service.py` - Data Layer
- `pydaw/ui/pianoroll.py` - Referenz für MIDI-Editor
- `pydaw/ui/main_window.py` - GUI-Integration

---

## ✅ WICHTIG

### Vor Start einer Session:
1. **Lies** neueste Session-Logs
2. **Prüfe** TODO.md
3. **Update** deine Umgebung (git pull)

### Nach Ende einer Session:
1. **Update** TODO.md
2. **Update** DONE.md
3. **Schreibe** Session-Log
4. **Commit** Changes (falls Git)

---

**Letzte Aktualisierung:** 2026-01-31 07:30  
**Aktualisiert von:** Claude  
**Nächster Schritt:** Siehe `PROJECT_DOCS/progress/TODO.md`
