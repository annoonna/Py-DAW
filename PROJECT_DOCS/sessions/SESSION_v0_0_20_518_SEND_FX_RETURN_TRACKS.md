# SESSION LOG: 2026-03-16 — v0.0.20.518

**Entwickler:** Claude Opus 4.6
**Zeit:** 2026-03-16
**Task:** Send-FX / Return-Tracks (Bitwig-Style)

## ZUSAMMENFASSUNG

Komplettes Send-FX / Return-Track System wie in Bitwig Studio implementiert.
FX-Spuren empfangen Audio per Send-Knobs von anderen Spuren, verarbeiten es
durch ihre eigene FX-Chain (z.B. Reverb, Delay) und mischen das Ergebnis
in den Master-Bus.

## ARCHITEKTUR

```
Track A (Instrument) ──┬── Post-FX Audio ──→ Vol/Pan ──→ Master
                       │
                       ├── Pre-Fader Send (0-100%) ──→ FX Bus 1
                       └── Post-Fader Send (0-100%) ──→ FX Bus 2

FX Track 1 (Reverb) ←── Send-Summe ──→ Reverb FX ──→ Vol/Pan ──→ Master
FX Track 2 (Delay)  ←── Send-Summe ──→ Delay FX  ──→ Vol/Pan ──→ Master
```

## GEAENDERTE DATEIEN (9 Dateien)

1. `pydaw/model/project.py` — Track.sends Feld + kind="fx"
2. `pydaw/audio/hybrid_engine.py` — Send-Bus RT-Routing
3. `pydaw/audio/audio_engine.py` — Send-Bus-Map Berechnung
4. `pydaw/services/project_service.py` — Send-API + add_track("fx")
5. `pydaw/ui/mixer.py` — Send-Knobs (QDial) + FX Add-Menu
6. `pydaw/ui/arranger.py` — FX-Spur in Add-Track-Menues
7. `pydaw/ui/main_window.py` — FX als Audio-FX-Ziel
8. `pydaw/ui/smartdrop_rules.py` — FX-Spur Label + Kompatibilitaet
9. `pydaw/services/smartdrop_morph_guard.py` — FX-Spur Label

## AUDIO-ENGINE SEND-ROUTING (Reihenfolge im Callback)

1. FX-Bus-Buffer nullen (wie Group-Bus-Buffer)
2. Tracks rendern (FX-Tracks werden uebersprungen)
3. Pre-Fader Sends: nach FX-Chain, vor Vol/Pan → in FX-Bus kopieren
4. Vol/Pan anwenden
5. Post-Fader Sends: nach Vol/Pan → in FX-Bus kopieren
6. Track → Group-Bus oder Master (wie bisher)
7. Group-Bus Processing (wie bisher)
8. FX-Bus Processing: eigene FX-Chain → Vol/Pan → Metering → Master
9. Master FX → Master Vol/Pan → Output

## NICHTS KAPUTT GEMACHT

- Alle bestehenden Audio-Pfade unveraendert
- Group-Bus-Routing unveraendert
- Pull-Sources unveraendert
- Master-FX unveraendert
- Bestehende Projekte ohne sends=[] laden normal (default=[])
