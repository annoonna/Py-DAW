# v0.0.20.248 — LADSPA ABI Layout + Port Flags Fix

## Problem
LADSPA Devices konnten beim Anklicken/Rebuild einen harten SIGSEGV in `_ctypes`/`libffi` auslösen.

## Ursache
- `pydaw/audio/ladspa_host.py` hatte ein ABI-fehlerhaftes `LADSPA_Descriptor`-ctypes-Layout.
- Das Feld `ImplementationData` fehlte; dadurch waren `instantiate`, `connect_port`, `run`, `cleanup` usw. um ein Pointer-Feld verschoben.
- Außerdem waren die Port-Bitmasks vertauscht, wodurch Audio/Control/Input/Output falsch erkannt wurden.

## Fix
- `ImplementationData` in den ctypes-Descriptor eingefügt.
- Port-Flags auf die offiziellen LADSPA-Werte gesetzt:
  - `LADSPA_PORT_INPUT = 0x1`
  - `LADSPA_PORT_OUTPUT = 0x2`
  - `LADSPA_PORT_CONTROL = 0x4`
  - `LADSPA_PORT_AUDIO = 0x8`

## Erwartetes Ergebnis
- Kein falscher Funktionspointer-Aufruf mehr beim LADSPA-Init/Rebuild.
- Korrekte Erkennung und Verdrahtung von Audio- und Control-Ports.
