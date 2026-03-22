# Session v0.0.20.353 — TrackList Drop-Markierung beim Maus-Reorder

Datum: 2026-03-08
Bearbeitung: GPT-5

## Aufgabe
- Beim lokalen Maus-Reorder in der linken Arranger-TrackList eine **sichtbare Drop-Markierung** ergänzen.
- Bestehenden **Cross-Project-Track-Drag** dabei nicht verändern oder brechen.

## Umsetzung
- `pydaw/ui/arranger.py` erhielt eine kleine sichere Drop-Marker-Logik direkt in der `TrackList`.
- `ArrangerTrackListWidget` meldet interne Reorder-Drag-Bewegungen jetzt an die bestehende TrackList zurück.
- Die TrackList zeigt dabei eine **cyanfarbene Marker-Linie** an der berechneten Einfügeposition im linken Listenbereich.
- Marker wird bei **Drag Leave**, **Drop** und **Refresh** wieder sicher entfernt.
- Marker reagiert nur auf das vorhandene lokale `MIME_TRACKLIST_REORDER`; andere Drag-Wege bleiben unberührt.

## Sicherheit
- Kein Eingriff in Audio-Routing, Mixer, DSP, Playback oder Clip-Daten.
- Kein Umbau am Cross-Project-Drag-Protokoll.
- Nur UI-Feedback für bereits vorhandenes lokales Reorder-Verhalten.

## Prüfung
- `python3 -m py_compile pydaw/ui/arranger.py pydaw/version.py`

## Ergebnis
- Beim Maus-Verschieben ist jetzt klar sichtbar, **wo** Spur oder Block landen werden.
- Die Bedienung im linken Arranger ist damit deutlich weniger blind, ohne den bisherigen Flow zu verändern.
