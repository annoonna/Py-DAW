# CHANGELOG v0.0.20.666 — Critical: GUI Freeze + Silent Playback Fix

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Kritischer Hotfix — Performance + Stabilität

## Problem

Nach Aktivierung von "Alle → Rust" im Engine Migration Dialog:
1. **Kein Sound** — Rust Engine kann nur Sine-PoC rendern, keine Python-Instrumente
2. **GUI friert ein** — RustEngineBridge flutet GUI mit "deleted C++ object" Fehlern
3. **ALSA Underrun-Flut** — Endlose `snd_pcm_recover underrun occurred` im Terminal
4. **Stop/Play unbenutzbar** — Fenster "main.py antwortet nicht"
5. **Persists nach Neustart** — QSettings hatte "Rust" als Default gespeichert

## Root Cause

Die Rust Audio Engine (Phase 1A/1B) ist ein **Proof-of-Concept** mit Sine-Generator.
Sie kann KEINE Python-Instrumente rendern (Advanced Sampler, AETERNA, DrumMachine, SF2).
Wenn `should_use_rust("audio_playback")` → True zurückgibt, delegiert AudioEngine
an Rust, aber Rust liefert nur Stille → ALSA Underruns → Error-Flood → GUI-Freeze.

## Fix (3 Ebenen)

### 1. Safety Gate: `should_use_rust()` → immer `False` (engine_migration.py)
- Bis Rust vollständiges Instrument-Rendering kann, gibt `should_use_rust()` IMMER `False` zurück
- Python-Engine bleibt der einzige aktive Audio-Pfad
- Migration-Dialog funktioniert weiterhin für Konfiguration/Benchmarking, aber Audio läuft über Python

### 2. Error-Flood-Schutz (rust_engine_bridge.py)
- Neues `_shutting_down` Flag — wird bei shutdown() SOFORT gesetzt
- `_dispatch_event()` prüft Flag VOR jedem Signal-Emit
- `RuntimeError("deleted")` wird gefangen → Flag gesetzt → Reader-Loop stoppt sofort
- Keine endlose Error-Schleife mehr die den GUI-Thread blockiert

### 3. Graceful Disconnect (rust_engine_bridge.py)
- `_shutting_down` wird vor Socket-Close gesetzt
- Reader-Thread prüft Flag und bricht sauber ab
- Kein Error-Logging nach gewolltem Disconnect

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| pydaw/services/engine_migration.py | `should_use_rust()` → Safety Gate, immer `False` |
| pydaw/services/rust_engine_bridge.py | `_shutting_down` Flag, RuntimeError Guard, sauberer Shutdown |
| VERSION | 665 → 666 |
| pydaw/version.py | 665 → 666 |

## Was als nächstes zu tun ist
- DAW starten → sollte sofort flüssig laufen (Python Engine)
- Advanced Sampler + Play testen → Sound sollte kommen
- Rust Engine Migration Dialog bleibt für Benchmarking nutzbar

## Bekannte Einschränkungen
- Rust Engine ist PoC — Audio Delegation deaktiviert bis Instrument-Rendering implementiert
- "Alle → Rust" Button setzt QSettings, hat aber keine Auswirkung auf Playback
