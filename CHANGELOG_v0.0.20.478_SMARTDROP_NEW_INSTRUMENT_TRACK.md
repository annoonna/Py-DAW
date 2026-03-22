# CHANGELOG v0.0.20.478 — SmartDrop: Neue Instrument-Spur aus Leerraum-Drop

## Neu

- `pydaw/ui/arranger_canvas.py`: Ein Instrument-Drop **unterhalb der letzten Spur** ist jetzt nicht mehr nur Preview, sondern löst einen echten SmartDrop-Request aus.
- `pydaw/ui/main_window.py`: Der SmartDrop erzeugt eine neue **Instrument-Spur**, benennt sie nach dem Plugin und fügt das Instrument über die vorhandenen sicheren DevicePanel-Pfade ein.

## Safety

- Kein SmartDrop auf bestehende Spuren.
- Kein Audio→MIDI-Morphing.
- Kein Routing-Umbau vorhandener Tracks.
- Bei Insert-Fehlschlag wird die neu angelegte Spur wieder entfernt.
