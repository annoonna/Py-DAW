# Session Log: v0.0.20.406 — MIDI Multi-Device + Mapping + Plugin Browser Fix

**Datum:** 2026-03-12
**Entwickler:** Claude Opus 4.6
**Start-ZIP:** Py_DAW_v0_0_20_405_TEAM_READY.zip
**Ergebnis-ZIP:** Py_DAW_v0_0_20_406_TEAM_READY.zip

## Probleme (von Anno gemeldet)

1. **Nur ein MIDI-Gerät gleichzeitig verbindbar** — nanoKEY2 + nanoKONTROL2 sollten beide gehen
2. **MIDI Mapping (Ctrl+K) funktioniert nicht mehr** — Dialog öffnet sich nicht
3. **MIDI Learn (Rechtsklick-Menü) funktioniert nicht** — hängt zusammen mit Bug 1+2
4. **Plugin Browser Instrument/Effect Trennung kaputt** — 🎹/🔊 Icons fehlen

## Fixes

### Fix 1: MIDI Mapping Dialog (Ctrl+K) — Kritischer Bug
**Datei:** `pydaw/ui/main_window.py`
**Problem:** `_show_midi_mapping()` übergab `self.services.midi` als erstes Argument an `MidiMappingDialog`, aber der Dialog erwartet `(project: ProjectService, mapping: MidiMappingService, parent)`. Ergebnis: TypeError → Dialog öffnet sich nie.
**Fix:** Korrekter Aufruf: `MidiMappingDialog(self.services.project, self.services.midi_mapping, parent=self)`

### Fix 2: Multi-MIDI Device Support
**Dateien:** `pydaw/services/midi_manager.py`, `pydaw/ui/midi_settings_dialog.py`
**Problem:** `MidiManager` hatte nur ein `_in_port` (Singular). `connect_input()` machte `disconnect_input()` vor jedem neuen Connect → nur 1 Gerät möglich.
**Fix:**
- `_in_port` / `_in_name` / `_thread` ersetzt durch `_inputs: Dict[str, Dict]` (Name → {port, thread, stop})
- Jedes verbundene Gerät bekommt eigenen Reader-Thread
- Alle Threads schreiben in die gleiche `_queue` → Qt-Thread verarbeitet alles
- `connect_input()` disconnected NICHT mehr das vorherige Gerät
- `disconnect_input(name)` trennt ein spezifisches Gerät, `disconnect_input()` (ohne Arg) trennt alle
- `connected_inputs()` → Liste aller verbundenen Ports
- `inputs_changed` Signal für UI-Refresh
- Neues `MidiSettingsDialog`: QListWidget mit Checkboxen statt QComboBox → Mehrfachauswahl

### Fix 3: Plugin Browser 🎹/🔊 Instrument/Effect Trennung
**Dateien:** `pydaw/services/plugin_scanner.py`, `pydaw/ui/plugins_browser.py`
**Problem:** `ExtPlugin` hatte kein `is_instrument` Feld. Plugin Browser zeigte alles gemischt ohne Typ-Info.
**Fix:**
- `ExtPlugin.is_instrument: bool = False` hinzugefügt (backwards-kompatibel)
- Cache Load/Save berücksichtigt neues Feld
- `scan_vst2()` nutzt jetzt `is_vst2_instrument()` aus `vst2_host.py` (subprocess-basiert, crash-sicher)
- Plugin Browser zeigt 🎹/🔊 Icons vor jedem Plugin-Namen
- Neuer Filter-Dropdown: "All" / "🎹 Instruments" / "🔊 Effects"

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/services/midi_manager.py` | Multi-Device Support (Dict statt Single Port) |
| `pydaw/ui/midi_settings_dialog.py` | Komplett neu: QListWidget mit Checkboxes |
| `pydaw/ui/main_window.py` | Fix _show_midi_mapping() Argumente |
| `pydaw/services/plugin_scanner.py` | is_instrument Feld + VST2 Instrument Detection |
| `pydaw/ui/plugins_browser.py` | 🎹/🔊 Icons + Instrument/Effect Filter |
| `VERSION` | 0.0.20.406 |

## Nicht verändert (NICHTS KAPUTT GEMACHT)
- Audio Engine (audio_engine.py, hybrid_engine.py)
- FX Chain (fx_chain.py)
- VST2/VST3 Host (vst2_host.py, vst3_host.py)
- Sampler (sampler_engine.py, sampler_widget.py)
- Automation System (automatable_parameter.py)
- MIDI Mapping Service (midi_mapping_service.py) — war nicht kaputt, nur der Aufruf
- Container Wiring (container.py)

## Test-Hinweise für Anno
1. `Audio → MIDI Settings` öffnen → beide nanoKEY2 + nanoKONTROL2 anhaken → "Verbinden"
2. `Audio → MIDI Mapping` (Ctrl+K) → sollte jetzt Dialog mit Track-Auswahl öffnen
3. Rechtsklick auf Sampler-Knob → MIDI Learn → Regler am Controller bewegen
4. Plugins Tab → neuer Filter "All / 🎹 Instruments / 🔊 Effects"
5. VST2 Plugins zeigen jetzt 🎹 oder 🔊 Icons (nach Rescan)
