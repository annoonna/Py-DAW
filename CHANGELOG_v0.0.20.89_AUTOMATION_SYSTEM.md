# CHANGELOG v0.0.20.89 — Automation System Foundation (Phase 1)

**Datum:** 2026-02-17
**Entwickler:** Claude Opus 4.6

## 🎯 Übersicht

Fundament für ein **Bitwig/Ableton-Grade Automationssystem** gelegt. Modulare Architektur,
die schrittweise erweitert werden kann — ohne bestehenden Code zu brechen.

## Neue Features

### AutomatableParameter (Core Engine)
- Unified Parameter System: Jeder Parameter unterstützt gleichzeitig Manual, Timeline-Automation und Modulation
- Wert-Stack: `effective_value = clamp(automation_value or base_value + modulation_offset)`
- Observer Pattern: Listener werden bei Wertänderungen benachrichtigt
- Lock-free Design: GUI schreibt, Audio-Thread liest via RTParamStore

### AutomationManager (Zentraler Service)
- Registry aller Parameter + Lanes
- Signal `request_show_automation(parameter_id)` — jedes Widget kann Automation im Arranger öffnen
- `tick(beat)` — wird bei Playback aufgerufen, interpoliert Lane-Daten → Parameter
- Import/Export für Projekt-Persistenz
- Legacy-Bridge für alte `automation_lanes` Dict-Struktur

### Breakpoint Envelopes (Bezier!)
- 4 Kurventypen: **Linear**, **Bezier** (quadratisch), **Step** (diskret), **Smooth** (S-Curve)
- Bezier: Draggbare Control Points als orangefarbene Rauten
- Sample-genaue Interpolation (anti-Zipper-Noise via RTParamStore Smoothing)

### AutomatedKnob (Bitwig-Style Widget)
- Rundes Knob-Widget mit Modulations-Ring
- Orange/Purple Ring zeigt Modulationsbereich
- Roter Notch bei aktiver Automation
- Shift+Drag = Feineinstellung, Doppelklick = Reset
- Rechtsklick-Kontextmenü: "Show Automation in Arranger"

### Enhanced Automation Lane Editor
- Professioneller Kurven-Editor mit Grid + Playhead
- Drag-to-move Punkte, Rechtsklick-to-delete
- ComboBox mit Suchfunktion für Parameter-Auswahl
- Track + Mode + Curve-Type Selektoren
- Reagiert auf `request_show_automation` → springt automatisch zum Parameter

## Architektur-Entscheidungen

1. **Modular**: Neue Module sind eigenständig, kein Refactoring bestehender Widgets nötig
2. **Observer Pattern**: AutomationManager → Signal-basiert, kein direkter Widget↔Arranger Coupling
3. **Lock-free Audio**: Alle Werte fließen über RTParamStore (bestehende Infrastruktur)
4. **Backward-Compatible**: Altes AutomationLanePanel bleibt als Fallback

## Dateien

| Datei | Status | Beschreibung |
|-------|--------|-------------|
| `pydaw/audio/automatable_parameter.py` | NEU | AutomatableParameter + AutomationManager + BreakPoint/Lane |
| `pydaw/ui/widgets/automated_knob.py` | NEU | AutomatedKnob + AutomatedSlider + Mixin |
| `pydaw/ui/automation_editor.py` | NEU | EnhancedAutomationEditor + Panel |
| `pydaw/services/container.py` | GEÄNDERT | AutomationManager registriert |
| `pydaw/ui/arranger.py` | GEÄNDERT | set_automation_manager(), Enhanced Panel |
| `pydaw/ui/main_window.py` | GEÄNDERT | Wiring, Playhead, View Range |
| `VERSION` / `pydaw/version.py` | GEÄNDERT | 0.0.20.89 |
