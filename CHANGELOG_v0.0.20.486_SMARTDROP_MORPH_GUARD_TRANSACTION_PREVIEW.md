# v0.0.20.486 — SmartDrop Morph Guard Transaction Preview

## Was wurde gemacht?

- Der zentrale Morphing-Guard-Plan in `pydaw/services/smartdrop_morph_guard.py` liefert jetzt zusaetzlich:
  - `required_snapshots`
  - `transaction_steps`
  - `transaction_key`
  - `transaction_summary`
- Der bestehende Guard-Dialog in `pydaw/ui/main_window.py` zeigt diese Struktur jetzt zusaetzlich als:
  - `Noetige Snapshots`
  - `Geplanter atomarer Ablauf`
  - `Transaction-Key`

## Warum ist das sinnvoll?

Damit die spaetere echte Audio->Instrument-Morphing-Apply-Phase bereits auf einer klaren atomaren Vorschau aufbauen kann, ohne heute schon Routing, Undo oder Projektzustand zu veraendern.

## Safety

- weiterhin **kein** echtes Audio->Instrument-Morphing
- weiterhin **kein** Routing-Umbau
- weiterhin **keine** Projektmutation

## Validierung

```bash
python -m py_compile pydaw/services/smartdrop_morph_guard.py pydaw/ui/main_window.py
```
