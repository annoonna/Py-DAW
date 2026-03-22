# CHANGELOG v0.0.20.373 — VST3 Widget Main-Thread Reload Hotfix

## Problem

Bei einigen externen VST3-Plugins schlug der späte Parameter-Fallback im `Vst3AudioFxWidget` weiterhin fehl mit:

```
Plugin ... must be reloaded on the main thread
```

Zusätzlich konnte das Widget beim Aufbau von Bool-Parametern an `QCheckBox` scheitern, weil der Import im Datei-Header fehlte.

## Lösung

- `pydaw/ui/fx_device_widgets.py` importiert jetzt `QCheckBox` explizit.
- Der bestehende Async-Fallback bleibt erhalten.
- Wenn der Worker explizit einen **Main-Thread-Reload** verlangt, plant das Widget automatisch einen **einmaligen sicheren Retry im Qt-Main-Thread** ein.
- Normale VSTs behalten damit weiter den responsiven Async-Pfad; nur der problematische Sonderfall wird synchron und gezielt nachgeladen.

## Sicherheit

- Kein Eingriff in Audio-Routing, Mixer, Transport, Projektmodell oder `Vst3Fx.process_inplace()`.
- Kein Rollback des Runtime-Param-Reuse-Pfads aus v0.0.20.370.
- Kein genereller Umbau des Plugin-Hostings; nur Widget-Fallback + fehlender Import wurden gehärtet.
