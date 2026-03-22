# Session-Log: v0.0.20.366 — VST3 Device Exact-Reference Hotfix

**Datum**: 2026-03-09
**Bearbeiter**: GPT-5
**Aufgabe**: Nach dem Startup-Hotfix sicherstellen, dass externe VST3s beim Insert ins Device zuverlässig wieder exakt als gewähltes Sub-Plugin geladen werden
**Ausgangsversion**: 0.0.20.365
**Ergebnisversion**: 0.0.20.366

## Ziel

Der Programmstart funktioniert wieder, aber beim Insert externer VST3s konnte in einzelnen Pfaden die genaue Sub-Plugin-Referenz verloren gehen. Dadurch landete im Device-Aufbau teils nur noch der Bundle-Pfad statt des exakt gewählten Sub-Plugins.

## Analyse

- Multi-Plugin-Bundles wie `lsp-plugins.vst3` brauchen eine **exakte Referenz** aus `Pfad + plugin_name`
- In der UI/Device-Kette existierten dafür schon `__ext_path` und `__ext_plugin_name`, aber nicht jeder Insert-/Rebuild-Pfad bevorzugte dieselbe kanonische Referenz
- Wenn nur der Basis-Pfad ausgewertet wurde, konnte beim Device-Aufbau das falsche Ziel oder gar kein Parameter-Set ankommen

## Umgesetzte Änderungen

- `pydaw/ui/plugins_browser.py`
  - Browser-Insert und Drag&Drop geben jetzt zusätzlich `__ext_ref` mit
- `pydaw/ui/device_panel.py`
  - externe VST3/VST2-Insert-Metadaten werden beim Hinzufügen normalisiert
  - `__ext_ref`, `__ext_path` und `__ext_plugin_name` werden konsistent aus Plugin-ID/Payload aufgebaut
- `pydaw/ui/fx_device_widgets.py`
  - VST-Widgets bevorzugen jetzt `__ext_ref` als Quelle
- `pydaw/audio/fx_chain.py`
  - Live-Host-Build nutzt ebenfalls zuerst die exakte Referenz und löst Basis-Pfad/Sub-Plugin daraus sauber auf
- Dokumentation/Version/Changelog auf `0.0.20.366` aktualisiert

## Sicherheitsprinzip

- Kein Eingriff in DSP-Kern, Automation-System, Transport oder Routing-Architektur
- Hotfix bleibt auf externe VST-Metadaten / Insert-Pfade / Device-Aufbau begrenzt
- Rückwärtskompatibel: alte gespeicherte Referenzen funktionieren weiter

## Tests

- ✅ `py_compile` für `plugins_browser.py`, `device_panel.py`, `fx_device_widgets.py`, `fx_chain.py`, `vst3_host.py`
- ✅ Helper-Test für `build_plugin_reference()` / `split_plugin_reference()` / `resolve_plugin_reference()`

## Nächste sichere Schritte

- [ ] Optional Device-Header bei Multi-Plugin-VST3s lesbarer machen (Datei + Sub-Plugin separat)
- [ ] Optional Diagnose-Hinweis ergänzen, wenn ein externes VST nach Insert keine Parameter zurückliefert
