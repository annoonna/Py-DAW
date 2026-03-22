# CHANGELOG v0.0.20.648 — Rust-Badge in Topbar-Mitte + bessere Snap-Lesbarkeit

**Datum:** 2026-03-20
**Autor:** GPT-5.4 Thinking
**Arbeitspaket:** User-Hotfix — UI Branding / Toolbar-Ergonomie

## Was wurde gemacht
- Rust-Badge aus dem rechten Toolbereich in die Transport-Leiste direkt hinter `Count-In` verschoben.
- Werkzeug- und Snap-ComboBoxen sichtbar vergroessert, damit `Zeiger`, `1/16` und `1/32` oben besser erkannt werden koennen.
- Dropdown-Zone der ComboBoxen vergroessert, damit der kleine obere Bedienbereich klarer sichtbar ist.
- Statusleisten-Feedback auf das neue Rust-Badge umverdrahtet.

## Geaenderte Dateien
| Datei | Aenderung |
|---|---|
| `pydaw/ui/transport.py` | Eigenstaendiges Rust-Badge in die Transport-Leiste verschoben |
| `pydaw/ui/toolbar.py` | ComboBox-Breiten, Font und Dropdown-Zone fuer bessere Lesbarkeit angepasst |
| `pydaw/ui/main_window.py` | Rust-Badge-Signal auf neue Position verdrahtet |

## Was als naechstes zu tun ist
- Screenshot pruefen, ob die neue Rust-Position genau der gewuenschten Topbar-Mitte entspricht.
- Falls noetig nur noch Feinjustierung der Badge-Abstaende, ohne die Toolbar-Logik anzutasten.

## Bekannte Probleme / Offene Fragen
- Visueller Laufzeittest war in dieser Umgebung nicht moeglich; der Hotfix ist deshalb ueber gezielte Layout-Anpassung und `py_compile` abgesichert.
