# 📌 Session Log — 2026-02-07 — MIDI Panic Action Fix (v0.0.20.2)

## Problem
Start-Crash beim App-Start:

`TypeError: AppActions.__init__() missing 1 required positional argument: 'midi_panic'`

Ursache: `AppActions` Dataclass enthält das Feld `midi_panic`, aber `build_actions()` hat es nicht an den Konstruktor übergeben.

## Fix
- `pydaw/ui/actions.py`: `midi_panic=a_midi_panic` im `return AppActions(...)` ergänzt.
- `pydaw/version.py`: Version auf **0.0.20.2** erhöht (Hotfix).

## Test-Hinweis
Wenn JACK nicht erreichbar ist (nur Warning), starte wie empfohlen mit:
- `pw-jack python3 main.py`

## Ergebnis
App startet wieder durch (kein init-crash mehr an `AppActions`).
