## v0.0.20.192 — Fix: AI Composer UI Freeze + Scroll/Visibility

### Fixes
- **Freeze/"python3 antwortet nicht":** `AiComposerNoteFxWidget.refresh_from_project()` blockiert Child-Signale korrekt per `QSignalBlocker` → keine Re-Entrancy-Schleifen mehr.
- **Update-Spam reduziert:** `_flush()` emittiert `project_updated` nur bei echten Parameteränderungen.

### UX
- **Nicht mehr abgeschnitten:** AI Composer UI ist intern in einem `QScrollArea` eingebettet (self-scrollable in Device-Cards).
- **Kompakter:** Custom-Genre-Zeilen nur sichtbar, wenn Genre = `Custom`.
- **Alle Genres möglich:** Genre-Combos sind editierbar (beliebige Genres direkt eintippbar).

### Dateien
- `pydaw/ui/fx_device_widgets.py`
- `VERSION`, `pydaw/version.py`
