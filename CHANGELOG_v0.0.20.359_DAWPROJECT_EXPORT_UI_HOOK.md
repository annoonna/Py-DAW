# v0.0.20.359 — DAWproject Export UI Hook

- Menüeintrag **Datei → DAWproject exportieren… (.dawproject)** ergänzt.
- Export nutzt weiter den bereits eingeführten **snapshot-basierten Exporter** und berührt die Live-Session nicht.
- Startet im Hintergrund über **QRunnable/QThreadPool**, damit die Oberfläche responsiv bleibt.
- Fortschritt wird über einen **QProgressDialog** angezeigt.
- Zielpfad wird sicher über **QFileDialog** gewählt; Standardname orientiert sich am Projektnamen bzw. an der `.pydaw.json`.
- Nach Abschluss erscheint ein kompakter Summary-Dialog mit Anzahl von Spuren, Clips, Noten, Audio-Dateien und Plugin-States.
- Keine Änderung an Audio-Engine, Mixer, Transport, Routing oder Undo/Redo-Core.
