# SESSION v0.0.20.349 — Group Fold-State / Arranger Group-Lane / Track-Reorder

Datum: 2026-03-08
Bearbeiter: GPT-5

## Kontext
User meldete, dass:
- der Gruppen-Einklappstatus beim Projektladen nicht erhalten bleibt,
- eingeklappte Gruppen im Arranger rechts noch nicht als echte gemeinsame Spur erscheinen,
- neue Spuren oft unterhalb der Gruppe landen,
- Spuren nach dem Erstellen nicht sauber nach oben/unten verschoben werden können.

## Umgesetzt
1. Projektmodell um persistente `arranger_collapsed_group_ids` erweitert.
2. TrackList synchronisiert Fold-State mit dem Projekt und speichert Änderungen zurück.
3. ArrangerCanvas führt eingeklappte Gruppen als gemeinsame sichtbare Lane.
4. Track-Menüs um `Spur nach oben` / `Spur nach unten` erweitert.
5. Gruppenkopf-/Track-Menüs können neue Spuren direkt in die aktive Gruppe einfügen.
6. `ProjectService.add_track()` auf sichere Insert-/Group-Optionen erweitert; `move_track()` ergänzt.

## Verifikation
- `python3 -m py_compile` erfolgreich für:
  - `pydaw/model/project.py`
  - `pydaw/services/project_service.py`
  - `pydaw/services/altproject_service.py`
  - `pydaw/ui/arranger.py`
  - `pydaw/ui/arranger_canvas.py`
  - `pydaw/version.py`

## Grenzen
- Keine echte Audio-Gruppenbus-Logik.
- Eingeklappte Gruppen-Lane ist visuell/organisatorisch, nicht routingbasiert.
