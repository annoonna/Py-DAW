# SESSION v0.0.20.230 — LV2: lv2info Type-Continuation Fix (URI ':' safe) + fallback when lilv yields none (2026-03-04)

## Problem (User Report)
- LV2 Device zeigt weiterhin: **„Keine LV2 Controls gefunden …“** obwohl `lv2info <URI>` korrekte Port-Infos ausgibt.
- Ursache war ein Edge-Case im `lv2info` Parsing:
  - `Type:` ist mehrzeilig.
  - Fortsetzungszeilen sind URIs (`http://...`) und enthalten ebenfalls `:`.
  - Unser Parser hat fälschlich **bei jedem ':'** abgebrochen → `InputPort`/`ControlPort` wurden nicht gemeinsam erkannt.

## Fix (SAFE)
1) `lv2info` Type-Block: Stop-Condition geändert:
   - nicht mehr „irgendein ':'“
   - sondern nur noch echte Key-Zeilen nach Muster `Key: <whitespace>`.
   - URIs wie `http://...` werden korrekt als Fortsetzung gelesen.

2) Extra-Safety-Net:
   - Wenn `python-lilv` verfügbar ist, aber `lilv` *trotzdem* keine Controls liefert,
     wird zusätzlich `lv2info` als UI-Fallback versucht.

## Files
- `pydaw/audio/lv2_host.py`
- `VERSION`, `pydaw/version.py`

## Notes
- UI-Fallback bleibt **UI-only** (kein Live-Processing ohne `python-lilv`).
