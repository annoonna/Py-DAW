# CHANGELOG v0.0.20.663 — Responsive UI + Bug-Fix

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** UI-Hotfix (letzte offene ROADMAP-Checkbox) + Bug-Fix

## Was wurde gemacht

### 1. Bug-Fix: SCALES Import in scale_ai.py
- `pydaw/notation/ai/scale_ai.py` importierte `SCALES` aus `database.py`, aber dieses Symbol existierte nicht
- Fix: Import auf `SCALE_DB.all_scales()` umgestellt, Rückgabe ist jetzt `(system, name)` Tupel
- Backward-Compat-Alias `SCALES = SCALE_DB.scales` in `database.py` ergänzt

### 2. Responsive Verdichtung für schmale Fensterbreiten (ROADMAP-Checkbox)
- **TransportPanel** (`transport.py`): 2-Tier `resizeEvent`
  - Tier 1 (<700px): Pre-Roll, Post-Roll, Count-In Labels + SpinBoxen ausgeblendet
  - Tier 2 (<520px): Punch-Checkbox, TS-Label, TS-ComboBox, Loop-Checkbox, Metro-Checkbox ausgeblendet
- **ToolBarPanel** (`toolbar.py`): 2-Tier `resizeEvent`
  - Tier 1 (<480px): Loop-Range SpinBoxen + Trennlabel ausgeblendet
  - Tier 2 (<350px): Follow-Button + Loop-Checkbox ausgeblendet
- Rein visuell: Keine Signale getrennt, versteckte Widgets behalten ihre Werte
- Play/Stop/Rec/BPM bleiben bei jeder Breite sichtbar

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| pydaw/ui/transport.py | `_responsive_tier1/tier2` Listen, `resizeEvent()` mit 2-Tier Logik |
| pydaw/ui/toolbar.py | `_responsive_tier1/tier2` Listen, `resizeEvent()` erweitert um Responsive-Logik |
| pydaw/notation/ai/scale_ai.py | Import-Fix: `SCALE_DB.all_scales()` statt `SCALES` |
| pydaw/notation/scales/database.py | `SCALES` Backward-Compat-Alias hinzugefügt |
| pydaw/version.py | 662 → 663 |
| VERSION | 662 → 663 |
| PROJECT_DOCS/ROADMAP_MASTER_PLAN.md | Letzte Checkbox abgehakt, Version-Stamp aktualisiert |

## Was als nächstes zu tun ist
- **Alle 10 Arbeitspakete (AP1–AP10) sind KOMPLETT** — alle ROADMAP-Checkboxen [x]
- Verbleibende optionale Arbeit aus TODO.md (ältere AVAILABLE-Einträge):
  - Rust Binary kompilieren + Integrations-Test (`cargo build --release`)
  - AETERNA-Feinpolish (Unison/Sub/Noise UX, Mod-Rack-Visualisierung)
  - SmartDrop nächste Schritte (Runtime-State-Registries)
- Integration Test Suite für CI/CD aufsetzen

## Bekannte Probleme / Offene Fragen
- 9 Module benötigen optionale Dependencies (`fluidsynth`, `pythonosc`) — kein Fehler, erwartetes Verhalten
- Alle 287 .py Dateien kompilieren fehlerfrei
- Alle 251 importierbaren Module (ohne optionale Deps) importieren korrekt
