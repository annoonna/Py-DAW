# Changelog — v0.0.20.469

## Fokus

CLAP-Editor-Bootstrap weiter absichern, ohne DSP/Audio-Logik anzufassen.

## Änderungen

- `_ClapPlugin.create_gui()` pumpt CLAP-`on_main_thread()` jetzt stufenweise nach `create()`, `set_parent()` und `show()`.
- Best-Effort `set_scale(1.0)` ergänzt.
- `ClapAudioFxWidget` hält bei offenem Editor einen sehr langsamen 120-ms-GUI-Keepalive aufrecht, damit späte `request_callback()`-Bursts nicht verloren gehen.

## Risiko

- Kein Eingriff in Audio-Thread / DSP.
- Kein Eingriff in Parameter-Mapping oder MIDI-Learn.
- Aktiv nur, wenn ein CLAP-Editor geöffnet wird.
