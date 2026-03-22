# Session: v0.0.20.193 — Pro Drum Machine AI‑Generator + Smart‑Assign

## Ziel
- Pro Drum Machine soll eine „AI‑like“ Drum‑Pattern‑Engine bekommen (Genres/Styles wie AI Composer).
- Output muss als MIDI‑Notes sauber im Clip landen (PianoRoll/Notation) und Mapping muss stabil bleiben:
  - C2 Kick (Slot1)
  - C#2 Snare (Slot2)
  - D2 Closed Hat (Slot3)
  - D#2 Open Hat (Slot4)
  - …
- Samples werden manuell geladen, dürfen aber nicht unabsichtlich „falsch gemappt“ werden.

## Änderungen (safe – nichts kaputt)

### 1) Drum‑Generator UI Upgrade (Instrument: Pro Drum Machine)
- **Genre A / Genre B / Mix** (Hybrid‑Slider)
- Kontext, Grid (1/8..1/32), Swing, Density, Intensity
- Bars bis 64
- Genre‑Combos sind **editierbar** → jedes Genre eintippbar

### 2) Neue Engine: `pydaw/music/ai_drummer.py`
- rein algorithmisch (Stochastik + Constraints), keine statischen MIDI‑Files
- deterministic/seeded (reproduzierbar)
- GUI‑safe (pure Python)

### 3) Smart‑Assign Samples (gegen „HiHat spielt Kick“)
- Beim Sample‑Load via Drag&Drop oder "Load" wird anhand Dateiname‑Keywords erkannt,
  ob es z.B. Kick/Snare/Hat/Crash ist.
- Dann wird das Sample **in das passende Pad** geladen.
- Kanonisches MIDI‑Mapping bleibt dadurch stabil.

### 4) Persistenz
- Generator‑Settings werden im Projekt gespeichert:
  - `track.instrument_state['drum_machine']['generator']`
- Beim Laden werden sie zurückgesetzt (QSignalBlocker‑safe).

## Dateien
- `pydaw/plugins/drum_machine/drum_widget.py`
- `pydaw/music/ai_drummer.py`
- `pydaw/version.py`
- `pydaw/model/project.py`

## Test‑Checkliste
1. Instrument "Pro Drum Machine" laden
2. Samples per Drag&Drop laden:
   - Datei enthält "kick" → landet in Slot1
   - Datei enthält "snare" → landet in Slot2
   - Datei enthält "hat" + "open" → landet in Slot4
3. MIDI‑Clip aktiv wählen
4. Generate → Clip
   - Notes erscheinen korrekt in PianoRoll (C2/C#2/D2/D#2…)
   - Groove reagiert auf Genre/Context/Grid/Swing/Density/Intensity

---

Assignee: GPT‑5.2 Thinking (ChatGPT) — 2026‑03‑02
