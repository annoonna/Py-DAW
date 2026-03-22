# SESSION LOG: 2026-03-16 — v0.0.20.516

**Entwickler:** Claude Opus 4.6
**Zeit:** 2026-03-16
**Task:** Cross-Track Device Drag&Drop (Bitwig-Style)

## ZUSAMMENFASSUNG

Devices (Instrumente, Audio-FX, Note-FX) koennen jetzt per Drag&Drop aus dem
DevicePanel einer Spur auf eine andere Spur im Arranger/TrackList verschoben
werden — genau wie in Bitwig Studio.

## WAS FUNKTIONIERT JETZT

1. **Instrument von Spur A → Instrument-Spur B**: Instrument wird auf B
   eingefuegt, von A entfernt.
2. **Instrument von Spur A → leere Audio-Spur**: v515 Morph-Guard konvertiert
   die Audio-Spur atomar zu Instrument-Spur, fuegt das Instrument ein, entfernt
   es von A. Alles in einem Undo-Punkt.
3. **Audio-FX von Spur A → kompatible Spur B**: FX wird auf B eingefuegt, von
   A entfernt.
4. **Note-FX von Instrument-Spur A → Instrument-Spur B**: Ebenso.
5. **Internes Reorder**: Drag innerhalb derselben Chain funktioniert exakt wie
   vorher (unveraendert).
6. **Browser-Drops**: Alle Browser→Arranger/TrackList/DevicePanel Pfade
   funktionieren exakt wie vorher (unveraendert).

## WAS BEWUSST NOCH NICHT GEHT

- Instrument auf BELEGTE Audio-Spur (Clips/FX) → weiterhin blockiert
- Ctrl+Drag fuer Copy statt Move → spaeterer Schritt
- Automatische Track-Typ-Anpassung der Quellspur → spaeterer Schritt

## ARCHITEKTUR-ENTSCHEIDUNG

Die gesamte Empfaenger-Infrastruktur (Arranger Canvas, TrackList, SmartDrop-
Signale, MainWindow-Handler) existierte bereits. Die Aenderung war rein
**sender-seitig**: DeviceCards senden jetzt reichere Payloads mit
`source_track_id`, und MainWindow entfernt nach erfolgreichem Drop das Device
von der Quellspur.

Kein neuer Signal-Typ, kein neuer MIME-Typ, keine neue Klasse noetig. Alles
rein additiv.

## GEAENDERTE DATEIEN

- `pydaw/ui/device_panel.py` (~30 Zeilen geaendert)
  - _DeviceCard: 3 neue init-Parameter
  - mouseMoveEvent: reicheres Payload
  - Note-FX/Audio-FX/Instrument Card Creation: Metadaten gesetzt
- `pydaw/ui/main_window.py` (~60 Zeilen geaendert)
  - _smartdrop_remove_from_source(): NEU
  - _on_arranger_smartdrop_instrument_to_track(): cross-track erweitert
  - _on_arranger_smartdrop_fx_to_track(): cross-track erweitert
  - _on_arranger_smartdrop_instrument_morph_guard(): cross-track erweitert

## NICHTS KAPUTT GEMACHT

- Alle bestehenden SmartDrop-Pfade unveraendert
- Internes Device-Reorder unveraendert
- Browser-Drops unveraendert
- Morph-Guard fuer belegte Spuren unveraendert
- Undo/Redo funktioniert (auto-undo snapshot deckt Move + Remove ab)
