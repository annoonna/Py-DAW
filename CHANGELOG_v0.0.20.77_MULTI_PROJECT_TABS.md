# CHANGELOG v0.0.20.77 — Multi-Project Tabs (Bitwig-Style)

**Datum:** 2026-02-15
**Entwickler:** Claude Opus 4.6

## 🎯 Feature: Multi-Project Tabs

Ermöglicht das gleichzeitige Öffnen mehrerer Projekte in Tabs — wie in Bitwig Studio.
Nur das aktive Projekt nutzt die Audio-Engine (ressourcenschonend).

### Neue Features

#### 1. Projekt-Tab-Leiste (1.2.1)
- Tab-Bar am oberen Rand des Hauptfensters
- Jedes geöffnete Projekt hat einen eigenen Tab
- Tab zeigt Projektname + Dirty-Indikator (•)
- Doppelklick zum Umbenennen
- Rechtsklick-Kontextmenü (Speichern, Umbenennen, Schließen)
- `+` Button für neues Projekt
- `📂` Button zum Öffnen in neuem Tab

#### 2. Datei-Menü Integration
- **Ctrl+T**: Neuer Tab (leeres Projekt)
- **Ctrl+Shift+O**: Projekt öffnen in neuem Tab
- **Ctrl+W**: Aktiven Tab schließen (mit Dirty-Check)

#### 3. Cross-Project Track-Copy (1.2.5 / 1.3.8)
- Tracks können zwischen Tabs kopiert werden
- **Full State Transfer**: Device-Chains, MIDI-Notes, Automationen, Media-Referenzen
- Clips werden automatisch mitkopiert
- Neue IDs verhindern Konflikte

#### 4. Projekt-Browser (1.3.5)
- Neuer "Projekte" Tab im rechten Browser-Dock
- Zeigt `.pydaw.json` Dateien in gewähltem Ordner
- **Peek-Funktion**: Klick auf Projektdatei → Tracks/Clips-Vorschau
- "In neuem Tab öffnen" Button
- "Tracks importieren" Button (direkt in aktives Projekt)

#### 5. Ressourcen-Management
- Nur das aktive Projekt ist an die Audio-Engine gebunden
- Tab-Wechsel: Transport Stop → Context-Swap → Engine-Rebind
- BPM/Taktart/Loop werden beim Wechsel synchronisiert
- Inaktive Projekte bleiben im Speicher (sofortiges Umschalten)

### Technische Details

**Neue Dateien:**
| Datei | Beschreibung |
|-------|-------------|
| `pydaw/services/project_tab_service.py` | Multi-Tab Service (State Management) |
| `pydaw/ui/project_tab_bar.py` | Tab-Bar Widget (QTabBar) |
| `pydaw/ui/project_browser_widget.py` | Projekt-Datei-Browser |
| `pydaw/ui/cross_project_drag.py` | MIME-Helpers für D&D |

**Geänderte Dateien:**
| Datei | Änderung |
|-------|----------|
| `pydaw/services/container.py` | +ProjectTabService |
| `pydaw/ui/main_window.py` | +Tab-Bar, +Menü, +Handler |
| `pydaw/version.py` | → 0.0.20.77 |
| `pydaw/model/project.py` | Version-String |

### Architektur

```
MainWindow
├── ProjectTabBar (QToolBar, ganz oben)
│   └── QTabBar + '+' Button + '📂' Button
├── TransportToolBar
├── ToolsToolBar
├── CentralWidget (Arranger)
├── BrowserDock
│   ├── Browser (DeviceBrowser)
│   ├── Parameter (TrackParameters)
│   └── Projekte (ProjectBrowserWidget)  ← NEU
└── BottomDocks (Editor, Mixer, Device)

ProjectTabService
├── tabs: List[ProjectTab]
│   ├── ProjectTab 0 (aktiv → AudioEngine)
│   ├── ProjectTab 1 (inaktiv, im Speicher)
│   └── ProjectTab N ...
├── copy_tracks_between_tabs()
├── copy_clips_between_tabs()
└── peek_project() (read-only für Browser)
```

### Abwärtskompatibilität
- ✅ Bestehendes Single-Project bleibt als Tab 0 erhalten
- ✅ Alle vorherigen Menü-Aktionen funktionieren unverändert
- ✅ Fallback: Wenn Tab-Service nicht verfügbar, läuft alles wie vorher
- ✅ Keine Breaking Changes
