# SESSION LOG: 2026-03-16 — v0.0.20.519

**Entwickler:** Claude Opus 4.6
**Zeit:** 2026-03-16
**Task:** Mixer Send-Knobs Compact + Automation folgt Device beim Move (Schritt C)

## WAS GEMACHT WURDE

### 1. Mixer Send-Knobs Compact (Bitwig-Style Fix)
- Vorher: 32px Knobs vertikal gestapelt → bei 6 FX-Spuren unbenutzbar
- Jetzt: 22px Knobs in horizontalen Reihen [Label][Knob]
- Gelb = Post-Fader, Blau = Pre-Fader (wie Bitwig)
- Aktive Sends hell, inaktive gedimmt

### 2. Automation folgt Device beim Move (Schritt C)
- `_migrate_automation_for_device_move()` findet alle Automation-Lanes
  deren parameter_id die Quellspur referenziert
- Schreibt sie auf die Zielspur um (neuer trk:{target}: Prefix)
- Volume/Pan bleiben bewusst bei der Spur
- Safe bei Konflikten: kein Ueberschreiben bestehender Ziel-Lanes
- Bei Ctrl+Copy wird Automation NICHT migriert

## GEAENDERTE DATEIEN
- `pydaw/ui/mixer.py` — Send-Knobs kompakt
- `pydaw/ui/main_window.py` — Automation-Migration + 3 Aufrufstellen

## DREIER-PLAN KOMPLETT
- A: Send-FX / Return-Tracks ✅ (v518)
- B: Device-Container → naechste Session
- C: Automation folgt Device ✅ (v519)
