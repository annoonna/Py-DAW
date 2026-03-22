# SESSION v0.0.20.187 — Regression-Fix: v0.0.20.176 Verhalten wiederherstellen

## Kontext
Nach den UI-Erweiterungen (Track-Header ▾, Favorites/Recents, Browser Tabs) liefen einige Aktionen/Editoren nicht mehr wie seit v0.0.20.176.
Ursachen waren hauptsächlich Qt-Signal-Signatur-Mismatches (QAction.triggered(bool), QPushButton.clicked(bool)) und fehlende Kompat-Helper.

## Fixes (additiv / safe)
1) **Signal-Signaturen wieder kompatibel**
- Alle `triggered.connect(lambda: ...)` / `clicked.connect(lambda: ...)` Stellen, die ein bool-Argument erhalten, wurden auf `lambda _=False: ...` umgestellt.
- Ergebnis: Menüs/Buttons feuern wieder zuverlässig, ohne dass Qt-Hardening Exceptions schlucken muss.

2) **ProjectService.get_clip() reintroduced (Compat)**
- UI-Komponenten (Clip Launcher / Audio Editor) erwarten `services.project.get_clip(clip_id)`.
- Methode wurde als Wrapper ergänzt (keine Logikänderung an Clips selbst).

3) **AudioEventEditor robustes Clip-Lookup**
- `refresh()` nutzt nun eine defensive Clip-Ermittlung, falls `_get_clip` in Refactor-Kantenfällen nicht verfügbar ist.

4) **Qt-Hardening Slot-Wrapper verbessert**
- Log-Spam verhindert: Logging dedupliziert pro (slot, exc, message).
- Extra Signal-Args werden toleriert: bei `TypeError` wird automatisch mit weniger positional args erneut aufgerufen.

## Ergebnis
- Start stabil.
- Aktionen/Buttons wieder wie in v0.0.20.176.
- Keine Log-Flut mehr durch wiederholte Slot-Exceptions.

