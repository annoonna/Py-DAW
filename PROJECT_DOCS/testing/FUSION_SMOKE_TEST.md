# Fusion Smoke Test (v0.0.20.582)

Ziel: die letzten Fusion-Hotfixes reproduzierbar pruefen, bevor neue Features wie LFO/Unison/FX dazukommen.

## 1) Automatischer Offscreen-Test

Im Projektordner:

```bash
QT_QPA_PLATFORM=offscreen python3 pydaw/tools/fusion_smoke_test.py
```

Der Test deckt ab:
- queued MIDI-CC Updates landen wirklich im gespeicherten State-Snapshot
- Scrawl Save/Load Roundtrip (`scrawl_points`, `scrawl_smooth`, Knob-Werte)
- Wavetable-Pfad + Wavetable-Knobs werden gespeichert und restauriert
- OSC/FLT/ENV Modulwechsel laufen einmal komplett durch

Erwartung:
- Exit-Code `0`
- Ausgabe enthaelt `[OK] Fusion smoke test passed`

## 2) Manueller UI/MIDI Test

### A. MIDI-CC / GUI-Fluessigkeit
- Fusion auf eine Instrument-Spur legen
- Rechtsklick auf 2-3 Knobs → MIDI Learn
- Hardware-Controller schnell drehen
- dabei mehrfach OSC / Filter / Env wechseln

Erwartung:
- kein Freeze / kein `main.py antwortet nicht`
- Knobs bleiben bedienbar
- Modulwechsel fuehren nicht zu haengenden Alt-Mappings

### B. Scrawl Recall
- OSC auf `Scrawl`
- eigene Welle zeichnen
- Projekt speichern
- DAW komplett schliessen
- Projekt neu laden

Erwartung:
- gleiche Welle erscheint wieder
- Smooth-Status bleibt gleich
- relevante Fusion-Knobs kommen identisch zurueck

### C. Wavetable Recall
- OSC auf `Wavetable`
- `.wt` oder `.wav` laden
- `Index`, `Uni Mode`, `Uni Vox`, `Uni Sprd` veraendern
- Projekt speichern, neu laden

Erwartung:
- geladene Wavetable bleibt referenziert
- Wavetable-Knobs kommen identisch zurueck

## 3) Nächster sinnvoller Schritt nach bestandenem Smoke-Test

- Fusion: LFO Modulation
- danach: Unison/Detune auf Engine-Ebene
- danach: Effects Section (Delay/Reverb/Chorus)
