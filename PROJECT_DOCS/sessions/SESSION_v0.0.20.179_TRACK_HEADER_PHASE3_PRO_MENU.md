# Session: v0.0.20.179 — Phase 3: Track-Header ▾ PRO (Favorites/Recents + Search + Mini-Icons) + Hotfix

## Ziel
- Track-Header ▾ System noch „pro-er“ machen (weiterhin **komplett additiv**, kein Workflow-Bruch):
  1) **Favorites/Recents** direkt im Track-▾ Menü (1‑Klick Insert)
  2) **Add Device Untermenüs** mit **Suchfeld** (Instruments / Note‑FX / Audio‑FX)
  3) **Mini-Header Icons** (Arm/Mute/Solo/Monitor) statt Buchstaben (ohne Layout-Umbruch)

Zusätzlich: Hotfix für Crash beim Start (`NameError: QMenu not defined`).

## Implementiert (safe)
### 1) Hotfix: QMenu Import
- `pydaw/ui/arranger.py`: fehlender Import `QMenu` (und `QWidgetAction`, `QLineEdit`) ergänzt.
- Damit startet die App wieder ohne Traceback.

### 2) Phase 3: Track-Header ▾ PRO
**TrackList → pro Track ▾ Menü** enthält nun (je nach Track-Typ):

- **⭐ Favorites**
  - 1‑Klick Insert der Favoriten in die passende Chain
  - „⭐ Add/Remove from Recents“: Recents als Checkliste → Favoriten toggeln

- **🕘 Recents**
  - 1‑Klick Insert der zuletzt verwendeten Devices
  - „Clear Recents“

- **Searchable Quick Insert**
  - **Add Instrument…** (nur Instrument‑Tracks)
  - **Add Note‑FX…** (nur Instrument‑Tracks)
  - **Add Audio‑FX…** (Audio/Bus/Master und auch Instrument‑Tracks)
  - Jede Liste hat oben ein **Suchfeld** (QLineEdit im Menü)

- **Browser**
  - Open Instruments (Browser)
  - Open Effects (Browser)
  - Device Panel zeigen

### 3) Mini-Header Icons (ohne Layout-Umbruch)
- Track Header Buttons (Mute/Solo/Rec) nutzen jetzt kleine Painter‑Icons.
- Monitor (I) nutzt ebenfalls ein kleines Icon.
- Fallback: wenn Icon-Erzeugung fehlschlägt, bleiben Buchstaben/Buttons erhalten.

### 4) Wiring in MainWindow
- Implementiert:
  - `_on_track_header_open_browser(track_id, tab_key)`
  - `_on_track_header_show_device(track_id)`
  - `_on_track_header_add_device(track_id, kind, plugin_id)`
- `MainWindow` hält jetzt `self._right_tabs`, damit Browser‑Tab-Switches stabil funktionieren.

### 5) Per-User Persistenz (Favorites/Recents)
- Neues Modul: `pydaw/ui/device_prefs.py`
- Speichert JSON nach: `~/.cache/ChronoScaleStudio/device_prefs.json`
- Absichtlich **nicht** im Projekt gespeichert → Projekte bleiben portabel.

## Dateien
- `pydaw/ui/arranger.py`
- `pydaw/ui/main_window.py`
- `pydaw/ui/device_prefs.py` (neu)
- `pydaw/ui/chrono_icons.py`
- `VERSION`, `pydaw/version.py`

## Test-Checkliste
1) Start: kein `NameError: QMenu` mehr.
2) TrackList: Buttons zeigen Icons (Mute/Solo/Rec, Monitor).
3) Track ▾ → Devices:
   - Favorites/Recents sichtbar.
   - „Add Instrument/Note‑FX/Audio‑FX…“ → Suchfeld filtert Liste.
   - Klick auf Device → Device wird eingefügt (1‑Klick).
4) Browser‑Actions:
   - „Open Instruments/Effects (Browser)“ → Browser Dock sichtbar, richtiger Tab aktiv.
5) Favorites:
   - Track ▾ → Devices → ⭐ Favorites → ⭐ Add/Remove from Recents → Haken setzen/entfernen.
   - Favorit erscheint danach in ⭐ Favorites.
