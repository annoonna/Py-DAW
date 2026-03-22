# 🚀 ChronoScaleStudio (Py_DAW) - TEAM-ÜBERGABE ANLEITUNG

**FÜR JEDEN KOLLEGEN - LIES DAS ZUERST!**

---

## 🎯 PROJEKT-ZIEL

Wir bauen eine **DAW (Digital Audio Workstation)** ähnlich wie:
- **Professioneller Notations-Editor** (Linux)
- **Pro-DAW**
- Aber: **UNSERE EIGENE!**

**Name:** ChronoScaleStudio (Py_DAW)  
**Sprache:** Python + Qt6  
**Audio:** JACK/PipeWire  
**Status:** In Entwicklung

---

## 🧠 TL;DR: Audio-Routing (1 Seite)

**Merksatz:** **`track_id` = Kanal / Instrument-Ziel** (nicht Pitch, nicht “anderer Notenbereich”).  
Darum können **SF2**, **Pro Audio Sampler** und **Pro Drum Machine** alle **C-1..C9** benutzen, ohne sich zu “kollidieren”:  
Die Noten werden beim Playback als **Events mit `track_id`** geroutet.

```
[ PianoRoll / Notation ]  (UI)
          |
          | schreibt MidiNote → Clip (clip_id)
          v
[ Project Model / ProjectService ]  (Undo/Redo, Clips, Noten)
          |
          | Transport: Playhead/BPM/Loop
          v
[ arrangement_renderer.py ]  (Prepare aktive Clips)
   ├─ SF2: MIDI → WAV Cache  (midi_render.py)  → wird wie Audio gemischt
   └─ Realtime Inst.: MIDI → PreparedMidiEvent(track_id,pitch,vel,time)
          |
          v
[ hybrid_engine.py ]  (Audio-Thread: Realtime Callback)
   - TrackParamState: Vol/Pan/Mute/Solo pro track_id (clickfrei gesmoothed)
   - MIDI Dispatch:
        SamplerRegistry.note_on(track_id, pitch, vel) / note_off(...)
   - Pull-Sources (Sampler/Drums):
        audio = pull(frames, sr)
        (pull ist getaggt mit _pydaw_track_id → per-Track Mix + VU)
   - Mixing:
        track_audio → Master → Output
   - Metering:
        AudioEngine._direct_peaks[track_id]  → Track-VU im Mixer
        Master-Peaks                      → Master-VU
          |
          v
[ JACK/PipeWire oder sounddevice ]  → Lautsprecher / Recording / Exporte
```

**Wichtig für neue Instrumente:**  
Wenn dein Instrument Realtime Audio liefert (Pull-Source), muss das Callable **`_pydaw_track_id`** anbieten, damit:
- Track-Fader (Vol/Pan/Mute/Solo) korrekt wirken
- Track-VU im Mixer ausschlägt (per-Track Peaks)

Details: `PROJECT_DOCS/plans/AUDIO_SYSTEM.md`

## 🆕 Neu in v0.0.20.89 — Automation System Foundation (Bitwig/Ableton-Grade)
- **AutomatableParameter System:** Jeder Parameter kann jetzt automatisiert + moduliert werden
  - Unified Value Stack: Manual (GUI) + Timeline Automation + Modulation gleichzeitig
  - Lock-free: GUI schreibt, Audio-Thread liest via RTParamStore
- **Breakpoint Envelopes mit Bezier-Kurven:**
  - 4 Kurventypen: **Linear**, **Bezier** (quadratisch, draggable Control Points), **Step** (diskret), **Smooth** (S-Curve)
  - Sample-genaue Interpolation (anti-Zipper-Noise)
- **AutomatedKnob Widget (Bitwig-Style):**
  - Rundes Knob-Widget mit Modulations-Ring (orange/purple für +/−)
  - Rechtsklick → "Show Automation in Arranger" öffnet automatisch die richtige Lane
  - Shift+Drag = Feineinstellung, Doppelklick = Reset
- **Enhanced Automation Lane Editor:**
  - Professioneller Kurven-Editor mit Beat/Bar Grid + Playhead
  - FX-Parameter Auswahl (Volume, Pan + alle registrierten Parameter, durchsuchbar)
  - Track/Mode/Curve-Type Selektoren
- **AutomationManager (zentraler Service):**
  - Signal `request_show_automation(parameter_id)` → jedes Widget kann Automation im Arranger öffnen
  - `tick(beat)` bei Playback → interpoliert Lane-Daten → Parameter

## 🆕 Neu in v0.0.20.88 — DAWproject Import (Bitwig/Studio One/Cubase)
- **DAWproject Import:** Projekte aus Bitwig Studio, Studio One und Cubase können jetzt importiert werden!
  - Menü: **Datei → DAWproject importieren… (.dawproject)** oder **Ctrl+Shift+I**
  - Importiert: Tracks, MIDI-Clips + Noten, Audio-Clips + Dateien, BPM, Taktart
  - Audio-Dateien werden automatisch in das Projekt-Media-Verzeichnis extrahiert
  - Non-destructive: Bestehende Inhalte im Projekt bleiben erhalten
  - Progress-Dialog zeigt Fortschritt, Summary-Dialog zeigt Ergebnis
  - Basiert auf dem offenen DAWproject-Standard (https://github.com/bitwig/dawproject)

## 🆕 Neu in v0.0.20.87 — Drag-over-Tab Auto-Switch (Bitwig-Style)
- **Tab wechselt automatisch beim Drag:** Wenn man eine Spur aus der TrackList über einen anderen Tab zieht, wechselt der Tab nach 500ms automatisch (genau wie in Bitwig/Ableton)
  - Workflow: Spur greifen → über Ziel-Tab hovern → Tab wechselt → auf Arranger droppen
  - Timer-basiert: 500ms Hover-Delay verhindert versehentliches Tab-Switching
  - Funktioniert mit Cross-Project Drags und Datei-Drags (Audio/MIDI)
  - Kein Crash: Defensive try/except in allen Drag-Events
- **Bugfix:** Potentieller Cursor-Crash in TrackList Drag-Start behoben

## 🆕 Neu in v0.0.20.86 — Cross-Project Track Drag&Drop
- **Track-Drag aus TrackList:** Spuren können jetzt direkt aus der TrackList (links im Arranger) per Drag&Drop in einen anderen Projekt-Tab gezogen werden
  - Multi-Select: Shift+Klick / Ctrl+Klick für mehrere Spuren gleichzeitig
  - Full State Transfer: Device-Chains, Clips, MIDI-Notes, Automationen werden mitkopiert
  - Ghost-Clip Preview (blau) im Ziel-Arranger
  - UI refresht automatisch nach dem Drop (TrackList, Mixer, DevicePanel)
  - **Workflow:** Tab A → Spur(en) auswählen → zum Ziel-Tab-Arranger draggen → Drop

## 🆕 Neu in v0.0.20.81 — Device-Drop "Insert at Position"
- **Insert at Position:** Beim Droppen von Note-FX / Audio-FX Devices wird jetzt an der Cursor-Position eingefügt (nicht mehr immer am Ende)
  - Vertikale cyan-farbige Linie zeigt die Einfügeposition in Echtzeit während des Drags
  - Center-basierte Detektion: links von der Card-Mitte → vor der Card, rechts → dahinter
  - Funktioniert für beide Zonen (Note-FX links, Audio-FX rechts vom Instrument-Anchor)
  - Indicator verschwindet automatisch beim Verlassen des Panels oder nach dem Drop

## 🆕 Neu in v0.0.20.80 — Instrument Power/Bypass
- **Instrument Power Button:** Jedes Instrument (SF2, Sampler, Drum Machine) hat jetzt einen Power-Button in der Device-Card
  - **OFF (Bypass):** Kein MIDI-Dispatch, kein SF2-Render, kein Pull-Source Audio → CPU-sparend
  - **ON:** Normales Verhalten (default)
  - Track bleibt sichtbar; FX Chain bleibt intakt
  - Zustand wird im Projekt gespeichert (`Track.instrument_enabled`)
  - Unterschied zu Track-Mute: Bypass verhindert Audio-Erzeugung komplett

## 🆕 Neu in v0.0.20.79 — Ghost-Clip Feedback + Dirty-Indicator Dot
- **Ghost-Clip Preview:** Beim Drag über den Arranger Canvas (Cross-Project, Audio-Drop, MIDI-Drop) erscheint ein halbtransparenter Clip-Preview an der Cursor-Position
  - Farbcodiert: Blau (Cross-Project), Grün (MIDI), Amber (Audio)
  - Snapped an Grid + Track-Lane, zeigt Label (z.B. "↗ 2 Tracks", "🔊 drums.wav")
- **Dirty-Indicator Dot:** Ungespeicherte Tabs zeigen jetzt einen orangefarbigen Punkt als Icon statt des "• " Text-Prefix — funktioniert auch bei eingeklappten Tab-Titeln

## 🆕 Neu in v0.0.20.78 — Multi-Project Tabs Polish
- **Cross-Project Drag im Arranger:** Tracks/Clips aus anderem Tab direkt auf den Arranger-Canvas droppen
- **Tab-Reorder:** Tabs per Drag&Drop in der Tab-Leiste umsortieren
- **Tab-Navigation:** **Ctrl+Tab** = nächster Tab, **Ctrl+Shift+Tab** = vorheriger Tab (wrapping)

## 🆕 Neu in v0.0.20.77 — Multi-Project Tabs (Bitwig-Style)
- **Multi-Project Tabs:** Mehrere Projekte gleichzeitig in Tabs offen (wie in Bitwig Studio)
  - Tab-Bar am oberen Rand: `+` für neues Projekt, `📂` zum Öffnen
  - **Ctrl+T** = Neuer Tab, **Ctrl+Shift+O** = Öffnen in neuem Tab, **Ctrl+W** = Tab schließen
  - Nur das aktive Projekt nutzt die Audio-Engine (ressourcenschonend)
- **Cross-Project Track-Copy:** Tracks mit Device-Chains, Clips, MIDI-Notes zwischen Tabs kopieren
- **Projekt-Browser:** "Projekte" Tab im Browser zeigt .pydaw.json Dateien, Peek-Vorschau per Klick
- **Full State Transfer:** Beim Kopieren bleiben Effekte, Automationen, Routing erhalten

## 🆕 Neu in v0.0.20.72
- **Hotfix:** Keine PyQt6 SIGABRT Crashes mehr bei Drag&Drop / QAction ("Unhandled Python exception")
  - Defensive try/except in Qt Overrides (dropEvent/dragEnterEvent)
  - Actions/Transport-Signale laufen über `_safe_call()`

## 📦 WAS IST IN DIESER ZIP?


```
Py_DAW_v0_0_20_72_TEAM_READY/
├── README_TEAM.md                    # ← DIESE DATEI
├── BRIEF_AN_KOLLEGEN.md              # Kurzüberblick
├── main.py                           # Start-File
├── pydaw/                            # Source Code
├── VERSION                            # Aktuelle Version
├── PROJECT_DOCS/                     # ★ ARBEITSVERZEICHNIS
│   ├── README.md                     # Schnellstart
│   ├── plans/MASTER_PLAN.md          # Haupt-Plan
│   ├── progress/TODO.md              # ★ WICHTIG: Was zu tun
│   ├── progress/DONE.md              # Was fertig ist
│   └── sessions/                     # Session-Logs
└── INSTALL.md                        # Installation
```

---

## ⚡ SCHNELLSTART (5 Minuten)

### Schritt 1: Entpacken
```bash
unzip Py_DAW_v0_0_20_72_TEAM_READY.zip
cd Py_DAW_v0_0_20_72_TEAM_READY
```

### Schritt 2: Lies Arbeitsmappe
```bash
# Im Programm-Menü: Hilfe → Arbeitsmappe
# ODER manuell:
cat PROJECT_DOCS/README.md           # Schnellstart
cat PROJECT_DOCS/plans/MASTER_PLAN.md # Übersicht
cat PROJECT_DOCS/progress/TODO.md     # ★ Was zu tun ist
```

### Schritt 3: Letzter Stand
```bash
# Lies neueste Session:
ls -t PROJECT_DOCS/sessions/ | head -1
cat PROJECT_DOCS/sessions/2026-*_SESSION_*.md
```

### Schritt 4: Task auswählen
```bash
# Öffne TODO.md
nano PROJECT_DOCS/progress/TODO.md

# Suche Task mit: [ ] AVAILABLE
# Markiere: [x] (Dein Name, 2026-01-31 08:00)
```

### Schritt 5: Session starten
```bash
# Erstelle Session-Log
DATE=$(date +%Y-%m-%d)
touch PROJECT_DOCS/sessions/${DATE}_SESSION_X.md

# Arbeite am Task
# Dokumentiere Fortschritt
```

---

## 📋 ARBEITSABLAUF (WICHTIG!)

### 🔄 Der Workflow - JEDER macht das:

```
1. ZIP empfangen
   ↓
2. Entpacken
   ↓
3. PROJECT_DOCS/progress/TODO.md öffnen
   ↓
4. Task mit [ ] AVAILABLE auswählen
   ↓
5. Task markieren: [x] (Name, Datum)
   ↓
6. Session-Log erstellen
   ↓
7. Code schreiben + dokumentieren
   ↓
8. TODO.md updaten (Task als DONE)
   ↓
9. DONE.md updaten (Task eintragen)
   ↓
10. Session-Log vervollständigen
    ↓
11. VERSION erhöhen (z.B. v0.0.19.7.38 → v0.0.19.7.39)
    ↓
12. Neue ZIP erstellen
    ↓
13. An nächsten Kollegen übergeben
```

---

## 🎯 BEISPIEL-SESSION

### Du bist Kollege #2:

**1. ZIP empfangen**
```bash
unzip Py_DAW_v0_0_20_72_TEAM_READY.zip

```

**2. Letzten Stand prüfen**
```bash
# Was wurde zuletzt gemacht?
cat PROJECT_DOCS/sessions/LATEST.md

# Was ist zu tun?
cat PROJECT_DOCS/progress/TODO.md
```

**3. Task auswählen**
```
Du siehst in TODO.md:

### Task 1: Daten-Model erweitern
**Assignee:** [ ] AVAILABLE   ← DAS nimmst du!
**Aufwand:** 1h
```

**4. Task markieren**
```markdown
# In TODO.md ändern:
### Task 1: Daten-Model erweitern
**Assignee:** [x] (Max, 2026-01-31 08:00)  ← DEIN NAME!
**Status:** 🚧 IN ARBEIT
```

**5. Session-Log erstellen**
```bash
touch PROJECT_DOCS/sessions/$(date +%F)_SESSION_X.md
```

```markdown
# 📝 SESSION LOG: 2026-01-31 (Session 2)

**Entwickler:** Max
**Zeit:** 08:00 - 09:00
**Task:** Task 1 - Daten-Model erweitern

## ERLEDIGTE TASKS
- [x] MidiNote-Klasse um accidental erweitert
- [x] to_staff_position() implementiert
- [x] Tests geschrieben

## PROBLEME
- Keine

## NÄCHSTE SCHRITTE
- Task 2: Staff-Renderer

## CODE-ÄNDERUNGEN
**Geändert:**
- pydaw/model/midi.py (+50 Zeilen)

**Neu:**
- tests/test_midi_conversion.py

## ZEITPROTOKOLL
08:00-08:30 - Klasse erweitern
08:30-09:00 - Tests schreiben
```

**6. Nach Fertigstellung**

**TODO.md updaten:**
```markdown
### Task 1: Daten-Model erweitern
**Assignee:** [x] (Max, 2026-01-31 08:00) ✅ DONE
**Status:** ✅ FERTIG
```

**DONE.md updaten:**
```markdown
#### 2026-01-31 09:00 - Daten-Model erweitert
**Task:** Task 1 - MidiNote erweitern
**Developer:** Max
**Dauer:** 1h

**Was gemacht:**
- [x] accidental Field hinzugefügt
- [x] to_staff_position() implementiert
- [x] Unit-Tests geschrieben

**Files:** pydaw/model/midi.py, tests/test_midi_conversion.py
**Erfolg:** ✅ Tests laufen durch
```

**7. Version erhöhen**
```bash
echo "0.0.19.3.7.14" > VERSION
```

**8. Neue ZIP erstellen**
```bash
cd ..
zip -r Py_DAW_v0_0_20_72_TEAM_READY.zip Py_DAW_v0_0_20_72_TEAM_READY/
```

**9. An Kollege #3 übergeben**
```
Sage zu Kollege #3:

"Hier ist v0.0.19.3.7.4!
Ich habe Task 1 erledigt (Daten-Model).
Als nächstes kommt Task 2 (Staff-Renderer).
Siehe TODO.md!"
```

---

## 📊 ARBEITSMAPPE IM PROGRAMM

### Im PyDAW Programm:
```
Menü → Hilfe → Arbeitsmappe
```

**Zeigt an:**
- ✅ Aktueller Stand (TODO/DONE)
- ✅ Letztes Session-Log
- ✅ Nächste Tasks
- ✅ Team-Übersicht

**Code:** `pydaw/ui/workbook_dialog.py`

---

## 🎯 WICHTIGE REGELN

### ✅ DOs (IMMER machen):

1. **TODO.md lesen** vor Start
2. **Task markieren** mit deinem Namen
3. **Session-Log schreiben** während Arbeit
4. **TODO.md + DONE.md updaten** nach Task
5. **VERSION erhöhen** vor ZIP
6. **Neue ZIP erstellen** für nächsten Kollegen

### ❌ DON'Ts (NIEMALS machen):

1. ❌ Task starten OHNE in TODO.md zu markieren
2. ❌ Code ändern OHNE zu dokumentieren
3. ❌ ZIP weitergeben OHNE TODO/DONE Update
4. ❌ VERSION vergessen zu erhöhen
5. ❌ Session-Log weglassen

---

## 🐛 PROBLEME MELDEN

### Problem während Arbeit:

**In Session-Log:**
```markdown
## PROBLEME & LÖSUNGEN

### Problem 1: Import-Error
**Symptom:** ModuleNotFoundError: pydaw.notation
**Ursache:** Pfad falsch
**Lösung:** sys.path.append() hinzugefügt
**Status:** ✅ FIXED

### Problem 2: Performance-Issue
**Symptom:** Notation-Rendering langsam (>1s)
**Lösung:** Noch offen
**Status:** ⚠️ TODO für nächsten Kollegen
```

**In TODO.md:**
```markdown
### Task X: Performance-Problem fixen
**Assignee:** [ ] AVAILABLE
**Priority:** HIGH
**Blocker:** Ja (blockt Task Y)
```

---

## 📚 WICHTIGE DATEIEN

### ★★★ Must-Read:
1. `PROJECT_DOCS/README.md` - Schnellstart
2. `PROJECT_DOCS/progress/TODO.md` - Was zu tun
3. `PROJECT_DOCS/sessions/LATEST.md` - Letzter Stand

### ★★ Should-Read:
4. `PROJECT_DOCS/plans/MASTER_PLAN.md` - Gesamt-Übersicht
5. `PROJECT_DOCS/plans/FX_CHAINS.md` - Note-FX + Audio-FX (wo/wie erweitern)
6. `PROJECT_DOCS/progress/DONE.md` - Was fertig

### ★ Nice-to-Read:
7. `PROJECT_DOCS/plans/ARCHITECTURE.md` - System-Architektur
8. Alle Session-Logs - Historie

---

## 🎓 CHECKLISTE FÜR ÜBERGABE

### Bevor du ZIP an Kollegen gibst:

- [ ] TODO.md updated (Task als DONE)
- [ ] DONE.md updated (Task eingetragen)
- [ ] Session-Log komplett
- [ ] VERSION erhöht
- [ ] Neue ZIP erstellt
- [ ] README_TEAM.md aktuell
- [ ] Code getestet
- [ ] Keine Syntax-Errors

---

## 💬 AN DEN NÄCHSTEN KOLLEGEN

### Übergabe-Text (Beispiel):

```
Hi [Name],

hier ist PyDAW v0.0.19.3.7.4!

✅ Erledigt: Task 1 (Daten-Model erweitern)
⏳ Nächster: Task 2 (Staff-Renderer, ~2h)

Siehe:
- PROJECT_DOCS/progress/TODO.md (Task-Liste)
- PROJECT_DOCS/sessions/LATEST.md (Letzter Stand)

Viel Erfolg!
- Max
```

---

## 🚀 PROGRAMM STARTEN

### Installation:
```bash
# Python 3.10+
python3 --version

# Virtual Env
python3 -m venv myenv
source myenv/bin/activate

# Dependencies
pip install -r requirements.txt

# JACK/PipeWire
# (System-abhängig, siehe INSTALL.md)
```

### Starten:
```bash
source myenv/bin/activate
python3 main.py
```

### Arbeitsmappe öffnen:
```
Im Programm: Menü → Hilfe → Arbeitsmappe
```

---

## 🎯 VERSIONS-SCHEMA

```
v0.0.19.3.7.4
     │  │ │ │
     │  │ │ └─ Patch (Task-Increment)
     │  │ └─── Minor (Feature-Increment)
     │  └───── Major-Minor
     └──────── Major

Nach jedem Task: +1 am Ende
Nach Feature: Erhöhe vorletzte Stelle
```

**Beispiel:**
- Task 2 fertig: v0.0.19.3.7.4 → v0.0.19.3.7.5
- Task 3 fertig: v0.0.19.3.7.5 → v0.0.19.3.7.6
- Feature fertig (v0.0.20.0 MVP): v0.0.19.3.7.X → v0.0.20.0.0

---

## ✅ ZUSAMMENFASSUNG

**Du als Kollege:**
1. ✅ ZIP entpacken
2. ✅ TODO.md lesen
3. ✅ Task nehmen + markieren
4. ✅ Session-Log erstellen
5. ✅ Code schreiben + dokumentieren
6. ✅ TODO/DONE updaten
7. ✅ VERSION erhöhen
8. ✅ Neue ZIP erstellen
9. ✅ An nächsten übergeben

**Das Ergebnis:**
🎯 **Eine professionelle DAW - UNSERE EIGENE!**

---

**Viel Erfolg! 🚀**

**Bei Fragen:** Siehe PROJECT_DOCS/ oder frag vorherigen Kollegen

## 🎼 Notation: Professionelle Eingabe-Palette (MVP)

- Im Notation-Tab gibt es jetzt eine Eingabe-Palette: Notenwerte 1/1..1/64, Punktierung, Rest-Mode, Vorzeichen (b/♮/#) und Ornament-Marker (tr).
- **Editor-Notes (Sticky Notes):** Über den 🗒 Button oder `Ctrl + Rechtsklick` im Notationsfeld → 'Editor-Notiz hinzufügen'.
- Markierungen werden im Projekt gespeichert: `Project.notation_marks`.

