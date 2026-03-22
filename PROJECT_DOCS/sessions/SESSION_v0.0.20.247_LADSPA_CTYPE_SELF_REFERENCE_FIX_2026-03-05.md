# SESSION v0.0.20.247 — LADSPA ctypes Self-Reference Fix

**Datum:** 2026-03-05  
**Bearbeiter:** GPT-5.4 Thinking (OpenAI)  
**Priorität:** 🔴 HIGH (User Report: LADSPA-Widget zeigt roten Importfehler statt Parameter)

## Ausgangslage
Im Device-Panel wurde für LADSPA-Plugins direkt ein roter Fehler angezeigt:

- `LADSPA load error: name 'LADSPA_Descriptor' is not defined`

Dadurch konnte `describe_plugin()` nicht laufen, die Parameter-UI blieb leer, und das LADSPA-Hosting wirkte defekt, obwohl der Browser das Plugin korrekt gefunden und eingefügt hatte.

## Root Cause
`pydaw/audio/ladspa_host.py` definierte `LADSPA_Descriptor` mit `_fields_` direkt **im Klassenkörper**.
Innerhalb dieser `_fields_` wurde aber bereits `ctypes.POINTER(LADSPA_Descriptor)` referenziert (`instantiate`).

Bei Python ist der Klassenname während der Auswertung des Klassenkörpers noch nicht gebunden. Ergebnis: `NameError`.

## Fix (SAFE)
- `LADSPA_Descriptor` zuerst als leere Forward-Declaration angelegt.
- `_fields_` danach außerhalb des Klassenkörpers gesetzt.
- Keine Änderung an Audio-Routing, UI-Layout oder Device-Chain-Logik.
- Zusätzlich Versions-/Projekt-Metadaten auf `0.0.20.247` synchronisiert.

## Geänderte Dateien
- `pydaw/audio/ladspa_host.py`
- `pydaw/model/project.py`
- `pydaw/version.py`
- `VERSION`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/sessions/LATEST.md`
- `PROJECT_DOCS/sessions/SESSION_v0.0.20.247_LADSPA_CTYPE_SELF_REFERENCE_FIX_2026-03-05.md`
- `CHANGELOG_v0.0.20.247_LADSPA_CTYPE_SELF_REFERENCE_FIX.md`

## Test
```bash
python3 - <<'PY'
import importlib
m = importlib.import_module('pydaw.audio.ladspa_host')
print('import_ok', hasattr(m, 'LadspaFx'))
PY
```

Ergebnis: `import_ok True`

## Erwartetes Verhalten nach dem Fix
1. LADSPA-Device im Device-Panel zeigt wieder Parameter statt rotem Importfehler.
2. `Rebuild FX` kann die Chain normal neu aufbauen.
3. Bestehende Projekte mit LADSPA-Devices bleiben kompatibel, weil keine Plugin-ID- oder State-Änderung erfolgt ist.
