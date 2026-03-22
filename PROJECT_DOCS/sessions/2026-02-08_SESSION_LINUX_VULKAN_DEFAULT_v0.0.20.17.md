# Session Log — 2026-02-08 — v0.0.20.18

## Thema
**Linux: Vulkan als Default (Bootstrap) + requirements / Install-Doku bereinigt**

## Kontext
Der User wollte, dass das Projekt unter Linux konsequent auf **Vulkan** vorbereitet wird.
Da die aktuelle UI überwiegend **Qt Widgets** nutzt (kein QtQuick/QML), ist ein kompletter Renderer-Wechsel (OpenGL → Vulkan) eine größere Baustelle.
In dieser Session wurde deshalb die **Start-Up-Konfiguration** so umgesetzt, dass Vulkan unter Linux **standardmäßig bevorzugt** wird, aber **niemals** einen Start-Crash verursacht.

## Änderungen
### ✅ Neu
- `pydaw/utils/gfx_backend.py`
  - pure Python (keine Qt-Imports)
  - wählt unter Linux automatisch `vulkan`, wenn ein Vulkan-Loader gefunden wird
  - setzt frühzeitig Env-Variablen für Qt Quick / RHI:
    - `QT_QUICK_BACKEND=rhi`
    - `QSG_RHI_BACKEND=vulkan|opengl`
    - bzw. `QT_QUICK_BACKEND=software`
  - schreibt `PYDAW_GFX_BACKEND_EFFECTIVE` zur Diagnose

### ✅ Geändert
- `main.py`
  - ruft `configure_graphics_backend()` **vor** dem Import von `pydaw.app` / PyQt6 auf

- `requirements.txt`
  - bereinigt (keine "Header"-Zeilen ohne #)
  - ergänzt:
    - `PyOpenGL` / `PyOpenGL-accelerate` (für den optionalen Arranger-GPU-Overlay)
    - `vulkan` + `wgpu` (Linux, optional / future-proof)

- `INSTALL.md`
  - aktualisierte Beispielpfade
  - Vulkan-Systempakete + `vulkaninfo`-Test
  - Override-Beispiele für Fallback

## Nutzung / Tests
### Default (Linux)
```bash
python3 main.py
```

### Override
```bash
PYDAW_GFX_BACKEND=opengl python3 main.py
PYDAW_GFX_BACKEND=software python3 main.py
```

### Vulkan System Packages (Debian/Ubuntu)
```bash
sudo apt update
sudo apt install libvulkan1 mesa-vulkan-drivers vulkan-tools
vulkaninfo | head
```

## Notes
- Das betrifft aktuell primär QtQuick/RHI (zukünftige Visuals/Renderer). Widgets-Painting bleibt CPU-basiert.
- Ein echter **Vulkan-Renderer** für den Arranger-Overlay (statt QOpenGLWidget/PyOpenGL) ist als nächste größere Aufgabe vorgesehen.

