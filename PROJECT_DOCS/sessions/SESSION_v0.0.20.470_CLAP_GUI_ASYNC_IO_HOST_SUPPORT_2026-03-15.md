# Session v0.0.20.470 — CLAP GUI Async-IO Host Support

**Datum:** 2026-03-15  
**Entwickler:** OpenAI GPT-5.4 Thinking  
**Ausgangsversion:** v0.0.20.469  
**Zielversion:** v0.0.20.470

## Ziel

Den nächsten kleinen, sicheren Schritt gegen das weiterhin leere Surge-XT-CLAP-GUI gehen — ohne Audio-Thread, DSP, Routing oder Parameterfluss anzufassen.

## Beobachtung

- `create_gui()` meldet lokal weiterhin Erfolg.
- Das Editorfenster öffnet sich, bleibt aber dunkel/leer.
- Der Fehler liegt damit sehr wahrscheinlich weiterhin im nativen GUI-Lifecycle und nicht im Audio-/Device-Pfad.

## Umsetzung

### 1. CLAP-Host erweitert

In `pydaw/audio/clap_host.py` ergänzt:

- `CLAP_EXT_POSIX_FD_SUPPORT`
- `CLAP_EXT_TIMER_SUPPORT`
- ctypes-Definitionen für Plugin-/Host-Strukturen beider Extensions
- Host-Callbacks zum Registrieren/Ändern/Entfernen von GUI-FDs
- Host-Callbacks zum Registrieren/Entfernen von GUI-Timern

Pro `_ClapPlugin` werden jetzt gespeichert:

- registrierte GUI-FDs
- registrierte GUI-Timer
- optionale Dispatch-Methoden `dispatch_gui_fd()` / `dispatch_gui_timer()`

### 2. Qt-Bridge nur für offenen Editor

In `pydaw/ui/fx_device_widgets.py` ergänzt:

- `QSocketNotifier`-basierte Spiegelung registrierter CLAP-GUI-FDs
- `QTimer`-basierte Spiegelung registrierter CLAP-GUI-Timer
- automatisches Re-Syncing während `_pump_editor_gui()`
- sauberes Aufräumen aller Async-Quellen beim Schließen des Editors

### 3. Risikoarm gehalten

Nicht geändert:

- kein Eingriff in `process()`
- kein Eingriff in Audio-Callback / Engine-Routing
- kein Umbau von Instrument-/FX-Erkennung
- keine Änderung an MIDI-/Automation-Logik

## Validierung

```bash
python -m py_compile pydaw/audio/clap_host.py pydaw/ui/fx_device_widgets.py
```

Ergebnis: **erfolgreich**.

## Nächster sinnvoller Schritt

Falls Surge XT lokal weiterhin leer bleibt:

- optionalen Floating-Window-Fallback nur für problematische CLAP-GUIs bauen
- dabei Embedded-Standardpfad unangetastet lassen
- keine generelle Verhaltensänderung für funktionierende CLAPs erzwingen
