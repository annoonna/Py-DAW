# Changelog v0.0.20.467 — CLAP Live-Plugin-Cache + Find-Log-Drosselung

## Änderungen

- `pydaw/ui/fx_device_widgets.py`
  - `ClapAudioFxWidget` nutzt jetzt einen lokalen Cache für die laufende CLAP-Instanz
  - `_find_live_clap_plugin()` unterstützt `use_cache=True/False`
  - `[CLAP-FIND]`-Meldungen werden nur noch bei Zustandswechseln geloggt
  - Editor-bezogene Lookup-Pfade nutzen bevorzugt den Cache

## Motivation

Beim geöffneten CLAP-Editor wurde derselbe Plugin-Finder sehr oft aufgerufen. Das erzeugte unnötige Map-Durchläufe und langen Terminal-Log-Spam, obwohl funktional immer dieselbe Instanz gefunden wurde.

## Risiko

Niedrig. Keine Änderung an DSP, Audio-Routing oder CLAP-ABI; nur UI-/Diagnose-Pfad.
