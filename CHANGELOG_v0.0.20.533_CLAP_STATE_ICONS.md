# CHANGELOG v0.0.20.533 — CLAP State Save/Load + Browser Icons Fix

**Datum:** 2026-03-16
**Entwickler:** Claude Opus 4.6
**Typ:** Feature + Bugfix

---

## Problem 1: CLAP Browser Icons fehlten
**Vorher:** Alle CLAP-Plugins hatten das gleiche generische Symbol im Browser — keine Unterscheidung Instrument vs. Effect.
**Fix:** `scan_clap()` liest jetzt `is_instrument` aus den CLAP-Features und gibt es an `ExtPlugin` weiter. Nach Rescan zeigen CLAP-Plugins 🎹 (Instrument) oder 🔊 (Effect).

## Problem 2: CLAP State ging bei Projekt-Reload verloren
**Vorher:** Surge XT und andere CLAP-Plugins verloren alle Preset-Einstellungen beim Speichern/Laden.
**Fix:** Komplette `clap.state` Extension Implementation:

### Datenfluss beim Speichern:
```
Projekt speichern → embed_clap_project_state_blobs()
  → findet laufende ClapFx/ClapInstrumentEngine in AudioEngine
  → ruft get_state_b64() → _ClapPlugin.get_state()
  → clap.state.save(plugin, ostream) → _MemoryOutputStream.data
  → base64.b64encode → params["__ext_state_b64"] in Projekt-JSON
```

### Datenfluss beim Laden:
```
Projekt laden → ChainFx._compile_devices() → ClapFx(params=...)
  → ClapFx._load() → prüft params["__ext_state_b64"]
  → base64.b64decode → _ClapPlugin.set_state(bytes)
  → clap.state.load(plugin, istream) → Plugin-State wiederhergestellt
```

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `pydaw/audio/clap_host.py` | +200 Zeilen: State-Extension, Streams, Save/Load, Embed |
| `pydaw/services/plugin_scanner.py` | is_instrument Fix für CLAP |
| `pydaw/services/project_service.py` | CLAP embed hooks in save_project_as + save_snapshot |

## Nichts kaputt gemacht ✅
- VST2/VST3 State-Persistenz unverändert
- CLAP Audio-Processing unverändert
- CLAP GUI-Embedding unverändert
- Alle anderen Plugin-Formate unberührt
