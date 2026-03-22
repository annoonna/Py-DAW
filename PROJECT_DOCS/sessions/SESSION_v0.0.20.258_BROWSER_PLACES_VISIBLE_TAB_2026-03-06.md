# SESSION v0.0.20.258 — Browser Orte/Favoriten sichtbar im rechten Browser

Datum: 2026-03-06
Autor: GPT-5.4 Thinking

## Ziel
Den echten rechten Browser sichtbar um Bitwig-artige Orte/Favoriten erweitern, nachdem die vorige Änderung im sichtbaren UI nicht klar erkennbar war.

## Änderungen
- Neuer Browser-Tab `⭐ Orte` in `pydaw/ui/device_browser.py`
- `pydaw/ui/sample_browser.py` um linke Orte-/Favoriten-Spalte erweitert
- Persistente UI-only Orte unter `~/.cache/ChronoScaleStudio/browser_places.json`
- Bestehende Filterlogik aus v0.0.20.257 bewusst beibehalten

## Sicherheitsrahmen
- Keine Änderungen an Audio-Engine
- Keine Änderungen an Bach-Orgel
- Keine Änderungen an SF2-/Sampler-Playback
- Keine Änderungen an Plugin-Hosting

## Validierung
- `python3 -m py_compile pydaw/ui/sample_browser.py pydaw/ui/device_browser.py pydaw/ui/browser_places_prefs.py pydaw/ui/browser_places_tab.py`

## Ergebnis
- Im rechten Browser ist jetzt ein eigener `⭐ Orte`-Tab sichtbar
- Im Samples-Tab gibt es zusätzlich eine linke Orte-/Favoriten-Spalte und `⭐ Aktuell`
- Home/Samples/SF2 bleiben mit den strikten Audio-/Sampler-Filtern nutzbar
