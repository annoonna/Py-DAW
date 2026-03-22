# 🎯 CLIP LAUNCHER MASTER PLAN (Bitwig/Ableton-Grade)

**Stand:** v0.0.20.149 (2026-02-28)
**Ziel:** Clip Launcher wie Bitwig Studio / Ableton Live

## ✅ UPDATE v0.0.20.149
- Grid-Orientierung jetzt **Bitwig-Style**: **Scenes = Spalten**, **Tracks = Zeilen**.
- Track-Header (Name + M/S/R) direkt im Grid.
- Slot-Zellen zeigen Clip-Farb-Tint (aus `clip.launcher_color`).

## 📊 FEATURE-VERGLEICH

| Feature | Bitwig | Ableton | PyDAW v147 | Status |
|---------|--------|---------|------------|--------|
| Grid (Scenes × Tracks) | ✅ | ✅ | ✅ | ✅ DONE |
| Slot Waveform Preview | ✅ | ✅ | ✅ | ✅ DONE |
| Scene Launch Buttons | ✅ | ✅ | ✅ | ✅ DONE |
| Drag & Drop (Slots) | ✅ | ✅ | ✅ | ✅ DONE |
| Quantized Launch | ✅ | ✅ | ✅ | ✅ DONE |
| Stop All | ✅ | ✅ | ✅ | ✅ DONE |
| Audio Playback (Looped) | ✅ | ✅ | ✅ | ✅ DONE |
| MIDI Playback | ✅ | ✅ | ✅ basic | ✅ DONE |
| **ZELLE Inspector Panel** | ✅ | ✅ (Clip View) | ✅ | ✅ DONE (v147) |
| Inspector resizable/collapsible | ✅ | ✅ | ✅ | ✅ DONE (v148) |
| **Per-Clip Color** | ✅ | ✅ | ✅ | ✅ DONE (v147) |
| **Per-Clip Quantize** | ✅ | ✅ | ✅ basic | 🚧 Phase 2 |
| **Main/ALT Quantize** | ✅ | ❌ | 🔲 UI only | 🚧 Phase 2 |
| **Playback Modes** | ✅ | ✅ | 🔲 Model only | 🚧 Phase 2 |
| **Release Actions** | ✅ | ❌ | 🔲 Model only | 🚧 Phase 2 |
| **Next Action System** | ✅ | ✅ (Follow Actions) | 🔲 Model only | 🚧 Phase 3 |
| **Shuffle/Accent** | ✅ | ❌ | 🔲 Model only | 🚧 Phase 3 |
| Play State Indicators | ✅ | ✅ | ❌ | 🔲 Phase 2 |
| Stop Button per Track | ✅ | ✅ | ❌ | 🔲 Phase 2 |
| Record into Launcher | ✅ | ✅ | ❌ | 🔲 Phase 4 |
| Capture to Arranger | ✅ | ✅ | ❌ | 🔲 Phase 4 |
| Clip Aliases | ✅ v6 | ❌ | ❌ | 🔲 Phase 5 |
| Comping Takes | ✅ | ✅ | ❌ | 🔲 Phase 5 |

## 🏗️ PHASEN-PLAN

### Phase 1: ZELLE Inspector UI ✅ DONE (v0.0.20.147)
**Was:** Bitwig-Style ZELLE Panel als linke Sidebar im Clip Launcher
**Dateien:**
- `pydaw/ui/clip_launcher_inspector.py` (NEU)
- `pydaw/model/project.py` (erweitert: per-Clip Properties)
- `pydaw/ui/clip_launcher.py` (refactored: Splitter Layout)
- `pydaw/services/launcher_service.py` (erweitert: per-Clip Quantize)

---

### Phase 2: Playback Engine + Visual Feedback [ ] AVAILABLE
**Aufwand:** ~4-6h
**Priorität:** 🔴 HIGH

#### Task 2.1: Play State Indicators [ ] AVAILABLE
- Slot-Buttons visuell markieren: ▶ grün = playing, ⏳ gelb = queued, ⬛ = stopped
- `ClipLauncherPlaybackService` exposes active voices → UI polls or signals
- SlotWaveButton.paintEvent: Rahmenfarbe basierend auf Play-State

#### Task 2.2: Per-Clip Quantize Engine [ ] AVAILABLE
- `_get_effective_quantize()` erweitern: echte Multi-Bar Quantisierung
- 8 Takte / 4 Takte / 2 Takte als `ceil(beat / (bpb * N)) * bpb * N`
- 1/2, 1/4, 1/8, 1/16 Noten als fractional-beat Quantize

#### Task 2.3: Playback Modes [ ] AVAILABLE
- **Trigger ab Start**: Standard (wie jetzt) — Clip startet von Anfang
- **Legato vom Clip**: Clip übernimmt Position des vorherigen Clips auf derselben Spur
- **Legato vom Projekt**: Clip startet relativ zur globalen Transport-Position
- Implementation in `ClipLauncherPlaybackService._start_voice()`:
  - Bei Legato: `start_beat` = current_beat - (current_beat % clip_length)

#### Task 2.4: Stop Button per Track [ ] AVAILABLE
- Unter jedem Track-Header: ■ Stop-Button
- Stoppt alle aktiven Clips auf dieser Spur
- `ClipLauncherPlaybackService.stop_track(track_id)`

---

### Phase 3: Release Actions + Next Actions [ ] AVAILABLE
**Aufwand:** ~4-6h
**Priorität:** 🟡 MEDIUM

#### Task 3.1: Release Actions [ ] AVAILABLE
- **Fortsetzen**: Clip spielt weiter nach Loslassen (Gate-Mode analog)
- **Stopp**: Clip stoppt sofort
- **Zurück**: Vorheriger Clip auf dieser Spur wird wieder aktiviert
- **Nächste Aktion**: Führt die "Nächste Aktion" aus
- Implementation: `LauncherService` trackt "previous voice per track"

#### Task 3.2: Next Action System [ ] AVAILABLE
- Nach N Wiederholungen (`launcher_next_action_count`) wird automatisch:
  - **Nächsten abspielen**: Nächster Slot in derselben Spalte
  - **Vorherigen abspielen**: Vorheriger Slot
  - **Zufälligen abspielen**: Random Slot aus der Spalte
  - **Round-robin**: Sequentiell durch alle Slots
  - **Zum Arrangement zurückkehren**: Clip Launcher stoppt, Arranger übernimmt
- Implementation: `ClipLauncherPlaybackService` braucht Loop-Counter pro Voice
- Bei Loop-Ende: Counter++, wenn Counter >= count → fire next action

---

### Phase 4: Recording & Capture [ ] AVAILABLE
**Aufwand:** ~6-8h
**Priorität:** 🟡 MEDIUM

#### Task 4.1: Record into Empty Slot [ ] AVAILABLE
- Record-Arm Button pro Track
- Klick auf leeren Slot → Recording startet (Audio oder MIDI)
- Audio: Ring-Buffer schreibt in WAV
- MIDI: Notes werden gesammelt, bei Quantize-Punkt in Clip geschrieben

#### Task 4.2: Capture to Arranger [ ] AVAILABLE
- Global Record + Transport aktiv + Clips triggern
- Ergebnis wird auf Arranger Timeline geschrieben
- Clip-Boundaries respektieren Quantize-Grid

---

### Phase 5: Advanced Features [ ] AVAILABLE
**Aufwand:** ~8-12h
**Priorität:** 🔵 LOW

#### Task 5.1: Comping Takes [ ] AVAILABLE
- Cycle Recording: Leere Slots werden nacheinander aufgenommen
- Take-Länge konfigurierbar

#### Task 5.2: Clip Aliases [ ] AVAILABLE
- Drag als Alias statt Copy
- Shared Pattern: Edit one → alle Aliases updaten
- "Make Unique" zum Trennen

---

## 📐 ARCHITEKTUR

```
┌─────────────────────────────────────────────────────────┐
│                    ClipLauncherPanel                     │
│  ┌──────────────┐  ┌──────────────────────────────────┐ │
│  │  Inspector   │  │         Grid (Scenes × Tracks)   │ │
│  │  (ZELLE)     │  │  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐      │ │
│  │              │  │  │S1│ │  │ │  │ │▶ │ │  │ Scene1 │ │
│  │ ┌──────────┐ │  │  ├──┤ ├──┤ ├──┤ ├──┤ ├──┤      │ │
│  │ │Clip Name │ │  │  │S2│ │  │ │▶ │ │  │ │  │ Scene2 │ │
│  │ │Color Pad │ │  │  ├──┤ ├──┤ ├──┤ ├──┤ ├──┤      │ │
│  │ │Takt/Loop │ │  │  │S3│ │  │ │  │ │  │ │  │ Scene3 │ │
│  │ │Quantize  │ │  │  └──┘ └──┘ └──┘ └──┘ └──┘      │ │
│  │ │Playback  │ │  │  [■]  [■]  [■]  [■]  [■] Stops  │ │
│  │ │Release   │ │  └──────────────────────────────────┘ │
│  │ │Next Act. │ │                                       │
│  │ │Audio Evt │ │                                       │
│  │ │Expressions│ │                                       │
│  │ └──────────┘ │                                       │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
  ClipContextService      LauncherService
         │                        │
         ▼                        ▼
   ProjectService ◄──── ClipLauncherPlaybackService
         │                        │
         ▼                        ▼
    Project Model           AudioEngine
   (Clip + new fields)    (pull-source mixing)
```

## 📋 DATENMODELL (v0.0.20.147)

### Clip (erweitert)
```python
# Per-Clip Launcher Properties
launcher_start_quantize: str = "Project"      # "Project"|"Off"|"1 Bar"|...
launcher_alt_start_quantize: str = "Project"   # ALT-Variante
launcher_playback_mode: str = "Trigger ab Start"
launcher_alt_playback_mode: str = "Trigger ab Start"
launcher_release_action: str = "Stopp"
launcher_alt_release_action: str = "Stopp"
launcher_q_on_loop: bool = True
launcher_next_action: str = "Stopp"
launcher_next_action_count: int = 1
launcher_shuffle: float = 0.0
launcher_accent: float = 0.0
launcher_seed: str = "Random"
launcher_color: int = 0
```

### Project (unverändert)
```python
clip_launcher: Dict[str, str]          # slot_key -> clip_id
launcher_quantize: str = "1 Bar"       # Global quantize
launcher_mode: str = "Trigger"         # Global mode
```

## 🔧 DATEIEN-ÜBERSICHT

| Datei | Beschreibung | Zeilen |
|-------|-------------|--------|
| `pydaw/ui/clip_launcher.py` | Haupt-Panel (Grid + Inspector) | ~700 |
| `pydaw/ui/clip_launcher_inspector.py` | ZELLE Inspector (NEU) | ~530 |
| `pydaw/ui/clip_launcher_overlay.py` | DnD Overlay | ~320 |
| `pydaw/services/launcher_service.py` | Quantized Launch Logic | ~160 |
| `pydaw/services/cliplauncher_playback.py` | Audio Playback Engine | ~610 |
| `pydaw/services/clip_context_service.py` | Slot Context Broadcast | ~175 |
| `pydaw/model/project.py` | Datenmodell (Clip + Launcher) | ~310 |


---

## ✅ Implementiert (Stand v0.0.20.152)

- Bitwig-Style Grid: Scenes=Spalten, Tracks=Zeilen
- Slot Play-State: Highlight + ▶
- Slot/Scene Queued-State: gelb/gestrichelt + Triangle-Outline
- **Queued Countdown**: Slot/Scene zeigt live `0.5 Bar` / `0.2 Beat` bis zum Fire-Beat

### UI-Datenquelle
- `LauncherService.pending_snapshot()` liefert: `kind`, `key`, `at_beat`, `quantize`
- UI rechnet `remaining = at_beat - transport.current_beat`

### Nächste Engine-Stufe
- Release/Next Actions aus dem Inspector tatsächlich ausführen (Stop/Return/Next/Random/etc.)
