# SESSION v0.0.20.243 — LV2 Scanner Subprocess-Sturm Fix

**Datum:** 2026-03-05  
**Bearbeiter:** Claude Opus (Anthropic)  
**Priorität:** 🔴 CRITICAL (App startet nicht)

## Ausgangslage
User Report: PyDAW bleibt beim Start hängen, Terminal spammt hunderte `Detaching after vfork...` Meldungen.

## Root Cause
Die Funktion `_resolve_bundle_via_lv2info()` (Fallback für „Bundle ohne erkennbare URI“) hat pro Bundle mehrere Subprozesse gestartet:
- `lv2ls` / `lv2info` pro Bundle bzw. Kandidat
→ Bei vielen LV2 Bundles entsteht ein **Subprocess-Sturm** (300–500+) und der Start blockiert.

## Fix (SAFE)
- `lv2ls` wird **einmal** ausgeführt und **modulweit gecacht**.
- URI-Auflösung erfolgt per **String-Heuristik** (ohne `lv2info`).
- Ergebnis: **0 weitere Subprozesse** beim Bundle-Fallback.

## Geänderte Dateien
- `pydaw/services/plugin_scanner.py`
- `CHANGELOG_v0.0.20.243_SCANNER_SUBPROCESS_FIX.md`
- `VERSION`, `pydaw/version.py`

## Testplan
1) Start mit vielen LV2 Bundles → keine `[Detaching after vfork...]` Flut mehr.
2) Plugins-Browser Rescan → LV2 Liste bleibt schnell.

