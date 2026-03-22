# CHANGELOG v0.0.20.715 — Rust Compile Fix

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Bugfix — cargo build --release Fehler beheben

## Problem
`cargo build --release` schlug fehl mit:
- `error[E0603]: enum import TrackParam is private` (engine.rs:995)
- `warning: unused imports: CStr, CString` (lv2_host.rs:27)
- `warning: unused imports: error, warn` (lv2_host.rs:29)

## Fix
- **engine.rs**: `use crate::audio_graph::TrackParam` → `use crate::ipc::TrackParam`
  (TrackParam ist in ipc.rs `pub`, in audio_graph.rs nur private re-imported)
- **lv2_host.rs**: Entfernt `CStr`, `CString`, `warn`, `error` aus Imports
  (werden erst bei FFI-Implementierung gebraucht)

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/engine.rs | TrackParam Import Fix |
| pydaw_engine/src/lv2_host.rs | Unused imports entfernt |
