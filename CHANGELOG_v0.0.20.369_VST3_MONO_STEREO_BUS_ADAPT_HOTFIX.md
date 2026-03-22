# CHANGELOG v0.0.20.369 — VST3 Mono/Stereo Bus-Adapt Hotfix

## Problem

Der neue `pedalboard`-basierte VST3-Host lief intern immer mit einem starren Stereo-Buffer (`2 x frames`).
Mono-Plugins wie **LSP Autogain Mono** oder **Filter Mono** akzeptieren aber nur einen 1→1-Hauptbus.
Dadurch kam es im Playback zu wiederholten Fehlern wie:

- `does not support 2-channel output`
- `Main bus currently expects 1 input channels and 1 output channels`

## Fix

- `pydaw/audio/vst3_host.py` adaptiert jetzt den Main-Bus zwischen Host und Plugin sicher.
- Stereo-Host → Mono-Plugin wird an der Bridge sauber heruntergemischt.
- Mono-Plugin → Stereo-Host wird wieder auf beide Kanäle gespiegelt.
- Falls `pedalboard` die Kanalzahl nicht vorab exponiert, wird sie einmal aus dem ersten Process-Fehler extrahiert und danach gecached.

## Wirkung

- Mono-FX aus `lsp-plugins.vst3` laufen jetzt im Audio-FX-Chain-Playback.
- Kein permanenter Fehler-Log-Spam pro Callback mehr.
- Keine Änderung an Mixer, Arranger, Routing oder sonstigem Core-Verhalten.

## Technischer Hinweis

Dieser Hotfix bleibt bewusst auf den **externen VST-Bridge-Pfad** beschränkt.
Der restliche DAW-Engine-Pfad bleibt weiterhin stereo-intern, um nichts an bestehendem Playback-Verhalten zu riskieren.

