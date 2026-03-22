# SESSION v0.0.20.228 — LV2: robust lilv import + lv2info UI fallback (2026-03-04)

## Problem (User)
- LV2 Plugin im Device-Rack zeigt nur Hinweis-Text (keine Parameter/GUI),
  obwohl `python3-lilv` + `lilv-utils` installiert wurden.
- Ursache ist meist: **python-lilv kann im venv nicht importiert werden**
  (kein `--system-site-packages` oder Python-Version-Mismatch).

## Ziel (safe)
- **Nichts kaputt machen.**
- LV2 Device soll **nicht mehr „leer“ wirken**:
  - Klarer Diagnose-Text (inkl. ImportError Kurzinfo)
  - Parameterliste kann **UI-only** über `lv2info` aufgebaut werden (wenn vorhanden)
- Plugins-Browser Status nach „Add to Device“ soll korrekt anzeigen,
  ob LV2 live aktiv ist oder nur Placeholder/No-op.

## Änderungen
✅ `pydaw/audio/lv2_host.py`
- Import-Robustheit:
  - nutzt `site.addsitedir()` für dist-packages (inkl. .pth Verarbeitung)
  - merkt sich `_LILV_IMPORT_ERROR` für UI-Diagnose
- `availability_hint()` zeigt jetzt:
  - ImportError (kurz)
  - konkrete Fixes (apt + venv `--system-site-packages`)
- UI-Fallback: `describe_controls()` versucht bei fehlendem python-lilv
  **`lv2info <URI>`** zu parsen (nur Control-Input Ports) → Parameter UI möglich.

✅ `pydaw/ui/fx_device_widgets.py`
- LV2 Widget baut Parameter-UI jetzt **auch ohne python-lilv**,
  sofern `lv2info` Controls liefern kann.
- Hinweistext bleibt sichtbar, wenn live processing deaktiviert ist.

✅ `pydaw/ui/plugins_browser.py`
- Nach „Add to Device“ Status:
  - LV2: „live OK“ oder „no-op (python-lilv fehlt)“
  - andere Typen: weiterhin Placeholder (Hosting später)

## Hinweise
- Das ist **keine native Plugin-GUI-Einbettung** (GTK/Qt UI),
  sondern generische Control-Port Liste (Bitwig/Ableton-style MVP).
- Live-Audio-Processing via LV2 benötigt weiterhin python-lilv.
  Wenn ImportError „Python-Version mismatch“ zeigt: venv mit System-Python erstellen.

## Files
- `pydaw/audio/lv2_host.py`
- `pydaw/ui/fx_device_widgets.py`
- `pydaw/ui/plugins_browser.py`
- `VERSION`, `pydaw/version.py`
