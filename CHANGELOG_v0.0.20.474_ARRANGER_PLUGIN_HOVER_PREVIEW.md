# v0.0.20.474 — Arranger/TrackList Plugin Hover Preview

## Was wurde gemacht?

- `pydaw/ui/arranger.py` markiert in der Arranger-TrackList jetzt rein visuell die Zielspur, wenn ein Plugin aus dem Browser über eine Spur gezogen wird.
- `pydaw/ui/arranger_canvas.py` zeichnet zusätzlich ein cyanfarbenes Spur-Overlay direkt im Arranger-Canvas.
- Die Preview unterscheidet zwischen **Instrument**, **Effekt** und **Note-FX** über den bestehenden Plugin-Payload.
- Instrument-Hover auf Audio-Spuren zeigt absichtlich nur einen Hinweis wie **„Morphing folgt später“** statt schon jetzt die Spur umzubauen.

## Warum ist das wichtig?

Das ist der nächste sichere Vorbauschritt für den späteren **SmartDropHandler** aus dem Rundschreiben:
- Zielseiten reagieren endlich auf die mitgelieferten Rollen-Metadaten.
- Der User bekommt klares visuelles Feedback, wohin ein Plugin gerade zielen würde.
- Bestehende Drop-/Routing-Logik bleibt unangetastet.

## Betroffene Dateien

- `pydaw/ui/arranger.py`
- `pydaw/ui/arranger_canvas.py`

## Validierung

```bash
python -m py_compile pydaw/ui/arranger.py pydaw/ui/arranger_canvas.py
```
