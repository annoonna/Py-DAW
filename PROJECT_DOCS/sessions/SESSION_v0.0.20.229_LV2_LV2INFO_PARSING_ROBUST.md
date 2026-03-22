# SESSION v0.0.20.229 — LV2: lv2info Parsing robust (2026-03-04)

## Problem (User)
- `python3-lilv` ist installiert.
- `lv2info <URI>` liefert Plugin-Infos, aber Py_DAW zeigt im LV2 Device weiterhin **keine Parameter** (nur leerer Bereich).
- `lv2info` gab zusätzlich Warnungen/Errors über **fremde kaputte LV2 Bundles** aus (missing manifest.ttl).

## Root Cause
1) `lv2info` kann bei solchen Warnungen mit **ExitCode != 0** enden, obwohl die Ausgabe für das gewünschte Plugin korrekt ist.
   Unser Fallback nutzte `subprocess.check_output()` → Exception → **keine Controls**.
2) Das Feld **Type:** in `lv2info` ist oft **mehrzeilig**:
   - Zeile 1 enthält z.B. `...#ControlPort`
   - Zeile 2 enthält z.B. `...#InputPort`
   Unser Parsing prüfte nur die erste Zeile → Input-Control Ports wurden fälschlich verworfen.

## Ziel (safe)
- **Nichts kaputt machen.**
- LV2 Parameter-UI soll auch dann zuverlässig erscheinen, wenn:
  - `lv2info` Warnungen ausgibt,
  - `lv2info` non-zero zurückgibt,
  - `Type:` wrapped/multiline ist.

## Änderungen
✅ `pydaw/audio/lv2_host.py`
- `_describe_controls_via_lv2info()`:
  - nutzt jetzt `subprocess.run(..., check=False, capture_output=True)` und parst Output trotz non-zero Exit.
  - kombiniert stdout/stderr (damit auch bei stderr-Warnungen genug Kontext vorhanden ist).
  - liest den gesamten **Type-Block** inkl. Folgezeilen → erkennt `ControlPort` + `InputPort` korrekt.

## Ergebnis
- UI-only Fallback (ohne python-lilv) baut die Control-Parameterliste jetzt stabil auf.
- `lv2info` Warnungen über kaputte Bundles verhindern die Param-UI nicht mehr.

## Files
- `pydaw/audio/lv2_host.py`
- `VERSION`, `pydaw/version.py`
