# Changelog v0.0.20.468 — CLAP Editor Deferred-Mapping + GUI-Visibility/Resize-Handshake

## Änderungen

- `pydaw/ui/fx_device_widgets.py`
  - CLAP-Editor wird jetzt deferred nach `show()` + `processEvents()` geöffnet
  - nativer GUI-Container nutzt `WA_DontCreateNativeAncestors`
  - Pump-Intervall wird nach der Startphase automatisch entschärft
  - `request_show`/`request_hide`/Resize werden an das Qt-Fenster gespiegelt

- `pydaw/audio/clap_host.py`
  - neue GUI-Helper: `take_requested_gui_visibility()`
  - neue GUI-Helper: `set_gui_size()`
  - letzte GUI-Größe wird lokal mitgeführt

## Motivation

`create_gui()` war zwar erfolgreich, aber der eingebettete Editor blieb lokal dennoch leer. Der Patch verschiebt den kritischen Parenting-/Mapping-Moment in einen späteren, stabileren Qt/X11-Zeitpunkt und ergänzt den GUI-Handshake zwischen Plugin und Host.

## Risiko

Niedrig. Kein Eingriff in DSP, Audio-Routing oder Plugin-Scan; nur Editor-Lifecycle und GUI-Kommunikation.
