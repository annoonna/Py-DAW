# Session Log — v0.0.20.444

**Datum:** 2026-03-13
**Bearbeiter:** Claude Opus 4.6
**Task:** Detachable Panels + Bitwig-Style Multi-Monitor Layout System

## Analyse

### Ist-Zustand (v0.0.20.443)
- 5 QDockWidgets: Editor, Mixer, Device, Browser, Clip Launcher
- Alle an BottomDockWidgetArea / RightDockWidgetArea gebunden
- Kein Detach/Float-Mechanismus
- Keine Multi-Monitor-Unterstützung
- `_set_view_mode()` wechselt nur Arrange/Mix/Edit/Device

### Anforderung (aus Screenshots + Beschreibung)
- Jedes Panel (Automation, Editor, Mixer, Device, Browser) als freies Fenster abkoppelbar
- Bitwig-Style Layout-Presets für 1/2/3 Monitore
- Menü wie im Screenshot: "Ein Bildschirm (Groß/Klein)", "Tablet", "Zwei Bildschirme (Studio/Arranger-Mixer/Hauptbildschirm-Detail/Studio-Touch)", "Drei Bildschirme"
- Automation-Lane als eigenständiges Fenster abkoppelbar

## Implementierung

### Neues Modul: `pydaw/ui/screen_layout.py` (~430 Zeilen)

**Architektur:**
1. `PanelId(Enum)` — Kanonische Namen für alle Panels
2. `_FloatingWindow(QWidget)` — Top-level Fenster; close → re-dock statt destroy
3. `DetachablePanel` — Kapselt ein Widget; toggle zwischen docked/floating
4. `LayoutPreset` / `PanelPlacement` — Datenklassen für Layout-Beschreibung
5. `LAYOUT_PRESETS` — 8 vordefinierte Presets (exakt wie Bitwig-Menü)
6. `ScreenLayoutManager` — Orchestriert alle Panels, wendet Presets an

**Best Practices angewendet:**
- Factory/Registry Pattern: Panels registrieren sich mit restore-Callback
- Relative Koordinaten (0..1) für Screen-Platzierung → DPI-unabhängig
- Persistenz via SettingsStore (gleicher Store wie restliche UI-Settings)
- Safety: Alle Qt-Ops in try/except, niemals crash

### Integration in `main_window.py`

- Import von `screen_layout` Modulen
- `_init_screen_layout_manager()`: Registriert 5 Panels (Editor, Mixer, Device, Browser, Automation)
- `_populate_screen_layout_menu()`: Dynamisches Menü mit Screen-Count-Erkennung
- Ansicht → Bildschirm-Layout Untermenü mit allen Presets + Einzel-Detach + "Alle andocken"
- `closeEvent`: Speichert Geometrie, dockt alles an

## Nicht veränderte Dateien
- Arranger, PianoRoll, Mixer, DevicePanel, AutomationEditor — unverändert
- Audio-Engine, Transport, Services — unverändert
- **Nichts kaputt gemacht** ✅

## Nächste Schritte (AVAILABLE)
- Keyboard Shortcuts (Ctrl+Alt+1/2/3)
- Custom Layouts speichern
- Screen-Change Detection (Hot-Plug)
- Arranger selbst auch detachable
