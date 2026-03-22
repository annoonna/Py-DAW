## v0.0.20.249 (2026-03-06) 🎛 FX-Automation für externe Effekte

### Neu
- **LV2/LADSPA/DSSI FX-Parameter sind jetzt automatisierbar**: Rechtsklick auf Parameter-Label, Slider oder SpinBox öffnet jetzt `Show Automation in Arranger`.
- **AutomationManager-Anbindung** für externe FX-Widgets: registriert Parameter mit sauberer `afx:{track}:{device}:...` ID.
- **Lane-Playback** aktualisiert jetzt bei externen FX sowohl UI als auch RT-Store und Projektwerte.
- **Basis-Audio-FX** `Gain` und `Distortion` wurden ebenfalls an die gleiche Automationsroute angeschlossen.

### Bewusst nicht in diesem Schritt
- **Kein LADSPA-Subprozess-Safe-Mode** in diesem Commit. Da aktuell kein Crash mehr reproduziert wurde, blieb dieser Schritt absichtlich draußen, um keine neue Hosting-Architektur unnötig zu riskieren.

---

