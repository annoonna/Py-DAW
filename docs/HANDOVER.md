# Übergabedokumentation – Python/Qt6 Musik-DAW (PyDAW / ChronoScaleStudio)

## Projektziel
Leichtgewichtige, modulare DAW in **Python + Qt6** mit „Pro-DAW-Feeling“:

- **Arranger/Timeline** (Clips auf Tracks)
- **Piano-Roll**
- **Mixer + Bus/Master-Konzept**
- Fokus auf **PipeWire/JACK-Workflow** (Client in `qpwgraph` sichtbar), **Input-Monitoring**, später **Recording** und **sauberes Routing**
- Stabiler, iterativer Ausbau mit **konsistenter Versionierung** als *„wachsende ZIP-Linie“*

## Architektur

### UI / Qt6-Struktur (High-Level)
- **QMainWindow** als Hauptfenster (Menüleiste, Transport, zentrale Layout-Aufteilung)
- Zentrale Bereiche:
  - **Arranger/Timeline-Widget** (Clips, Grid, Playhead, Auswahlwerkzeuge)
  - **Track-Liste / Inspector** links (Audio/Instrument/Bus/Master, M/S/R, Routing-Auswahl)
  - **Mixer** unten (Vol/Pan pro Track, Master)
  - **Piano-Roll** (Notenbearbeitung)
  - **Audio Settings Dialog** (Backend, Ports, Samplerate/Buffer, JACK-Client, Monitoring)
- Custom Widgets (typisch):
  - Arranger Canvas / Timeline Canvas (QGraphicsView/QWidget-basiert)
  - Piano-Roll Canvas (QGraphicsView/QWidget-basiert)
  - Clip-Objekte (MIDI/AUDIO) als **Datenmodelle** + **visuelle Repräsentation**

### Service-/Engine-Schicht
- **ServiceContainer** (Dependency Injection / zentrale Dienste)
- **AudioEngine** als zentrale Schicht (Backend + Routing)
- **JACK Client Service** (JACK-Modus: Client „PyDAW“ mit Ports)
- **Arrangement-Rendering / Pre-Render**
  - `arrangement_renderer`: bereitet Clips vor, rendert MIDI→Audio (z. B. SF2/FluidSynth) und erzeugt Playback-Quellen

## Aktueller Code-Stand (Implementierte Features)

### 1) GUI / Bedienung
- Transport: **Play/Stop/Loop**, Tempo, Taktart, Grid/Snap (z. B. 1/16)
- Track-Typen sichtbar: **Audio Track**, **Instrument Track**, **Bus**, **Master**
- **M/S/R** Buttons in der Trackliste
- Piano-Roll vorhanden (Noten sichtbar/bearbeitbar – abhängig von Version/Clip-Status)
- Arranger: Clips sichtbar (MIDI/AUDIO), Grid/Playhead, Auswahl-Tools

### 2) Audio-Backends & Routing
- Backend-Auswahl im Audio-Dialog:
  - `sounddevice` (PortAudio) – klassischer Stereo I/O
  - **JACK / PipeWire-JACK** (in `qpwgraph` sichtbar)
- JACK Client „PyDAW“: In + Out im selben Client (sample-synchron)
- Konfigurierbare Portanzahl über GUI (Stereo-Paare → Ports)
- **Input Monitoring** (Inputs → Outputs) implementiert (Pass-Through)
- Auto-Restart-Mechanismus beim „OK“ im Audio-Dialog (Port-Änderungen/Backend-Wechsel werden wirksam)

### 3) JACK Playback (Arrangement → JACK)
- Ziel: „Echtes“ Playback über JACK statt nur Monitoring
- Engine erzeugt Audioausgabe über JACK-Out Ports
- Logging nach `~/.cache/ChronoScaleStudio/pydaw.log`

### 4) Projekt-/Session-Verhalten
- Alte Projekte laden grundsätzlich möglich, aber es gab Regressionen
- Problemstelle: Port/Backend-Wechsel kann zu „neuem leeren Projekt“ führen, wenn State/Reload nicht sauber übernommen wird

## Struktur der Hauptdatei (main.py / App-Entry)
Typischer Ablauf (konzeptionell):
1. Logging initialisieren (`setup_logging`)
2. Qt Application erstellen
3. ServiceContainer initialisieren
4. AudioEngine initialisieren (backend-abhängig)
5. MainWindow erstellen + `show()`
6. Eventloop starten
7. Audio-Settings „OK“: Settings persistieren → Engine neu konfigurieren (aktuell via Restart/`exec`)

## Bekannte Probleme / Regressionen (v0.0.19.3.1–v0.0.19.3.4)
- Renderer-/Datamodel-Inkonsistenzen (RenderKey/Clip-Länge/SF2 Bank/Preset/MidiNote-Objekt)
- JACK nicht verfügbar führt zu UX-Problemen (Spam/Blockade)
- Port-Änderung erzeugt neue Instanz, Terminal-Kontext kann verloren gehen (Restart-Mechanismus)
- Routing aktuell zu hardware-nah: internes Playback/Master-Out darf nicht „verschwinden“, wenn Recording-Spuren dazukommen

## Nächste geplante Schritte

### A) Pro-DAW-Style internes Routing (höchste Priorität)
Ziel: **Track → Bus → Master → Out** immer stabil, unabhängig von Recording-Spuren.
- Interne Bus-Struktur fix:
  - Jeder Track hat Output-Bus (z. B. „Master“ oder „Bus 1/2…“)
- Recording-Spuren wählen **Input** (z. B. In 1/2, In 3/4), Output bleibt Bus/Master
- GUI:
  - Track **Input Selector** (für Recording)
  - Track **Output Selector** (Bus/Master)
- JACK:
  - Stabile Out-Ports (`out_1/out_2/...`)
  - Master → `out_1/out_2` (Default), optional Alt-Mix → `out_3/out_4` etc.

### B) Stabiler Restart / kein Terminal-Verlust
- Restart nicht via `os._exit`, sondern `os.execvpe` oder `subprocess` mit Log-Weiterleitung
- Optional: UI-Button „Log anzeigen“
- Wenn JACK nicht läuft:
  - Auto-Fallback: `pw-jack` (wenn verfügbar) oder Backend automatisch auf `sounddevice`

### C) Recording (Audio aufnehmen)
- Aufnahme in Audio Clips direkt in die Timeline
- Record-Arm pro Track
- Quelle: JACK Inputs (`in_1..in_6`)
- WAV schreiben (Streaming), Clip automatisch erzeugen
- Latenz/Alignment: Puffergröße berücksichtigen, später „Latency Compensation“

### D) Renderer-Konsistenz / Projekt-Laden
- MIDI Note Model vereinheitlichen (keine `.get()` auf MidiNote)
- RenderKey-Signatur stabil halten (sf2_bank/preset/samplerate/clip_length_beats)
- Caching: MIDI→WAV Cache via `midi_content_hash` zuverlässig

### E) Hot-Reconfigure (ohne Restart) – später
- Ports dynamisch registrieren/deregistrieren während JACK-Client läuft
- Internes Rebind der Busse/Ports ohne App-Neustart (nach stabiler Bus/Master-Architektur)

## Technischer Stack
- Python 3.x (bei dir oft 3.13; grundsätzlich 3.x)
- Qt6: PyQt6 oder PySide6 (Qt Widgets)
- Audio:
  - `sounddevice` (PortAudio)
  - JACK / PipeWire-JACK via `python-jack-client` (Client „PyDAW“)
- MIDI→Audio Rendering: SF2/FluidSynth-Pfad vorgesehen/angebunden
- Logging: `~/.cache/ChronoScaleStudio/pydaw.log`
