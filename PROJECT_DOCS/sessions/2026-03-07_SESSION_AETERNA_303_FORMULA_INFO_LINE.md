# SESSION — v0.0.20.303 — AETERNA Formel-Infozeile

Datum: 2026-03-07
Autor: GPT-5

## Ziel
Nächster sicherer lokaler AETERNA-Schritt nach den freigegebenen stabilen Automationszielen:
Eine kleine Formel-Infozeile ergänzen, die klar zeigt, ob ein Startbeispiel nur im Feld steht,
manuell geändert wurde oder bereits angewendet ist.

## Umsetzung
- Im AETERNA-Formelbereich wurde eine neue lokale **Formel-Infozeile** ergänzt.
- Die Zeile unterscheidet jetzt sichtbar zwischen:
  - Beispiel geladen / im Feld
  - manuell geändert / noch nicht angewendet
  - angewendet
  - leer / Fallback bei Anwenden
- Beim Laden eines Startbeispiels wird der lokale Status sofort aktualisiert.
- Beim Anwenden der Formel wird der zuletzt angewendete Text lokal mitgeführt.
- Der UI-Status wird im lokalen AETERNA-Instrument-State mitgespeichert, ohne Änderungen am globalen DAW-Core.

## Risiko / Sicherheit
- Nur `pydaw/plugins/aeterna/aeterna_widget.py` lokal angepasst.
- Keine Änderungen an Arranger, Clip Launcher, Audio Editor, Mixer, Transport, Playback-Core oder globalem Automationssystem.

## Nächste sichere Schritte
- Kuratierte lokale Formel-Preset-Karte um weitere Startbeispiele ergänzen.
- Automation-ready-Hinweise an ausgewählten AETERNA-Knobs noch kompakter machen.
