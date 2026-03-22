# CHANGELOG v0.0.20.617 — Slot-Timer Repaint + Arranger Follow-Grid Fix

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6

---

## Fix 1: Slot-Zeit aktualisiert sich nicht (steht bei "0.0 Bar")

**Root Cause:** Der 60ms Timer-Tick rief nur `self.inner.update()` und
`self.update()` auf — das sind die Container-Widgets. Die einzelnen
`SlotWaveButton`-Instanzen bekamen kein `update()` und wurden daher
nicht repainted. Der Countdown-Text wurde zwar berechnet, aber nie
neu gezeichnet.

**Fix:** Timer-Tick iteriert jetzt über `self._active_slots` und ruft
`btn.update()` direkt auf den aktiven Slot-Buttons auf.

## Fix 2: Arranger Follow-Modus — Grid verschwindet beim Scrollen

**Root Cause:** Wenn Follow-Playhead die Scrollbar verschob, wurde
danach nur ein schmaler Streifen um den Playhead repainted
(`self.update(QRect(...))`). Grid, Clips und Hintergrund am neuen
Scroll-Offset wurden nicht neu gezeichnet.

**Fix:** Nach einem Follow-Scroll wird `self.update()` (volles Repaint)
aufgerufen statt nur des schmalen Streifens. Ohne Follow-Scroll bleibt
der performante Streifen-Repaint erhalten.

## Zum Thema: Arranger-Transport spielt Launcher-Clip

Das ist **korrektes Bitwig/Ableton-Verhalten**: Wenn du einen Clip im
Launcher per ▶ startest, läuft er unabhängig vom Transport. Der Transport
ist nur die globale Uhr — der Launcher nutzt sie zur Synchronisation.

Wenn du den Transport stoppst und wieder startest, laufen bereits
gestartete Launcher-Clips weiter. Du musst explizit ■ (Stop pro Track)
oder "Stop All" klicken um Launcher-Clips zu stoppen.

---

## Geänderte Dateien

| Datei | Fix |
|---|---|
| `pydaw/ui/clip_launcher.py` | Timer-Tick → aktive Buttons direkt updaten |
| `pydaw/ui/arranger_canvas.py` | Follow-Scroll → volles Repaint |
