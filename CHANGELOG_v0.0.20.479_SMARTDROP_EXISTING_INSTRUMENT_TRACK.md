# v0.0.20.479 — SmartDrop auf bestehende Instrument-Spur

- ArrangerCanvas akzeptiert jetzt erstmals einen **echten Instrument-Drop auf bestehende Instrument-Spuren**.
- Arranger-TrackList (links) akzeptiert denselben Drop ebenfalls; beide Wege leiten die Aktion zentral an MainWindow weiter.
- Hover-/Tooltip-Texte unterscheiden jetzt zwischen **echter Aktion** (`Instrument → Einfügen auf ...`) und reiner Preview (`Nur Preview — SmartDrop folgt später`).
- Weiterhin bewusst eingeschränkt: **kein Audio→MIDI-Morphing**, **kein SmartDrop auf Audio-Spuren**, **keine Routing-Umbauten**.
