# v0.0.20.289 — AETERNA Widget Hotfix

- fixed local AETERNA widget build bug in the modulation toolbar
- removed duplicated insertion of the preview toolbar layout
- removed duplicated creation of the modulation preview widget
- replaced invalid stretch handling in the grid toolbar with safe column stretch
- shortened the long preview hint text so it no longer overwhelms the preview area

Safety: only `pydaw/plugins/aeterna/aeterna_widget.py` changed.
