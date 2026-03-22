# v0.0.20.473 — Plugins Browser Scope-Badge + Rollen-Metadaten

## Was wurde gemacht?

- `pydaw/ui/plugins_browser.py` zeigt jetzt ebenfalls eine **Scope-Badge** im Header an.
- Die Badge reagiert auf die erkannte Plugin-Rolle:
  - **Instrument** → Badge/Tooltip nutzt den Instrument-Kontext der aktiven Spur
  - **Effekt** → Badge/Tooltip nutzt den Audio-FX-Kontext der aktiven Spur
- Externe Plugin-Payloads für **Add** und **Drag&Drop** tragen jetzt zusätzlich:
  - `device_kind`
  - `params["__ext_is_instrument"]`
- Der bestehende sichere Insert-Pfad bleibt bewusst gleich: Plugins-Browser nutzt weiterhin den bekannten Add-/Drop-Weg.

## Warum ist das wichtig?

Das ist der kleinste sichere Vorbereitungsschritt für den späteren **SmartDropHandler** aus dem Rundschreiben:
- Targets müssen künftig nicht mehr nur raten, ob ein externes Plugin Instrument oder Effekt ist.
- Die aktive Spur wird im Plugins-Browser jetzt sichtbarer als Ziel kommuniziert.
- Kein Risiko für Audio-Engine, Routing oder Projektformat.

## Betroffene Dateien

- `pydaw/ui/plugins_browser.py`
- `pydaw/ui/device_browser.py`

## Validierung

```bash
python -m py_compile pydaw/ui/plugins_browser.py pydaw/ui/device_browser.py
```
