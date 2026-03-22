# Changelog — v0.0.20.470

## CLAP GUI Async-IO Host Support

### Neu
- Host-Support für `clap.posix-fd-support`
- Host-Support für `clap.timer-support`
- Qt-Spiegelung registrierter CLAP-GUI-FDs via `QSocketNotifier`
- Qt-Spiegelung registrierter CLAP-GUI-Timer via `QTimer`

### Geändert
- `ClapAudioFxWidget` synchronisiert GUI-Async-Quellen nur solange ein CLAP-Editor wirklich offen ist
- FD-/Timer-Events pumpen nach dem Dispatch wieder gezielt `on_main_thread()`

### Risiko
- bewusst klein gehalten
- keine Änderung am Audio-Thread
- keine Änderung an DSP oder Routing
- Fokus ausschließlich auf CLAP-GUI-Lifecycle unter Linux/X11/XWayland
