# SESSION v0.0.20.323 — AETERNA Composer + Snapshot-Slot-Kurznamen

Datum: 2026-03-07

## Ziel
- Nur lokal in **AETERNA** arbeiten.
- Neuer sicherer Komfortschritt: lokaler Composer mit Dreiecks-Menü für mathematisch generierte MIDI-Clips auf der aktuellen AETERNA-Spur.
- Zusätzlich den bereits geplanten kleinen Snapshot-Schritt umsetzen: **Snapshot-Slot-Kurznamen**.

## Umsetzung
- `pydaw/plugins/aeterna/aeterna_widget.py` erweitert um einen neuen Bereich **AETERNA COMPOSER (LOCAL SAFE)**.
- Breiten lokalen **Weltstil-Katalog** ergänzt; UI erlaubt außerdem freie Eingabe über editierbare Comboboxen.
- Neuer **QToolButton mit Menü** ergänzt für:
  - neuen MIDI-Clip auf aktueller AETERNA-Spur erzeugen
  - aktiven Clip dieser Spur überschreiben
  - Seed neu würfeln
  - Stil-Mix neu würfeln
- Composer bleibt rein lokal und nutzt nur bestehende sichere APIs:
  - `ProjectService.add_midi_clip_at(...)`
  - `ProjectService.set_midi_notes(...)`
  - `ProjectService.commit_midi_notes_edit(...)`
- Erzeugte Voices: **Bass / Melodie / Lead / Pad / Arp**
- Ausdrücklich **keine Drum-Logik** ergänzt.
- Seed-/Style-/Voice-/Grid-/Bars-/Density-/Hybrid-/Swing-Parameter werden lokal im AETERNA-State gespeichert und beim Projektladen wiederhergestellt.
- Snapshot-Karte zeigt jetzt automatisch kurze Slot-Namen aus **Preset/Hörbild**; diese werden auch in Schnellaufrufen genutzt.

## Sicherheit
- Kein Eingriff in Playback-Core, Arranger, Clip Launcher, Audio Editor, Mixer oder Transport.
- Keine globalen Modelländerungen.
- Keine Änderungen an anderen Instrumenten.

## Prüfung
- `python3 -m py_compile pydaw/plugins/aeterna/aeterna_widget.py` erfolgreich.

## Nächste sichere Schritte
- Composer-Vergleichshinweise (aktueller Stil-Mix vs. letzter Seed) nur lokal im Widget.
- Snapshot-Vergleichshinweise mit Composer-Kontext.
