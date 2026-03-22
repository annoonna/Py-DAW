# Session-Log: v0.0.20.365 — VST3 Startup Scan Hang Hotfix

**Datum**: 2026-03-09
**Bearbeiter**: GPT-5
**Aufgabe**: Start-Hänger nach v0.0.20.364 beheben, ohne die sichere VST3-Browser-/Host-Kette kaputt zu machen
**Ausgangsversion**: 0.0.20.364
**Ergebnisversion**: 0.0.20.365

## Ziel

Nach dem letzten VST3-Browser-Fix öffnete das Programm auf dem Nutzersystem nicht mehr zuverlässig. Der Stacktrace zeigte keinen Crash im DAW-Core, sondern einen Hänger in `ZamVerb.vst3` / `pedalboard_native`, ausgelöst während des automatischen Plugin-Scans beim App-Start.

## Analyse

- `plugins_browser.py` startet direkt beim Erzeugen des Widgets einen asynchronen `rescan()`
- `plugin_scanner.py` rief in v0.0.20.364 für **jedes** gefundene VST3 `probe_multi_plugin_names()` auf
- `probe_multi_plugin_names()` instanziiert das Plugin intern via `pedalboard.load_plugin()`
- Das ist für echte Multi-Plugin-Bundles wie `lsp-plugins.vst3` nützlich, aber für manche normale VST3s riskant
- Auf dem gemeldeten System blieb der Start dadurch in `ZamVerb.vst3` hängen

## Umgesetzte Änderungen

- `pydaw/services/plugin_scanner.py`
  - neuer Guard `_should_try_multi_vst_probe(path)`
  - automatisches Eager-Probing nur noch für bekannte sichere Collection-Bundles (`lsp-plugins.vst3`)
  - allgemeiner Debug-Override `PYDAW_VST_MULTI_PROBE=1` ergänzt
- Dokumentation/Version/Changelog auf `0.0.20.365` aktualisiert

## Sicherheitsprinzip

- Kein Eingriff in Audio-Engine, Fx-Chain, Hybrid-Engine oder Projektmodell
- Hotfix nur im Discovery-/Scanner-Pfad des Plugins-Browsers
- Bereits implementierte exakte `plugin_name`-Weitergabe aus v0.0.20.364 bleibt erhalten

## Tests

- ✅ `py_compile` für geänderte Scanner-Datei
- ✅ Logiktest für `_should_try_multi_vst_probe()` (normale VST3s = kein Eager-Probe, `lsp-plugins.vst3` = erlaubt)

## Nächste sichere Schritte

- [ ] Optional Lazy-Fallback-Dialog für unbekannte Multi-Plugin-Bundles
- [ ] Optional UI-Schalter für safe/deep scan
