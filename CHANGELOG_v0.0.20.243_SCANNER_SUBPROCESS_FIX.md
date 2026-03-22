# CHANGELOG v0.0.20.243 — LV2 Scanner Subprocess Storm Fix

**Datum:** 2026-03-05
**Bearbeiter:** Claude Opus (Anthropic)
**Priorität:** 🔴 CRITICAL (App startet nicht)

## Problem
PyDAW öffnet sich nicht — bleibt im Terminal hängen mit hunderten
`[Detaching after vfork from child process ...]` Meldungen bis Ctrl+C.

## Ursache
Die in v0.0.20.240 hinzugefügte `_resolve_bundle_via_lv2info()` Funktion
im Plugin-Scanner rief für **jedes nicht-gematchte LV2 Bundle**:
- `lv2ls` (1 Subprocess pro Bundle)  
- `lv2info` (N Subprocesses pro Bundle, für jeden URI-Kandidaten)

Bei 50+ unaufgelösten Bundles auf einem typischen Kali/Debian-System:
**300-500+ Subprozesse** allein beim Startup-Scan.

## Fix
`_resolve_bundle_via_lv2info()` komplett umgeschrieben:
- `lv2ls` wird **EINMAL** aufgerufen und im Modul-Level gecacht
- URI-Matching geschieht rein über **String-Heuristik** (kein `lv2info`)
- **0 weitere Subprozesse** pro Bundle

Vorher: ~300-500 Subprozesse beim Start
Nachher: **1 Subprozess** (`lv2ls`) beim ersten Scan, danach 0

## Geänderte Dateien
- `pydaw/services/plugin_scanner.py` — `_resolve_bundle_via_lv2info()` + Cache
- `VERSION` → 0.0.20.243
- `pydaw/version.py`
