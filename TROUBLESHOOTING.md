# 🔧 PyDAW Troubleshooting Guide

## 🔴 BEKANNTE PROBLEME & LÖSUNGEN

---

## Problem 1: Master Volume funktioniert nicht sofort

### **Symptome:**
- Master Volume Slider bewegen → Sound ändert sich NICHT
- Sound bleibt gleich laut

### **URSACHE:**
Audio Engine nutzt **Snapshot** vom Projekt beim Play-Start!
```
1. Play drücken → Snapshot erstellt (Volume = 0.80)
2. Slider bewegen → Live-Projekt ändert sich
3. Audio nutzt IMMER NOCH alten Snapshot! ❌
```

### **LÖSUNG / WORKAROUND:**
```
1. Master Volume ändern
2. ⏹️ STOP drücken
3. ▶️ PLAY nochmal drücken
4. ✅ Neue Lautstärke aktiv!
```

### **WARUM IST DAS SO?**
Realtime-Audio läuft in eigenem Thread. Direkter Zugriff auf Live-Projekt 
würde zu Race Conditions/Crashes führen. Snapshot ist sicher aber nicht Echtzeit.

**FIX KOMMT IN:** v0.1.x (Echtzeit Parameter-Messaging System)

---

## Problem 2: Pre-Render bleibt bei 0% hängen

### **Symptome:**
- "Pre-Render: 1 MIDI Clips... 0%"
- Dialog bleibt stehen
- Nichts passiert

### **MÖGLICHE URSACHEN:**

#### **A) SF2 Datei fehlt**
```
Track hat kein SoundFont → Kann nicht rendern!

LÖSUNG:
1. Track auswählen
2. Projekt → Sound Font (SF2) laden...
3. SF2 Datei auswählen
4. Nochmal Pre-Render probieren
```

#### **B) FluidSynth hängt**
```
ensure_rendered_wav() blockiert

DEBUG:
1. Terminal öffnen
2. Pre-Render starten
3. Terminal checken:
   - Fehler angezeigt?
   - "Rendering Clip 1/1..." ?
   - Timeout nach 30 Sekunden?
```

#### **C) MIDI Clip ist leer**
```
Keine Noten → Nichts zu rendern!

CHECK:
- Clip öffnen (Doppelklick)
- Piano Roll: Sind Noten da?
```

### **FIX IN v0.0.19.7.13:**
- Progress wird VOR Render emitted
- Errors werden angezeigt statt zu hängen
- "Rendering Clip X/Y..." Text

---

## Problem 3: JACK Warnings im Terminal

### **Symptome:**
```
Cannot connect to server socket err = Datei oder Verzeichnis nicht gefunden
jack server is not running or cannot be started
```

### **URSACHE:**
PyDAW versucht JACK zu connecten obwohl JACK Server nicht läuft.

### **LÖSUNG:**

#### **Option A: JACK nicht verwenden (empfohlen)**
```
→ Ignorieren! 
→ PyDAW nutzt sounddevice (PortAudio)
→ Funktioniert ohne JACK!
```

#### **Option B: JACK/PipeWire-JACK aktivieren**
```
# PipeWire-JACK (modern):
pw-jack python3 main.py

# Oder JACK Server starten:
jackd -d alsa
```

**WICHTIG:** JACK ist OPTIONAL! PyDAW funktioniert ohne!

---

## Problem 4: PC wird langsam / Lüfter springt an

### **Symptome:**
- CPU 100%
- Lüfter laut
- "Beenden/Warten" Dialog
- UI friert ein

### **URSACHE:**
v0.0.19.7.10 hatte Debug Prints im Audio Callback! ❌

### **FIX:**
✅ GEFIXT in v0.0.19.7.11!
- Alle Debug Prints entfernt
- Audio Callback optimiert
- Performance normal

**WENN IMMER NOCH LANGSAM:**
```
1. Wie viele Tracks? (>20?)
2. Wie viele Clips? (>100?)
3. Audio Files Größe? (>1GB?)

→ Screenshots + Info schicken!
```

---

## Problem 5: Track umbenennen funktioniert nicht

### **Symptome:**
- Doppelklick auf Track in Track-Liste → Nichts
- Kein Dialog

### **FIX:**
✅ GEFIXT in v0.0.19.7.10!
- Expliziter DoubleClick Handler
- QInputDialog öffnet sich jetzt

**WENN IMMER NOCH NICHT:**
```
→ Screenshot schicken!
→ Welche Track-Liste? (Links oder Mixer?)
```

---

## Problem 6: "Vor Play warten" blockiert Playback

### **Symptome:**
- Play drücken → Nichts passiert
- DAW hängt

### **FIX:**
✅ GEFIXT in v0.0.19.7.12!
- Default: FALSE (nicht mehr aktiviert)

**MANUELL DEAKTIVIEREN:**
```
1. Audio → Audio-Einstellungen...
2. "Vor Play warten..." → UNCHECKEN
3. OK
```

---

## 🧪 DEBUGGING TIPPS

### **Terminal immer offen lassen!**
```bash
python3 main.py
```
→ Zeigt Fehler, Warnings, Status

### **GDB für Crashes:**
```bash
gdb -batch -ex "run" -ex "bt" --args python3 main.py
```
→ Zeigt wo PyDAW crashed

### **Log Datei:**
```bash
cat ~/.cache/ChronoScaleStudio/pydaw.log
```
→ Enthält alle Logs

---

## 🎯 FEATURE WORKAROUNDS

### **Master Volume Echtzeit:**
```
AKTUELL: Stop+Play nach Volume-Änderung
KOMMT: v0.1.x (Lock-Free Queue System)
```

### **Track Volume Echtzeit:**
```
AKTUELL: Funktioniert! ✅
(nur Master Volume ist Snapshot-basiert)
```

### **Pre-Render Progress:**
```
AKTUELL: v0.0.19.7.13 zeigt Progress + Errors
WENN HÄNGT: SF2 fehlt oder FluidSynth Problem
```

---

## 📧 SUPPORT

**GitHub Issues:** https://github.com/YOUR_REPO/issues
**Discord:** [Link wenn vorhanden]
**Email:** support@pydaw.com

**BEI BUG REPORT BITTE MITSCHICKEN:**
1. Screenshot vom Problem
2. Terminal Output (copy/paste)
3. pydaw.log (~/.cache/ChronoScaleStudio/)
4. System Info (Linux/macOS/Windows)
5. PyDAW Version (siehe VERSION Datei)

---

**Version:** v0.0.19.7.13
**Status:** BETA - Bekannte Issues werden aktiv gefixt!
