# CHANGELOG v0.0.20.540 — Instrument-Layer Phase 3: Velocity-Split / Key-Range

**Datum:** 2026-03-17
**Entwickler:** Claude Opus 4.6
**Typ:** Feature (Phase 3 — Instrument-Layer komplett)

---

## Velocity-Split + Key-Range

Jeder Layer kann jetzt einschränken welche MIDI-Noten er empfängt:

### Velocity-Split
- **Vel Min / Vel Max** (0-127) — nur Noten mit Velocity in diesem Bereich
- Beispiel: Layer 1 = 0-64 (leise), Layer 2 = 65-127 (laut)

### Key-Range  
- **Key Min / Key Max** (0-127) — nur Noten in diesem Tastenbereich
- Beispiel: Layer 1 = 0-59 (Bass), Layer 2 = 60-127 (Treble)
- Tooltips zeigen Notennamen: C-2 bis G8

### Technische Details
- Dispatcher filtert `note_on()` pro Layer — Noten außerhalb werden ignoriert
- `note_off()` geht immer an alle Layer (keine Stuck Notes)
- Default: Full Range (0-127 für beides) — keine Änderung wenn nicht gesetzt
- Ranges werden in Projekt-JSON persistiert

## Geänderte Dateien
- `pydaw/audio/audio_engine.py` — Dispatcher + Range-Extraktion
- `pydaw/ui/fx_device_widgets.py` — UI-Controls + Handler + Hilfsfunktion

## Nichts kaputt gemacht ✅
- Bestehende Instrument-Engines unverändert
- MIDI-Routing unverändert (additive Filterung)
- Projekt-Format abwärtskompatibel (fehlende Ranges = Full Range)
