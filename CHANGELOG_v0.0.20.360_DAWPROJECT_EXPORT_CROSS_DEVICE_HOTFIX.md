# v0.0.20.360 — DAWproject Export Cross-Device Hotfix

- Kritischen Export-Fehler **`[Errno 18] Ungültiger Link über Gerätegrenzen hinweg`** behoben.
- Der finale `.dawproject`-ZIP wird jetzt als **temporäre Schwesterdatei im Zielordner** geschrieben statt in `/tmp`.
- Dadurch bleibt der Abschluss weiter **atomar via `os.replace()`**, auch wenn Staging in `/tmp` liegt und der Zielordner auf einem anderen Dateisystem liegt.
- Fehlerfall-Cleanup für die temporäre Zieldatei ergänzt.
- Keine Änderung an Audio-Engine, Routing, Mixer, Transport, Undo/Redo oder Projektmodell.
