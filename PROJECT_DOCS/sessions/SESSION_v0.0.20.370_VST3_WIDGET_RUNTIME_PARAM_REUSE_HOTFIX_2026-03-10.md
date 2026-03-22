# v0.0.20.370 — VST3 Widget Runtime-Param-Reuse Hotfix

**Datum**: 2026-03-10
**Bearbeiter**: GPT-5
**Aufgabe**: Sicheren Fix für leere VST3-Parameter-Widgets nach dem Bus-Hotfix ergänzen, ohne den responsiven Insert wieder kaputt zu machen
**Ausgangsversion**: 0.0.20.369
**Ergebnisversion**: 0.0.20.370

## Ziel

Nach dem Bus-Adapt-Hotfix liefen Mono-VSTs audioseitig korrekt, aber im Device-Widget trat ein neuer Fehlerpfad auf:

- `describe_controls: load failed ... must be reloaded on the main thread`

Dadurch blieben frisch eingefügte VST3-Widgets teilweise ohne Parameterliste, obwohl die DSP-Instanz bereits erfolgreich im FX-Map lief.

Wichtig war dabei:

- **keinen** Rollback auf den alten blockierenden Sync-Load machen
- den **Async-Insert aus v0.0.20.368 behalten**
- nur den Parameter-Metadatenpfad robuster machen

## Umgesetzte Änderungen

- `pydaw/ui/fx_device_widgets.py`
  - VST-Widget versucht Parameter jetzt zuerst aus der **laufenden DSP-Instanz** (`audio_engine._track_audio_fx_map`) zu lesen
  - kleiner Retry-/Poll-Pfad ergänzt, falls das Device gerade frisch kompiliert wird
  - Async-Loader bleibt als Fallback erhalten, startet aber erst danach

- `pydaw/audio/vst3_host.py`
  - interne Helferfunktion `_extract_param_infos(plugin)` ergänzt
  - `Vst3Fx._load()` nutzt die bereits geladene Plugin-Instanz für Parameterauslese statt denselben VST-Pfad direkt erneut zu laden

## Sicherheitsprinzip

- Keine Änderung an Audio-Routing, Mixer, Projektmodell oder Transport
- Keine Änderung am eigentlichen DSP-Process-Pfad außer dem Wegfall eines unnötigen Zweit-Loads beim Build
- Async-Fallback bleibt erhalten, damit der UI-Freeze-Fix aus v0.0.20.368 nicht verloren geht

## Benutzerwirkung

- Externe VST3-Devices mit bereits laufender DSP-Instanz zeigen ihre Parameter wieder zuverlässig an
- Die Meldung
  - `must be reloaded on the main thread`
  taucht im typischen Device-Fall nicht mehr als Ursache für leere Parameterlisten auf
- Frisch eingefügte Plugins bleiben weiterhin responsiv beim Insert

## Tests

- ✅ `python -m py_compile pydaw/audio/vst3_host.py pydaw/ui/fx_device_widgets.py`
- ✅ kleiner Smoke-Test für `_extract_param_infos()` mit Mock-Plugin
- ℹ️ echter Qt-/PyQt6-Widget-Lauftest war im Container nicht möglich, weil `PyQt6` dort nicht installiert war

## Nächste sichere Schritte

- [ ] Optional kleinen Header-Hinweis ergänzen, ob die Parameter aus **live DSP** oder **Fallback-Load** stammen
- [ ] Optional Diagnose-Hinweis ergänzen, wenn weder Runtime-FX noch Fallback Parameter liefern
