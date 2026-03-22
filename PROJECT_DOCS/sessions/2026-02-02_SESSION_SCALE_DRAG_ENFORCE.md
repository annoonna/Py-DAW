# Session Log – 2026-02-02 – Scale Lock: Drag/Move Enforcement + Mode UI Fix

Version: **v0.0.19.5.1.18**

## Ziel
- Scale Lock soll auch beim **Drag/Move** (Pitch-Editing) greifen.
- Mode-Auswahl **Snap/Reject** soll UI-seitig eindeutig sein (exklusiv, Checkmarks sofort aktuell).

## Umsetzung
- Piano Roll (`pydaw/ui/pianoroll_canvas.py`)
  - neue Helper-Funktion `_scale_constrain_pitch()` (Snap: nearest allowed, Reject: fallback)
  - angewendet bei **Single-Drag** und **Multi-Drag** (Batch Move)
  - Pen-Klick (kleiner Selektions-Click) nutzt jetzt `_add_note_at()` → Scale-Lock gilt auch dort

- UI (`pydaw/ui/scale_menu_button.py`)
  - Mode-Actions sind jetzt in einer **exklusiven QActionGroup**
  - Menü wird nach jeder Änderung neu aufgebaut, damit die Häkchen sofort korrekt sind

## Testplan (manuell)
1) Scale Lock aktivieren → Root z.B. **C**, Scale z.B. **Major**
2) Mode = **Snap**
   - Note auf C# zeichnen/draggen → sollte auf C oder D snappen (nearest)
3) Mode = **Reject**
   - Note auf C# zeichnen → keine Note wird gesetzt (Statusmeldung)
   - vorhandene Note nach C# ziehen → Pitch bleibt auf der letzten erlaubten Note (keine „falschen“ Noten)

## Nächste Schritte
- Optional: Visualisierung (Cyan Dots/Highlights) der erlaubten Skalentöne im Piano Roll Grid/Keyboard.
