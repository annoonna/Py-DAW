# CHANGELOG v0.0.20.240 — LV2 Unconnected Ports Fix

**Datum:** 2026-03-05
**Bearbeiter:** Claude Opus (Anthropic)
**Priorität:** 🔴 CRITICAL

## Problem
LV2 Audio-Effekte (Reverb, Delay, Wah, etc.) zeigen "DSP: ACTIVE" mit korrekten
Parameter-Werten in der UI, aber produzieren **keinen hörbaren Effekt**. Distortion
funktioniert. SWH-Plugins zeigen "attempt to map invalid URI" → BLOCKED.

## Ursachen & Fixes

### 1. CRITICAL: Unconnected Output-Control-Ports
**Ursache:** LV2 spec fordert: alle non-optional Ports MÜSSEN verbunden sein.
Output-Control-Ports (Latenz, Meter, Level) waren NICHT verbunden → Plugin's
`run()` schreibt in NULL → undefined behavior → kein Audio-Output.

**Fix:** `pydaw/audio/lv2_host.py` — Nach Audio + Control-Input Verbindung:
alle restlichen Ports bekommen Dummy-Buffer (np.zeros). Gehalten in
`self._dummy_bufs` (kein GC). Debug-Logging auf stderr.

### 2. get_port_ranges_float() API falsch
**Ursache:** Code rief `plugin.get_port_ranges_float(port)` auf — die lilv
Python API nimmt KEIN port-Argument. Gibt 3 Arrays zurück (mins, maxs, defaults).
Der falsche Call schlug fehl → Exception → Defaults 0.0/1.0/0.0 statt
Plugin-Defaults. Reverb Dry/Wet Default könnte 0.5 sein, wurde aber 0.0.

**Fix:** Korrekte Array-basierte API in `controls_for_uri()` und in `Lv2Fx.__init__`.

### 3. SWH Plugin Scanner
**Ursache:** Manifest.ttl Regex matched nicht alle TTL-Formate → Scanner speichert
Bundle-Pfad statt URI → lilv kann nicht laden.

**Fix:** 3 zusätzliche Regex-Patterns + lv2info CLI-Fallback.

## Geänderte Dateien
- `pydaw/audio/lv2_host.py`
- `pydaw/services/plugin_scanner.py`
- `VERSION` (→ 0.0.20.240)
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/sessions/SESSION_v0.0.20.240_UNCONNECTED_PORTS_FIX_2026-03-05.md`

## Test
1. LV2 Reverb laden → muss jetzt hörbar sein
2. Konsole: `[LV2] ... dummy=N` zeigt wie viele Dummy-Ports verbunden wurden
3. SWH-Plugins: Rescan → URIs statt Pfade
4. Keine Crashes (oberste Direktive: NICHTS KAPUTT MACHEN)
