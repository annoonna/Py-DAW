# CHANGELOG v0.0.20.247 — LADSPA ctypes Self-Reference Fix

## Fix
- Behebt den LADSPA-Importfehler `name 'LADSPA_Descriptor' is not defined`.
- Ursache war eine selbstreferenzierende `ctypes.Structure`-Definition direkt im Klassenkörper.
- `LADSPA_Descriptor` wird jetzt als Forward-Declaration definiert und `_fields_` danach gesetzt.

## Wirkung
- LADSPA Parameter-UI kann `describe_plugin()` wieder laden.
- LADSPA Devices zeigen wieder Controls statt rotem Fehlertext.
- Keine Änderung an Projektformat, Device-State oder Audio-Routing.
