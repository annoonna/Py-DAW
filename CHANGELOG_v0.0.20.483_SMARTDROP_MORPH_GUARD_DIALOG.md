# Changelog v0.0.20.483 — SmartDrop Morph Guard Dialog

## Neu

- `pydaw/ui/main_window.py`: Geblockte `Instrument -> Audio-Spur`-Drops zeigen jetzt optional einen read-only Sicherheitsdialog, wenn der vorhandene Morphing-Plan `requires_confirmation=True` meldet.
- Der Dialog nutzt direkt `blocked_message`, `summary` und `blocked_reasons` aus dem zentralen Guard-Plan.
- Nach dem Dialog bleibt die Statusbar-Meldung aktiv, damit der Guard-Zustand weiterhin klar sichtbar ist.

## Safety

- Kein echtes Audio->Instrument-Morphing
- Kein Routing-Umbau
- Keine Projektmutation
- Keine Aenderung an Canvas-/TrackList-Drop-Zielregeln
