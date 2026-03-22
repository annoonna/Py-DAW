# CHANGELOG v0.0.20.653 — CLAP Unified Presets + Multi-Output Wiring

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP4 Phase 4B (CLAP Cleanup) + AP5 Phase 5C (Multi-Output Wiring)

## Was wurde gemacht

### 1. CLAP → Unified PresetBrowserWidget (Konsistentes Look & Feel)
- Alten v0.0.20.569 Preset-Scan-Timer aus CLAP-Widget entfernt — das Unified PresetBrowserWidget
  (v652) übernimmt jetzt Refresh, Kategorien, Favoriten und A/B-Vergleich für CLAP
- Undo-Notify (`notify_param_changed()`) in CLAP `_flush_to_project()` integriert
- Legacy `_preset_combo` als Hidden-Widget erhalten (verhindert AttributeError in alten Methoden)
- CLAP-eigene Preset-Methoden (_preset_dir, _refresh_presets, _save_preset, etc.) bleiben als
  Fallback erreichbar, werden aber nicht mehr automatisch getriggert

### 2. Multi-Output Plugin Wiring im HybridAudioCallback (Kern-Feature)
- **Neues Datenfeld:** `_plugin_output_map` in `HybridAudioCallback.__slots__` + `__init__`
  - Format: `Dict[str, Dict[int, str]]` → parent_track_id → {output_idx: child_track_id}
  - Output 0 geht immer zum Parent-Track (implizit)
- **Setter-Methoden:**
  - `HybridAudioCallback.set_plugin_output_map()` — Atomic Reference Swap
  - `HybridEngineBridge.set_plugin_output_map()` — GUI→Audio Thread Bridge
- **`_mix_source_to_track()` Helper-Methode** (NEU):
  - Extrahiert aus dem alten Pull-Source-Loop: FX-Chain → Metering → Vol/Pan → Mix
  - Zero-Alloc: Nutzt pre-allokierten `_block_buf` als Scratch-Buffer
  - Wiederverwendbar für Parent-Track UND Child-Tracks
- **`render_for_jack()` Step 8 komplett umgebaut:**
  - Prüft `_pydaw_output_count` auf jedem Pull-Source
  - Single-Output (count=1): Exakt wie vorher → `_mix_source_to_track()`
  - Multi-Output (count>1): Splittet Buffer in Stereo-Paare (0:2, 2:4, 4:6, ...)
    - Output 0 → Parent-Track via `_mix_source_to_track()`
    - Output N → Child-Track via `_plugin_output_map[parent_tid][N]`
  - **100% backwards-kompatibel**: Ohne `_plugin_output_map` Einträge = alter Codepfad
- **`AudioEngine.rebuild_fx_maps()` erweitert:**
  - Neuer Block: Baut `po_map` aus `Track.plugin_output_routing` + `Track.plugin_output_count`
  - Pushed Map an Bridge: `self._hybrid_bridge.set_plugin_output_map(po_map)`
  - Taggt bestehende Pull-Sources mit `_pydaw_output_count` aus Projektdaten
- **VST3 Instrument Pull-Sources:** `_pydaw_output_count = 1` bei Registrierung gesetzt

### Bestehende Funktionalität: NICHT geändert
- Single-Output-Plugins: Identischer Codepfad (kein Overhead)
- Keine Änderungen am Project Model (nutzt bestehendes Track.plugin_output_routing aus v650)
- Keine Änderungen an der Mixer-UI
- Keine Änderungen an bestehenden FX-Chains

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| `pydaw/audio/hybrid_engine.py` | `_plugin_output_map` Slot/Init, `set_plugin_output_map()`, `_mix_source_to_track()` Helper, Multi-Output Pull-Loop, Bridge Setter |
| `pydaw/audio/audio_engine.py` | `rebuild_fx_maps()`: plugin_output_map Builder + Pull-Source Tagging, VST3 inst `_pydaw_output_count` |
| `pydaw/ui/fx_device_widgets.py` | CLAP: alten Preset-Timer entfernt, Undo-Notify in `_flush_to_project` |
| `VERSION` | 0.0.20.652 → 0.0.20.653 |
| `pydaw/version.py` | Version-String aktualisiert |

## Was als nächstes zu tun ist
- **AP7 Phase 7A — Advanced Sampler**: Multi-Sample Mapping Editor, Round-Robin
  - Sampler-Engine muss bei Multi-Output `pull()` einen (frames, 2*N) Buffer liefern
  - `_pydaw_output_count` muss vom Sampler-Engine-Registration gesetzt werden
- Optional: `render_offline` für Multi-Output (AP10 Phase 10C Vorbereitung)

## Bekannte Probleme / Offene Fragen
- Pull-Sources die Multi-Output liefern müssen (frames, 2*N) zurückgeben, nicht (frames, 2)
  → Sampler/DrumMachine Engine muss angepasst werden (AP7)
- Sounddevice-Callback (`_process`) hat noch nicht die gleiche Multi-Output-Logik
  (nur `render_for_jack` wurde umgebaut — SD-Callback nutzt meist den gleichen Pfad über JACK)
