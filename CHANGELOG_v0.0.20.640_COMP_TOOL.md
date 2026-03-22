# CHANGELOG v0.0.20.640 — Comp-Tool (AP2 Phase 2D Abschluss)

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP2, Phase 2D — Comping / Take-Lanes (Abschluss)

## Was wurde gemacht

### 1. TakeService — Comp-Methoden
- `set_comp_region(track_id, start, end, clip_id, crossfade)` — setzt einen Comp-Bereich
  - Non-destructive Split/Trim bei überlappenden Regionen (last-write-wins)
  - Sortierung nach start_beat
- `get_comp_regions(track_id)` — alle Comp-Regionen eines Tracks
- `clear_comp_regions(track_id)` — alle Regionen löschen
- `get_active_clip_at_beat(track_id, beat)` — welcher Clip spielt an Position X?
  - Prüft erst CompRegions, dann Fallback auf aktiven Take
- `comp_select_take_at(track_id, clip_id)` — Convenience: ganzen Take als Comp-Region wählen
- `_find_track()` — interner Helper

### 2. Datenmodell
- `Track.comp_regions: List[Dict]` — persistierte Comp-Regionen (start_beat, end_beat, source_clip_id, crossfade_beats)
- Backward-kompatibel (leere Liste als Default)

### 3. Arranger — Comp Interaktion
- `_hit_take_lane_clip(pos)` — Hit-Test für inaktive Takes in Take-Lanes
- Klick auf Take-Lane-Clip → `comp_select_take_at()` → Take wird für seine Beat-Region aktiv
- Status-Message: "Comp: Take 'X' ausgewählt"

### 4. Arranger — Comp-Region Visualisierung
- Farbige Balken (4px) am oberen Rand der Track-Lane zeigen aktive Comp-Regionen
- 5 Farben rotierend pro Clip-ID (grün, blau, gold, lila, orange)
- Nur gerendert wenn comp_regions vorhanden

## AP2 Phase 2D — KOMPLETT ✅
Alle 5 Tasks abgeschlossen:
1. ✅ Loop-Recording (v0.0.20.639)
2. ✅ Take-Lanes im Arranger (v0.0.20.639)
3. ✅ Comp-Tool (v0.0.20.640)
4. ✅ Flatten (v0.0.20.639)
5. ✅ Take-Management (v0.0.20.639)

## AP2 — KOMPLETT ✅
Alle 4 Phasen abgeschlossen:
- Phase 2A: Single-Track Recording (v0.0.20.632)
- Phase 2B: Multi-Track Recording (v0.0.20.636)
- Phase 2C: Punch In/Out (v0.0.20.637–638)
- Phase 2D: Comping / Take-Lanes (v0.0.20.639–640)

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/services/take_service.py | Comp-Methoden: set/get/clear/select |
| pydaw/model/project.py | Track.comp_regions Feld |
| pydaw/ui/arranger_canvas.py | Take-Lane Klick, Comp-Region Rendering |
| pydaw/version.py | → 0.0.20.640 |
| VERSION | → 0.0.20.640 |

## Was als nächstes zu tun ist
Gemäß Roadmap-Priorität: **AP5 (Routing) → AP4 (Plugins) → AP3 (Warp)**
- AP5 Phase 5A — Send/Return Tracks
- AP3 Phase 3A — Warp-Marker System

### 5. Visuelles Routing im Mixer (AP5 Phase 5A) — BONUS
- `_RoutingOverlay` QWidget: Transparentes Overlay auf dem Mixer-ScrollArea
- Bezier-Kurven von Source-Strip zum FX-Target-Strip
- Farbkodiert pro FX-Track (8 Farben rotierend)
- Opacity proportional zum Send-Amount (0% → transparent, 100% → voll)
- Kleiner Punkt am Ziel-Strip
- `_update_routing_overlay()` in MixerPanel.refresh() — berechnet Positionen aus Strip-Geometrie

### AP5 Phase 5A — KOMPLETT ✅ (bereits v527–529 + v640 Routing-Lines)
