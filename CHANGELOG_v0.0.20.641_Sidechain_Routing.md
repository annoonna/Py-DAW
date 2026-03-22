# CHANGELOG v0.0.20.641 — Sidechain Routing + Routing Matrix (AP5 Phase 5B+5C)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP5, Phase 5B — Sidechain-Routing + Phase 5C — Routing-Matrix

## Was wurde gemacht

### AP5 Phase 5B — Sidechain-Routing (KOMPLETT ✅ 4/4 Tasks)

1. **Track-Datenmodell**: `Track.sidechain_source_id` (str)
2. **Hybrid Engine**: `_sidechain_map`, `set_sidechain_map()`, SC-Buffer in Render-Loop (Normal/Group/FX)
3. **FX Chain API**: `ChainFx._sidechain_buf`, `set_sidechain_buffer()` für Devices
4. **Audio Engine Push**: SC-Map in `_push_to_hybrid_bridge()`
5. **Mixer UI**: SC ComboBox + Orange Label-Indikator
6. **Routing Overlay**: Orange gestrichelte Bezier-Linien + Diamant-Marker
7. **SC Routing Matrix Dialog**: Grid-Ansicht, Radio-Style, "SC Matrix" Button

### AP5 Phase 5C — Routing-Matrix (3/4 Tasks)

1. **Patchbay Dialog**: `PatchbayDialog(QDialog)` — Komplett-Übersicht aller Routing-Verbindungen
   - Output-Routing, Sends (read-only), Sidechain, Channel Config pro Track
   - Erreichbar über "Patchbay" Button im Mixer-Header
2. **Output Routing**: `Track.output_target_id` — Track kann zu Group/Bus geroutet werden
   - Output ComboBox in MixerStrip (→M / →GroupName)
   - `audio_engine.py` erweitert `set_group_bus_map()` um `output_target_id`
3. **Mono/Stereo Track Config**: `Track.channel_config` ("stereo"|"mono")
   - Channel ComboBox in MixerStrip (St/Mo)
   - `HybridEngineBridge`: `_channel_config_map`, `set_channel_config_map()`
   - Mono-Summing: `(L+R)*0.5` vor Vol/Pan-Anwendung

**Noch offen in Phase 5C:** Multi-Output Plugins (z.B. Drum-Sampler → separate Outputs)
→ Benötigt AP4 (Plugin-Hosting Robustheit) als Voraussetzung

### AP3 Phase 3A — Warp-Marker System (KOMPLETT ✅ 4/4 Tasks)

1. **WarpMarker Dataclass**: `WarpMarker(src_beat, dst_beat, is_anchor)` im Datenmodell
2. **Beat-Detection**: `detect_beat_positions()` in `bpm_detect.py` — Essentia RhythmExtractor2013 + Autocorr-Fallback
3. **Auto-Warp Service**: `ProjectService.auto_detect_warp_markers()` — Beats erkennen → Marker setzen, `clear_warp_markers()`
4. **Audio Editor Verdrahtung**: Kontextmenü "Warp Markers" → "Auto-Detect Warp Markers" + "Clear Warp Markers"
5. **Manuelle Marker**: Existierte bereits (Doppelklick in Stretch-Overlay)
6. **Elastic Stretch**: Existierte bereits (_apply_warp_markers in arrangement_renderer)

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| pydaw/model/project.py | WarpMarker dataclass, `sidechain_source_id`, `channel_config`, `output_target_id` |
| pydaw/audio/hybrid_engine.py | SC-Map, Channel-Config-Map, Mono-Summing, SC-Buffer in Render ×3 |
| pydaw/audio/fx_chain.py | `ChainFx._sidechain_buf`, `set_sidechain_buffer()` |
| pydaw/audio/audio_engine.py | SC-Map Push, Channel-Config Push, Output-Target in Group-Bus-Map |
| pydaw/audio/bpm_detect.py | `BeatPositions`, `detect_beat_positions()` |
| pydaw/services/project_service.py | `auto_detect_warp_markers()`, `clear_warp_markers()` |
| pydaw/ui/mixer.py | SC ComboBox, Ch/Output ComboBox, SC Matrix Dialog, Patchbay Dialog, Routing Overlay SC-Linien |
| pydaw/ui/audio_editor/audio_event_editor.py | Warp Markers Kontextmenü + Handler |
| pydaw/version.py | 0.0.20.641 |
| VERSION | 0.0.20.641 |

## Was als nächstes zu tun ist
- AP3 Phase 3B — Stretch-Modi (Beats/Tones/Texture/Re-Pitch)
- AP5 Phase 5C Task 3: Multi-Output Plugins (benötigt AP4)
- AP4 Phase 4A — Sandboxed Plugin-Hosting

## Bekannte Probleme / Offene Fragen
- Sidechain-Buffer: Pre-Fader Audio des Source-Tracks. Render-Reihenfolge bestimmt Latenz (0 oder 1 Block, ~5-10ms — akzeptabel).
- Multi-Output Plugins (Phase 5C Task 3): Benötigt AP4 Plugin-Hosting als Voraussetzung.
- DSP-Devices (Compressor, Gate) die den Sidechain-Buffer nutzen: Teil von AP8 (Built-in FX). Die API ist bereit.
- Beat-Detection Qualität hängt von Essentia-Installation ab. Fallback (Autocorr) ist ungenauer.
