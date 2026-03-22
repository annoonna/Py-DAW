# SESSION v0.0.20.326 — Bounce/Freeze erste sichere Workflow-Stufe + AETERNA Formula Families

Datum: 2026-03-07
Autor: GPT-5

## Ziel
- Ersten sicheren **Bounce in Place / Freeze Track**-Workflow ergänzen, ohne Playback-Core umzubauen.
- Parallel AETERNA lokal um breitere **Random-Math-/Formel-Familien** erweitern.

## Umgesetzt
- `ProjectService` um lokale Offline-Render-Helfer erweitert:
  - Rendern einer Track-/Clip-Auswahl in eine WAV
  - Erzeugen einer neuen Audio-Proxy-Spur
  - erstes Reaktivieren von Freeze-Quellen
- `ArrangerCanvas` Kontextmenü erweitert:
  - **Bounce in Place → neue Audiospur (+FX)**
  - **Bounce in Place + Quelle stummschalten**
  - **Bounce in Place (Dry)**
- `TrackListWidget` Kontextmenü erweitert:
  - **Spur einfrieren (Bounce → Audio + FX)**
  - **Spur bouncen (Dry)**
  - **Gruppe einfrieren** bei vorhandener Track-Gruppe
  - **Freeze-Quellen wieder aktivieren** für Proxy-Spuren
- `AETERNA` lokal erweitert:
  - Formelhilfe und Randomizer um zusätzliche mathematische Familien ergänzt
  - Ziel: nicht nur `phase`-dominierte Startideen, sondern mehr env/chaos/coherent/noise-inspirierte Richtungen

## Sicherheit / bewusst nicht angefasst
- kein Playback-Core-Umbau
- kein Mixer-/Transport-Umbau
- keine globale Freeze-Engine
- keine Hintergrund-Job-Architektur geändert

## Hinweise
- Erste sichere Stufe: workflow-orientiert und bewusst konservativ
- Nächster sinnvoller Schritt: kleiner **Bounce-/Freeze-Dialog** oder **sichtbare Freeze-Statusmarker**
