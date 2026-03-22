# Py DAW v0.0.19.3.6_fix11 - Quick Start

## 🎉 Was wurde behoben?

### Der SIGABRT-Crash ist Geschichte!
Die Hauptursache für die Programmabstürze wurde gefunden und vollständig behoben:

**Problem**: Rekursive `notify()` Aufrufe in der Event-Loop führten zu Speicherüberlauf und SIGABRT
**Lösung**: Komplettes Refactoring der Event-Behandlung mit `event()` Override

✅ **Das Programm läuft jetzt stabil!**

---

## 🚀 Neue Features

### 1. Audio-Recording (PipeWire/JACK)
Nehmen Sie Audio direkt in der DAW auf:
- Unterstützt PipeWire, JACK und Sounddevice
- Automatische Backend-Erkennung
- Echtzeit-Recording mit niedriger Latenz

### 2. FluidSynth Integration
Hochwertige MIDI-Wiedergabe:
- Laden Sie SoundFont-Dateien (SF2)
- 16 MIDI-Kanäle
- Reverb & Chorus Effekte
- JACK/PipeWire Audio-Routing

### 3. Erweiterte Notation
Grundlagen für vollständiges Notationssystem:
- Skalen-Datenbank mit 500+ Skalen
- Basis-Notations-Editor funktioniert
- Framework für ChronoScaleStudio vorbereitet

---

## ⚡ Installation in 3 Schritten

```bash
# 1. Entpacken
unzip Py_DAW_v0.0.19.3.6_fix11.zip
cd Py_DAW_v0.0.19.3.6_fix11

# 2. Virtuelle Umgebung
python3 -m venv myenv
source myenv/bin/activate

# 3. Installieren & Starten
pip install -r requirements.txt
python3 main.py
```

---

## 🎯 Erste Schritte

### Basis-Workflow

1. **Neues Projekt**: Datei → Neu
2. **Track hinzufügen**: Rechtsklick in Track-Liste
3. **MIDI-Clip erstellen**: Stift-Tool → In Timeline klicken
4. **Noten eingeben**: Doppelklick auf Clip → Piano Roll
5. **Abspielen**: Leertaste drücken

### Audio aufnehmen

1. **Audio-Track erstellen**
2. **Input wählen**: Edit → Audio Settings
3. **Record aktivieren**: Rote Taste [●]
4. **Play drücken**: Aufnahme läuft!

### FluidSynth verwenden

1. **SoundFont laden**: Audio → FluidSynth → Load SoundFont
2. **MIDI-Clip erstellen**
3. **Track-Output**: FluidSynth wählen
4. **Play**: Genießen Sie den Sound!

---

## 📋 System-Anforderungen

### Minimum
- Linux (Debian 11+, Ubuntu 20.04+, Arch, Fedora 35+)
- Python 3.9+
- 4 GB RAM
- Dual-Core CPU

### Empfohlen
- Linux mit PipeWire
- Python 3.11+
- 8 GB RAM
- Quad-Core CPU

---

## 🛠️ Optionale Pakete

```bash
# FluidSynth
pip install pyfluidsynth

# JACK Backend
pip install JACK-Client

# Recording
pip install numpy sounddevice
```

---

## 📖 Dokumentation

- **README.md** - Übersicht & Features
- **docs/USER_GUIDE.md** - Vollständiges Handbuch
- **CHANGELOG.md** - Alle Änderungen
- **docs/HANDOVER.md** - Entwickler-Dokumentation

---

## 🐛 Bekannte Probleme & Lösungen

### "ModuleNotFoundError"
```bash
# Virtuelle Umgebung aktivieren!
source myenv/bin/activate
```

### Kein Sound
```bash
# Backend prüfen
Edit → Audio Settings → Backend: sounddevice

# PipeWire-Status
systemctl --user status pipewire
```

### MIDI-Keyboard reagiert nicht
```bash
# MIDI-Gerät verbinden
aconnect -l

# Settings
Edit → MIDI Settings → Input Device wählen
```

---

## 💡 Tipps

### Performance optimieren
- Buffer-Size: 512 Samples (Audio Settings)
- Sample-Rate: 48000 Hz
- CPU-Governor: Performance-Modus

### Shortcuts
- `Leertaste`: Play/Pause
- `R`: Record
- `Strg+Z`: Undo
- `Strg+S`: Speichern

### qpwgraph verwenden
```bash
qpwgraph &
```
Visualisieren Sie Audio-Verbindungen zwischen PyDAW und System.

---

## 🎓 Weitere Ressourcen

### Kostenlose SoundFonts
```bash
# FluidR3_GM (General MIDI)
sudo apt install fluid-soundfont-gm
# Datei: /usr/share/sounds/sf2/FluidR3_GM.sf2
```

### PipeWire optimieren
```bash
# Latenz reduzieren
pw-metadata -n settings 0 clock.force-quantum 256
```

---

## 🙏 Danke

Vielen Dank für die Verwendung von Py DAW!

Bei Fragen oder Problemen:
- Logs prüfen: `~/.cache/ChronoScaleStudio/pydaw.log`
- Debug-Modus: `PYDAW_LOG_LEVEL=DEBUG python3 main.py`

**Viel Erfolg beim Musik machen!** 🎵

---

**Version**: 0.0.19.3.6_fix11  
**Datum**: 2026-01-30  
**Status**: ✅ Stabil & Produktionsbereit
