# v0.0.20.371 — VST3 Project-State Raw-Blob Save/Load

**Datum**: 2026-03-10
**Bearbeiter**: GPT-5
**Aufgabe**: Projektseitige Preset-/State-Speicherung für externe VST2/VST3-Devices ergänzen, ohne den Audio-Callback oder das Live-Hosting zu riskieren
**Ausgangsversion**: 0.0.20.370
**Ergebnisversion**: 0.0.20.371

## Ziel

Nach den Hotfixes für Live-Hosting, Multi-Plugin-Referenzen, Mono/Stereo-Bus-Adapt und Runtime-Param-Reuse fehlte noch der nächste sichere Schritt:

- Preset-/Plugin-State projektseitig sichern
- beim Projektladen wiederherstellen
- dabei **nicht** direkt auf die laufende DSP-Instanz schreiben/lesen
- **keinen** blockierenden Umbau des Audio-Threads einführen

## Umgesetzte Änderungen

- `pydaw/audio/vst3_host.py`
  - Base64-Helfer für `raw_state` ergänzt
  - `export_state_blob(...)` lädt für den Save-Pfad eine **frische Plugin-Instanz**, setzt die aktuell gespeicherten Projekt-Parameter und serialisiert daraus `plugin.raw_state`
  - `embed_project_state_blobs(project)` iteriert über alle externen VST2/VST3-Devices in den Track-Audio-FX-Ketten und schreibt den Blob nach `params["__ext_state_b64"]`
  - `Vst3Fx._load()` restauriert diesen Blob beim Laden zuerst wieder auf die Live-Instanz
  - explizit gespeicherte Parameterwerte bleiben weiterhin maßgeblich und werden danach wie bisher auf RT/Plugin gespiegelt

- `pydaw/fileio/project_io.py`
  - Vor dem JSON-Schreiben wird jetzt automatisch `embed_project_state_blobs(project)` ausgeführt
  - dadurch greifen sowohl normales Speichern als auch Snapshot-Pfade, ohne mehrere Save-Aufrufer einzeln umzubauen

## Sicherheitsprinzip

- Kein Zugriff auf `raw_state` der laufenden DSP-Instanz im Audio-Callback
- Kein Umbau an Mixer, Routing, Transport oder Hybrid-Callback
- Save-Pfad nutzt bewusst eine **temporäre, frische Plugin-Instanz**
- Falls `pedalboard` oder `raw_state` nicht verfügbar ist, bleibt das Verhalten defensiv: bestehendes Projektformat bleibt gültig, Save bricht nicht ab

## Benutzerwirkung

- Projekte können für externe VST2/VST3-Devices jetzt zusätzlich einen eingebetteten State-Blob mitschreiben
- Beim erneuten Laden wird dieser State vor der normalen Parameter-Initialisierung restauriert
- Damit ist die Grundlage gelegt, Plugin-Preset-/State-Daten projektseitig zu erhalten, ohne den bereits stabilisierten Live-Hosting-Pfad zu riskieren

## Tests

- ✅ `python -m py_compile pydaw/audio/vst3_host.py pydaw/fileio/project_io.py pydaw/model/project.py pydaw/version.py`
- ✅ statischer Syntax-Check der neuen Base64-/Save-Helfer
- ℹ️ echter `pedalboard`-/VST3-Lauftest war im Container nicht möglich, weil `pedalboard` hier nicht installiert war

## Nächste sichere Schritte

- [ ] Optional im VST3-Widget einen kleinen Hinweis anzeigen, ob ein eingebetteter State-Blob vorhanden ist
- [ ] Optional später einen manuellen **„Preset/State aktualisieren“**-Trigger ergänzen, falls native Plugin-Editoren internen State außerhalb der generischen Parameter ändern
