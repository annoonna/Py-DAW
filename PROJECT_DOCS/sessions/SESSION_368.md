# SESSION 368 — VST3 Widget Async-Param-Load Fix

**Version**: 0.0.20.367 → 0.0.20.368
**Datum**: 2026-03-09
**Problem**: UI friert 10-60 s ein wenn ein VST3-Plugin per "Add to Device" hinzugefügt wird

---

## Root Cause

`Vst3AudioFxWidget._load_controls_and_build_rows()` rief `describe_controls()` synchron
im Qt-Main-Thread auf. `describe_controls()` → `pedalboard.load_plugin(path, plugin_name=…)`
blockiert den Main-Thread für die gesamte Plugin-Initialisierungszeit.

Für komplexe Bundles (z.B. `lsp-plugins.vst3` mit 100+ DSP-Plugins) bedeutet das:
- UI friert beim Klick auf "Add to Device" komplett ein
- 10-60 Sekunden Wartezeit
- Plugin erscheint danach ggf. ohne Parameter ("Keine Parameter gefunden")
- Anwender sieht "nichts wurde erstellt" oder falschen Zustand

Dieser Fehler ist identisch in der Klasse mit dem Startup-Scan-Hang (Session 367),
nur im Widget-Erzeugungs-Pfad statt im Browser-Init-Pfad.

---

## Fix — `pydaw/ui/fx_device_widgets.py`

### Neue Klasse: `_Vst3ParamLoader(QThread)`
Vor `Vst3AudioFxWidget` eingefügt:
- `params_ready = pyqtSignal(list)` — sendet Liste von `Vst3ParamInfo`
- `load_failed = pyqtSignal(str)` — sendet Fehlermeldung
- `run()` ruft `describe_controls(path, plugin_name)` im Background-Thread auf

### Geänderte Methode: `_load_controls_and_build_rows()`
Vorher: synchron `describe_controls(...)` + Row-Build im Main-Thread.
Nachher:
1. Zeigt sofort "Lade Plugin-Parameter…" im Status-Label
2. Erzeugt `_Vst3ParamLoader` und startet ihn
3. Verbindet `params_ready → _on_params_loaded` und `load_failed → _on_load_failed`

### Neue Methoden:
- `_on_params_loaded(infos)` — empfängt Parameter im Main-Thread, ruft `_build_rows_from_infos()`, `refresh_from_project()`, `_ui_sync_timer.start()`
- `_on_load_failed(msg)` — setzt Fehlermeldung im Status-Label
- `_build_rows_from_infos()` — extrahierter Row-Build-Code (vorher inline in `_load_controls_and_build_rows`)

### `__init__` Ergänzung:
`self._loader = None` — hält QThread-Referenz, verhindert vorzeitige GC

### `_build()` Änderung:
`refresh_from_project()` und `_ui_sync_timer.start()` entfernt aus `_build()`,
werden jetzt in `_on_params_loaded()` aufgerufen (nach async-Load).

---

## Ergebnis

| Situation | Vorher | Nachher |
|-----------|--------|---------|
| VST3 per Browser hinzufügen | UI friert 10-60 s | Sofort responsive, "Lade…" Status |
| Einfaches VST3 (schnelles Bundle) | Hängt kurz | Parameter in < 1 s verfügbar |
| Komplexes Bundle (lsp-plugins) | Hängt 30+ s | UI bleibt offen, Parameter kommen async |
| Plugin-Ladefehler | Status "Laden fehlgeschlagen" | Gleich, aber UI bleibt reaktiv |

---

## Nicht geändert
- Kein DSP-Core, kein Audio-Engine-Pfad
- Kein Transport, kein Mixer, kein Routing
- LV2/LADSPA Widget-Klassen unberührt
- Startup-Cache-Guard (Session 367) unberührt
