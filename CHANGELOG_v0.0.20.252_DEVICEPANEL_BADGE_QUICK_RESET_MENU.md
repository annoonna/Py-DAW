# CHANGELOG v0.0.20.252 — DevicePanel Header-Badge anklickbar

## Neu
- Das DevicePanel-Header-Badge (`NORMAL`, `ZONE N/I/A`, `FOKUS ◎`) ist jetzt nicht mehr nur Anzeige, sondern auch Bedien-Element.
- **Linksklick** auf das Badge:
  - bei aktivem Modus → **Quick-Reset** auf Normalansicht
  - im Normalzustand → bestehendes **Kurzhilfe-Popup**
- **Rechtsklick** öffnet ein kleines Ansichtsmenü mit:
  - Reset
  - Fokus-Modus
  - Zonenfokus N / I / A
  - Inaktive einklappen
  - Alle einklappen
  - Alle ausklappen
  - Kurzhilfe

## Sicherheit
- Rein **UI-only**.
- Keine Änderungen an Audio-Engine, DSP, Projektmodell, Playback, DnD oder Reorder.
- Es werden ausschließlich bereits vorhandene UI-Methoden aufgerufen.
