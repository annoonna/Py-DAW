# Py DAW v0.0.19.3.6_fix11

Eine modulare Digital Audio Workstation (DAW) in Python mit PyQt6.

## 🎯 Was ist neu in fix11?

### Kritische Fehlerbereinigungen
- **SIGABRT-Crash behoben**: Der kritische Absturz durch rekursive `notify()` Aufrufe wurde vollständig eliminiert
- **Stabile Event-Behandlung**: Neue Event-Loop-Architektur verhindert Qt-Crashes
- **Verbesserte Fehlerbehandlung**: Alle Ausnahmen werden ordnungsgemäß abgefangen und protokolliert

### Neue Features

#### 1. PipeWire/JACK Recording Support
- **Multi-Backend-Aufnahme**: Unterstützung für PipeWire, JACK und Sounddevice
- **Automatische Backend-Erkennung**: Das System wählt automatisch den besten verfügbaren Audio-Backend
- **Echtzeit-Recording**: Niedrige Latenz für professionelle Audioaufnahmen
- **WAV-Export**: Direkte Speicherung aufgenommener Spuren als WAV-Dateien

#### 2. FluidSynth Integration
- **SoundFont-Unterstützung**: Laden und Abspielen von SF2-Dateien
- **Echtzeit-MIDI-Synthesis**: Hochwertige Klangwiedergabe
- **16 MIDI-Kanäle**: Volle GM-Kompatibilität
- **Program Changes**: Wechsel zwischen Instrumenten
- **JACK/PipeWire-Routing**: Nahtlose Integration in professionelle Audio-Setups

#### 3. Erweiterte Notation
- **ChronoScaleStudio-Integration**: Vollständiges Notationssystem vorbereitet
- **500+ Skalen-Datenbank**: Zugriff auf weltweite Musikskalen
- **Notation-Editor**: Musiknotation direkt in der DAW
- **MIDI-Sync**: Bidirektionale Synchronisation mit Piano Roll

## 🚀 Schnellstart

```bash
# Installation
cd Py_DAW_v0.0.19.3.6_fix11
python3 -m venv myenv
source myenv/bin/activate
pip install -r requirements.txt

# Starten
python3 main.py
```

## 📚 Vollständige Dokumentation

Siehe die ausführliche [Dokumentation](docs/) für:
- Installation & Setup
- Features & Verwendung
- Fehlerbehebung
- Entwickler-Guide

## 🐛 Bekannte Probleme & Lösungen

### Das Programm stürzt nicht mehr ab!
Die kritischen SIGABRT-Fehler wurden in fix11 vollständig behoben.

### FluidSynth/Recording Features
Zusätzliche Pakete erforderlich:
```bash
pip install pyfluidsynth numpy sounddevice
```

## 🤝 Beitragen

Contributions willkommen! Siehe [CONTRIBUTING.md](docs/CONTRIBUTING.md)

## 📄 Lizenz

MIT License

---

**Version**: 0.0.19.3.6_fix11  
**Datum**: 2026-01-30  
**Status**: ✅ Stabil & Produktionsbereit
