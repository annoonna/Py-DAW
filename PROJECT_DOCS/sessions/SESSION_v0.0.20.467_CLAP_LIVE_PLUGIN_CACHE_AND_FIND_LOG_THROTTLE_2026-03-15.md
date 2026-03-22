# Session v0.0.20.467 — CLAP Live-Plugin-Cache + Find-Log-Drosselung

**Datum:** 2026-03-15  
**Entwickler:** OpenAI GPT-5.4 Thinking  
**Version:** 0.0.20.466 → 0.0.20.467

## Ziel

Den CLAP-Widget-Lookup sicher entlasten, ohne am Audio-Thread oder am eigentlichen CLAP-Processing etwas zu ändern.

## Umgesetzte Änderungen

- `ClapAudioFxWidget` hält jetzt einen lokalen Cache auf die zuletzt gefundene laufende CLAP-Instanz.
- `_find_live_clap_plugin()` kann bei Bedarf weiterhin mit `use_cache=False` frisch in den Engine-Maps suchen.
- Wiederholte `[CLAP-FIND]`-Meldungen werden über `_log_clap_find_once()` gedrosselt.
- Editor-Pump und GUI-Support-Check verwenden primär den Cache und refreshen nur bei Bedarf.
- Beim Schließen des Editors wird der Cache invalidiert, damit ein späteres Reopen sauber neu auflösen kann.

## Warum das sicher ist

- Keine Änderung an `clap_host.py`
- Keine Änderung am Audio-Callback
- Keine Änderung an Parameterwerten, Routing oder Host-ABI
- Nur UI-seitige Wiederverwendung einer bereits gefundenen Plugin-Referenz

## Betroffene Datei

- `pydaw/ui/fx_device_widgets.py`

## Validierung

- `python -m py_compile pydaw/ui/fx_device_widgets.py`

## Offen

- Das leere Surge-XT-Editorfenster auf manchen X11/XWayland-Setups ist noch separat zu untersuchen.
