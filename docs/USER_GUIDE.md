# Py DAW Benutzerhandbuch v0.0.19.3.6_fix11

## Inhaltsverzeichnis
1. [Installation](#installation)
2. [Erste Schritte](#erste-schritte)
3. [Audio-Recording](#audio-recording)
4. [MIDI & FluidSynth](#midi--fluidsynth)
5. [Notation-Editor](#notation-editor)
6. [Workflow-Tipps](#workflow-tipps)
7. [Fehlerbehebung](#fehlerbehebung)

---

## Installation

### System-Voraussetzungen

#### Linux (empfohlen)
- **Betriebssystem**: Debian 11+, Ubuntu 20.04+, Arch Linux, Fedora 35+
- **Python**: 3.9 oder höher
- **Audio**: PipeWire (empfohlen) oder JACK
- **RAM**: 4 GB minimum, 8 GB empfohlen
- **CPU**: Dual-Core, 2 GHz+

#### Abhängigkeiten installieren

**Debian/Ubuntu:**
```bash
sudo apt update
sudo apt install -y \
    python3 python3-pip python3-venv \
    pipewire pipewire-jack qpwgraph \
    fluidsynth libfluidsynth-dev \
    portaudio19-dev \
    git
```

**Arch Linux:**
```bash
sudo pacman -S \
    python python-pip \
    pipewire pipewire-jack qpwgraph \
    fluidsynth \
    portaudio \
    git
```

**Fedora:**
```bash
sudo dnf install -y \
    python3 python3-pip \
    pipewire pipewire-jack-audio-connection-kit qpwgraph \
    fluidsynth fluidsynth-devel \
    portaudio-devel \
    git
```

### Python-Umgebung einrichten

```bash
# In das Projektverzeichnis wechseln
cd Py_DAW_v0.0.19.3.6_fix11

# Virtuelle Umgebung erstellen
python3 -m venv myenv

# Umgebung aktivieren
source myenv/bin/activate

# Basis-Abhängigkeiten installieren
pip install --upgrade pip
pip install -r requirements.txt

# Optionale Features installieren
pip install pyfluidsynth        # FluidSynth Support
pip install JACK-Client         # JACK Backend (optional)
pip install numpy sounddevice   # Recording Support
```

### Erste Prüfung

```bash
# DAW starten (Test)
python3 main.py
```

Wenn das Hauptfenster erscheint: ✅ Installation erfolgreich!

---

## Erste Schritte

### 1. Neues Projekt erstellen

**Menü: Datei → Neu**
- Projektname eingeben
- Speicherort wählen
- BPM einstellen (Standard: 120)
- Taktart wählen (Standard: 4/4)

### 2. Die Benutzeroberfläche

```
┌─────────────────────────────────────────────────────┐
│  Menüleiste: Datei | Bearbeiten | Ansicht | Audio   │
├─────────────────────────────────────────────────────┤
│  Transport: [◀◀] [▶] [■] [●] | BPM: 120 | 4/4      │
├─────────────────────────────────────────────────────┤
│  Toolbar: [Zeiger] [Stift] [Messer] ... Grid: 1/16 │
├──────────────┬──────────────────────────────────────┤
│  Track-Liste │  Arranger (Timeline)                 │
│  ┌─────────┐│  ═════════════════════════════       │
│  │Track 1  ││  [MIDI Clip] [Audio Clip]           │
│  │Track 2  ││  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌            │
│  │Track 3  ││                                      │
│  └─────────┘│                                      │
├──────────────┴──────────────────────────────────────┤
│  Editor-Tabs: [Piano Roll] [Notation]              │
│  ┌──────────────────────────────────────────────┐  │
│  │  (Piano Roll zeigt Noten des ausgewählten   │  │
│  │   MIDI-Clips)                                │  │
│  └──────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────┤
│  Mixer/Bibliothek (rechts)                          │
└─────────────────────────────────────────────────────┘
```

### 3. Track erstellen

**Rechtsklick in Track-Liste → "Track hinzufügen"**
- Wählen: **Instrument** oder **Audio**
- Track benennen
- Farbe auswählen (optional)

### 4. MIDI-Clip erstellen

1. **Track auswählen** (Klick in Track-Liste)
2. **Stift-Tool aktivieren** (Toolbar oder Taste `D`)
3. **In Timeline klicken** → MIDI-Clip wird erstellt
4. **Doppelklick auf Clip** → Piano Roll öffnet sich

### 5. Noten eingeben

Im **Piano Roll**:
- **Stift-Tool**: Noten hinzufügen (Klick in Raster)
- **Zeiger-Tool**: Noten auswählen/verschieben
- **Radierer**: Noten löschen
- **Messer**: Noten teilen
- **Grid-Raster**: 1/1, 1/2, 1/4, 1/8, 1/16, 1/32, 1/64

**Tastaturkürzel:**
- `Leertaste`: Play/Pause
- `Strg+Z`: Undo
- `Strg+Shift+Z`: Redo
- `Strg+C/V`: Kopieren/Einfügen
- `Entf`: Löschen

---

## Audio-Recording

### Setup

1. **Audio-Backend konfigurieren**
   - Menü: **Edit → Audio Settings**
   - Backend wählen: **sounddevice** (PipeWire/ALSA) oder **jack**
   - Input-Gerät auswählen
   - Sample Rate: 48000 Hz (Standard)
   - Buffer Size: 256 oder 512 Samples

2. **Recording-Status prüfen**
   - Statusleiste zeigt: `Recording: Backend=pipewire`

### Aufnahme starten

1. **Audio-Track erstellen**
   - Rechtsklick in Track-Liste → "Audio Track"

2. **Input-Monitor aktivieren**
   - Track-Parameter: **Monitor-Button** aktivieren (🔊)
   - Input-Pegel wird angezeigt

3. **Recording aktivieren**
   - **Transport: Rote Record-Taste** [●]
   - oder Taste `R`

4. **Aufnahme starten**
   - **Play-Taste drücken** [▶]
   - Recording läuft!

5. **Aufnahme beenden**
   - **Stop-Taste** [■]
   - Audio-Clip wird automatisch im Track eingefügt

### Recording-Optionen

**Im Recording-Dialog** (Menü: Audio → Recording Setup):

| Option | Beschreibung |
|--------|-------------|
| **Pre-Roll** | Metronom-Klicks vor Aufnahme |
| **Count-In** | 1-4 Takte Vorlauf |
| **Loop-Recording** | Mehrere Takes aufeinander |
| **Auto-Punch** | Nur bestimmten Bereich ersetzen |

### Tipps für beste Qualität

1. **Latenz reduzieren**:
   ```bash
   # PipeWire-Latenz prüfen
   pw-metadata -n settings
   
   # Latenz anpassen (z.B. 256/48000)
   pw-metadata -n settings 0 clock.force-quantum 256
   ```

2. **Monitoring ohne Latenz**:
   - **Hardware-Monitoring** am Audio-Interface verwenden
   - oder **JACK-Passthrough** aktivieren (Audio Settings)

3. **Buffer-Size optimieren**:
   - **Zu klein** (< 128): Knackser, CPU-Überlastung
   - **Zu groß** (> 1024): Spürbare Latenz
   - **Empfohlen**: 256 oder 512 Samples

---

## MIDI & FluidSynth

### FluidSynth einrichten

1. **SoundFont besorgen**
   
   **Kostenlose SoundFonts:**
   ```bash
   # FluidR3_GM (General MIDI)
   wget https://member.keymusician.com/Member/FluidR3_GM/FluidR3_GM.sf2
   
   # Oder aus Repository
   sudo apt install fluid-soundfont-gm
   # Datei liegt dann in: /usr/share/sounds/sf2/FluidR3_GM.sf2
   ```

2. **SoundFont laden**
   - Menü: **Audio → FluidSynth → Load SoundFont...**
   - SF2-Datei auswählen
   - Statusleiste: "SoundFont geladen: FluidR3_GM.sf2"

3. **Track auf FluidSynth routen**
   - Track-Parameter: **Output** → "FluidSynth"
   - oder im Mixer: Routing-Einstellungen

### MIDI-Eingabe

#### Über MIDI-Keyboard

1. **MIDI-Device verbinden**
   ```bash
   # Verfügbare MIDI-Geräte anzeigen
   aconnect -l
   ```

2. **MIDI-Einstellungen**
   - Menü: **Edit → MIDI Settings**
   - Input Device wählen
   - **MIDI Through** aktivieren

3. **Recording-Ready**
   - Track aktivieren (rot)
   - Play + Record drücken
   - Auf Keyboard spielen → Noten werden aufgenommen

#### Über Computer-Tastatur

**Tastatur-Mapping** (wie ein Mini-Keyboard):

```
  2 3   5 6 7   9 0   =
 Q W E R T Y U I O P [ ]
  C# D#  F# G# A#  C# D#
 C  D  E  F  G  A  B  C  D
```

- **A/S/D/F/G/H/J/K**: Weiße Tasten (C-C)
- **W/E/T/Y/U/O/P**: Schwarze Tasten (#)
- **Z/X**: Oktave runter/hoch

### FluidSynth-Einstellungen

**Erweitert** (Menü: Audio → FluidSynth → Settings):

| Parameter | Beschreibung | Werte |
|-----------|-------------|-------|
| **Gain** | Master-Lautstärke | 0.0 - 2.0 (Standard: 0.2) |
| **Reverb** | Hall-Effekt | On/Off, Level, Room Size |
| **Chorus** | Chorus-Effekt | On/Off, Level, Speed, Depth |
| **Interpolation** | Qualität | Linear, 4-point, 7-point |

---

## Notation-Editor

### Aktivieren

**Menü: Ansicht → Notation (WIP)**

Der **Notation-Tab** erscheint neben dem Piano Roll.

### Grundlegende Bedienung

#### Tools

| Tool | Funktion | Tastatur |
|------|----------|----------|
| **Select** | Noten auswählen | `Esc` |
| **Pencil** | Noten hinzufügen | `D` |
| **Eraser** | Noten löschen | `E` |
| **Time** | Playhead setzen | `T` |
| **Knife** | Noten teilen | `K` |

#### Noten eingeben

1. **Pencil-Tool aktivieren**
2. **Auf Notenlinie klicken** → Note wird hinzugefügt
3. **Grid bestimmt Notenlänge** (1/16, 1/8, 1/4 etc.)
4. **Snap aktiviert** → Automatisches Einrasten

#### Notenwerte

**Grid-Einstellung** entspricht Notenwerten:
- `1/1`: Ganze Note
- `1/2`: Halbe Note
- `1/4`: Viertelnote
- `1/8`: Achtelnote
- `1/16`: Sechzehntelnote
- `1/32`: Zweiunddreißigstelnote

#### Zoom & Navigation

- **Mausrad + Strg**: Horizontal zoomen
- **Mausrad**: Vertikal scrollen
- **Mittlere Maustaste + Ziehen**: Pan (Verschieben)
- **Zoom-Buttons**: +/- in Toolbar

### Erweiterte Features (ChronoScaleStudio)

*Hinweis: Vollständige Integration in Vorbereitung*

Die DAW enthält bereits die **Skalen-Datenbank** mit 500+ Skalen:

```python
# Verfügbare Skalen anzeigen
from pydaw.notation.scales.database import ScaleDatabase
db = ScaleDatabase()
print(db.get_all_scales())
```

**Geplante Features:**
- Scale-Browser im Notation-Tab
- Automatische Skalen-Highlights
- Scale-basierte Quantisierung
- Chord-Suggestions
- AI-gestützte Harmonisierung

---

## Workflow-Tipps

### Effizientes Arbeiten

#### 1. Templates nutzen

**Eigene Project-Templates erstellen:**
```bash
# Projekt speichern als Template
Datei → Als Template speichern...

# Template laden
Datei → Neues Projekt aus Template...
```

#### 2. Tastaturkürzel lernen

**Essential Shortcuts:**
| Aktion | Shortcut |
|--------|----------|
| Play/Pause | `Leertaste` |
| Stop | `Strg+Leertaste` |
| Aufnahme | `R` |
| Undo/Redo | `Strg+Z` / `Strg+Shift+Z` |
| Speichern | `Strg+S` |
| Kopieren/Einfügen | `Strg+C` / `Strg+V` |
| Clip duplizieren | `Strg+D` |
| Grid kleiner/größer | `G` / `Shift+G` |

#### 3. Clip-Launcher verwenden

**Für Live-Performance & Arrangement-Ideen:**

1. **Clip-Launcher öffnen** (Menü: Ansicht → Clip Launcher)
2. **Clips in Slots ziehen**
3. **Slots triggern** (Mausklick oder MIDI-Mapping)
4. **Szenen speichern** → Komplette Arrangements abspielen

### Audio-Routing mit qpwgraph

**JACK/PipeWire Verbindungen visualisieren:**

```bash
# qpwgraph starten
qpwgraph &
```

**Py DAW erscheint als:**
- `PyDAW` (Hauptanwendung)
- `PyDAW_Recorder` (beim Recording)
- `fluidsynth` (wenn FluidSynth aktiv)

**Verbindungen:**
- **System Capture** → `PyDAW_Recorder` (Recording)
- `PyDAW` → **System Playback** (Wiedergabe)
- `fluidsynth` → **System Playback** (MIDI-Synth)

### Projekt-Organisation

**Empfohlene Struktur:**
```
~/Musik/PyDAW_Projects/
├── Project1/
│   ├── Project1.pydaw       # Projektdatei
│   ├── Audio/               # Audio-Recordings
│   │   ├── Take1.wav
│   │   └── Take2.wav
│   ├── MIDI/                # MIDI-Exports
│   └── Mixdown/             # Finale Mixdowns
├── Project2/
└── Templates/               # Eigene Templates
```

---

## Fehlerbehebung

### Problem: Programm startet nicht

**Fehler:** `ModuleNotFoundError: No module named 'PyQt6'`

**Lösung:**
```bash
# Virtuelle Umgebung aktivieren!
source myenv/bin/activate

# Abhängigkeiten erneut installieren
pip install -r requirements.txt
```

---

### Problem: Kein Ton bei FluidSynth

**Symptom:** MIDI-Noten werden gespielt, aber kein Sound

**Checkliste:**
1. **SoundFont geladen?**
   - Statusleiste prüfen: "SoundFont geladen: ..."
   
2. **Track-Routing korrekt?**
   - Track-Output → FluidSynth
   
3. **Lautstärke?**
   - Master-Fader im Mixer prüfen
   - FluidSynth Gain erhöhen (Audio → FluidSynth → Settings)
   
4. **System-Audio aktiv?**
   ```bash
   # PipeWire-Status
   systemctl --user status pipewire
   
   # Test-Sound
   speaker-test -c 2 -t wav
   ```

---

### Problem: Recording produziert nur Stille

**Symptom:** Aufnahme funktioniert, aber WAV-Datei ist leer

**Checkliste:**
1. **Input-Gerät gewählt?**
   - Edit → Audio Settings → Input Device
   
2. **Input-Level?**
   ```bash
   # Input-Pegel visuell prüfen
   pavucontrol  # PulseAudio Volume Control
   # Oder
   pw-cli info all  # PipeWire Nodes
   ```
   
3. **Berechtigungen?**
   ```bash
   # Benutzer zu audio-Gruppe
   sudo usermod -aG audio $USER
   # Neu anmelden!
   ```

4. **Recording-Service aktiv?**
   - Statusleiste: "Recording: Backend=..."

---

### Problem: Hohe CPU-Last

**Symptom:** System wird langsam, Audio knackst

**Lösungen:**

1. **Buffer-Size erhöhen**
   - Audio Settings → Buffer Size: 512 oder 1024

2. **Sample-Rate reduzieren**
   - 48000 Hz statt 96000 Hz

3. **Weniger Tracks/Plugins**
   - Tracks "Freeze" (Bounce to Audio)

4. **System-Optimierung:**
   ```bash
   # CPU-Governor auf Performance
   sudo cpupower frequency-set -g performance
   
   # Nice-Level für Audio
   sudo renice -n -19 -p $(pgrep -f python3)
   ```

---

### Problem: MIDI-Keyboard reagiert nicht

**Symptom:** Tasten werden gedrückt, aber keine Eingabe

**Lösungen:**

1. **MIDI-Gerät verbunden?**
   ```bash
   aconnect -l
   # Sollte zeigen: PyDAW und Keyboard
   ```

2. **MIDI-Settings korrekt?**
   - Edit → MIDI Settings
   - Input Device auswählen
   - "MIDI Through" aktiviert?

3. **Manual Connection** (JACK/PipeWire):
   ```bash
   # In qpwgraph:
   # Keyboard → PyDAW MIDI In verbinden
   ```

---

### Support & Community

**Bei weiteren Problemen:**

1. **Logs prüfen:**
   ```bash
   tail -f ~/.cache/ChronoScaleStudio/pydaw.log
   ```

2. **Debug-Modus:**
   ```bash
   PYDAW_LOG_LEVEL=DEBUG python3 main.py 2>&1 | tee debug.log
   ```

3. **Issue auf GitHub erstellen** (wenn vorhanden)

---

## Nächste Schritte

- **Tutorials**: [docs/tutorials/](docs/tutorials/)
- **Video-Guides**: [Link zu YouTube-Playlist]
- **API-Dokumentation**: [docs/api/](docs/api/)

**Viel Erfolg mit Py DAW!** 🎵🎹🎧
