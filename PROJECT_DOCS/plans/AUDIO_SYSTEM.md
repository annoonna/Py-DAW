# 🔊 AUDIO_SYSTEM — Wie unser Audio‑System wirklich funktioniert (SF2 + Pro Sampler + Pro Drum Machine)

> Ziel dieser Datei: **Jeder Kollege** soll danach sofort wissen:
> - **wo** Audio & MIDI durchlaufen
> - **warum** SF2 / Pro Audio Sampler / Pro Drum Machine *parallel* funktionieren
> - **wie** Track‑Kanäle getrennt bleiben (auch wenn alle das gleiche Pitch‑Spektrum C‑1…C9 nutzen)
> - **wie** VU‑Meter/Peaks angeschlossen sind
> - **wo** man ein **neues Instrument** sauber einhängt

---

## 1) Grundprinzip: Routing ist Track‑ID, nicht Pitch

In PyDAW ist ein „Kanal“ im Audio‑System **kein MIDI‑Kanal** und auch **nicht** eine bestimmte Note.

✅ **Der Kanal ist die Track‑ID** (`Track.id`).

- Jede Spur (Instrument oder Audio) hat eine eindeutige ID wie `trk_ab12cd34ef`.
- MIDI‑Noten (Pitch 0…127) werden immer **zusammen mit der Track‑ID** betrachtet.
- Dadurch können **mehrere Instrumente gleichzeitig die gleiche Note** (z. B. C3) spielen, ohne sich gegenseitig zu stören.

**Wichtig:**
- Pitch‑Bereich (C‑1…C9) ist nur *die Tastatur‑Skala* im Editor.
- *Welche Bedeutung* ein Pitch hat, entscheidet das Instrument:
  - Sampler: Pitch = Note/Keyzone/Root‑Bezug
  - Drum‑Machine: Pitch = Pad‑Mapping (Basisnote + Index)
  - SF2: Pitch = Note im SoundFont‑Preset

---

## 2) Datenmodell: Wo steht „welche Spur ist welches Instrument“?

### 2.1 Track & Clip
Datei: `pydaw/model/project.py`

- `Track.kind`: `"audio" | "instrument" | "bus" | "master"`
- `Track.plugin_type`: (Pro-DAW‑Style Instrument‑Routing)
  - `"sf2"`, `"sampler"`, `"drum_machine"`, oder beliebige Strings für zukünftige Plugins
- `Track.sf2_path`, `sf2_bank`, `sf2_preset`: Legacy/SF2‑State

- `Clip.kind`: `"audio" | "midi"`
- `Clip.track_id`: **entscheidend** für Routing (welche Spur)

### 2.2 Warum `plugin_type` wichtig ist
Datei: `pydaw/audio/arrangement_renderer.py`

Beim Arranger‑Playback gilt:
- **SF2‑Spur** (plugin_type == `"sf2"` oder auto‑detected via `sf2_path`) → wird **vorgerendert** zu WAV
- **Alle anderen Instrument‑Spuren** → bekommen **Live‑MIDI‑Events** (Realtime dispatch) an das registrierte Engine‑Objekt

---

## 3) Überblick: Playback‑Pipeline (Arranger)

### 3.1 „Prepare“ (nicht realtime)
Datei: `pydaw/audio/audio_engine.py`

- Beim Start von Playback (oder bei Veränderungen) wird die Arrangement‑Vorbereitung gestartet.
- Dabei wird:
  - Audio‑Clips geladen/gekürzt/gestretched (aus Cache wenn möglich)
  - **SF2‑MIDI‑Clips** per `fluidsynth` in WAV gerendert (Cache: `~/.cache/Py_DAW/`)
  - eine `ArrangementState` aufgebaut: vorbereitete Clips + MIDI‑Events

### 3.2 Realtime Callback (sounddevice/JACK)
Dateien:
- `pydaw/audio/hybrid_engine.py` (HybridAudioCallback)
- `pydaw/audio/audio_engine.py` (Legacy sounddevice arrangement callback)

Realtime‑Block (Frames) macht:
1. **MIDI‑Events dispatchen** (nur für non‑SF2 Instrumente)
2. Pro Track:
   - vorbereitete Audio‑Clips in Track‑Buffer mischen
   - Track‑Vol/Pan/Mute/Solo anwenden
   - Track‑Meter aktualisieren
3. Zusätzliche Quellen (**Pull‑Sources**, z. B. Pro Sampler/Drum) einmischen
4. In Master summieren, Master‑Meter aktualisieren, ausgeben

---

## 4) Instrument‑Typen im Detail

### 4.1 SF2 Instrument (SoundFont) — „Render‑to‑WAV“
**Warum?** Stabil, realtime‑sicher, keine Synth‑Graph‑Komplexität.

**Codepfad:**
- `pydaw/audio/arrangement_renderer.py`
  - bei MIDI‑Clips auf Instrument‑Tracks mit `plugin_type == "sf2"`
  - ruft `ensure_rendered_wav(...)` auf
- `pydaw/audio/midi_render.py`
  - erzeugt kleine `.mid` Datei (mido)
  - ruft System‑Binary `fluidsynth` auf
  - schreibt gerendertes WAV in `~/.cache/Py_DAW/`

**Wichtig:**
- SF2 Audio ist danach „normaler Audio‑Clip“ im Renderer.
- Track‑Fader/VU greifen ganz normal, weil es in `render_track()` landet.

**Voraussetzungen:**
- `fluidsynth` muss im System verfügbar sein.
- Python deps: `mido` (für MIDI‑File build)

---

### 4.2 Pro Audio Sampler — Live Engine + Pull‑Source
Plugin‑Ordner: `pydaw/plugins/sampler/`

**1) Engine**
- `pydaw/plugins/sampler/sampler_engine.py` (`ProSamplerEngine`)
  - lädt Samples
  - `trigger_note(...)` (Preview / One‑shot)
  - `note_on(...)`/`note_off(...)` (Live/Playback)
  - `pull(frames, sr)` → liefert Stereo‑Block

**2) Widget**
- `pydaw/plugins/sampler/sampler_widget.py`
  - registriert Pull‑Source im AudioEngine:
    - `audio_engine.register_pull_source(name, pull_fn)`
  - setzt `_pydaw_track_id` **auf dem Pull‑Callable**

**3) Track‑Routing über SamplerRegistry**
- `pydaw/plugins/sampler/sampler_registry.py`
- Registrierung erfolgt zentral in:
  - `pydaw/ui/main_window.py` → `_add_instrument_to_device()`
    - sobald ein Device mit `.engine` und `trigger_note` existiert
    - wird `SamplerRegistry.register(track_id, engine, widget)` aufgerufen

**Playback:**
- `arrangement_renderer.py` erzeugt `PreparedMidiEvent(track_id, pitch, velocity, on/off, ...)`
- `hybrid_engine.py` dispatcht diese Events an `SamplerRegistry.note_on(track_id, ...)`

✅ Ergebnis: Jeder Sampler‑Track ist isoliert, obwohl alle die gleichen Pitches nutzen.

---

### 4.3 Pro Drum Machine — 16 Pads (je Pad eigener Sampler) + Pull‑Source
Plugin‑Ordner: `pydaw/plugins/drum_machine/`

**Engine:** `pydaw/plugins/drum_machine/drum_engine.py`
- `DrumMachineEngine` besteht aus 16 `DrumSlot`
- Jeder Slot hat eine eigene `ProSamplerEngine` Instanz
- Mapping:
  - `base_note = 36` (nach interner Note‑Namen‑Logik ist das **C2**, weil C4=60)
  - `pitch_to_slot_index(pitch) = pitch - base_note`

**Wichtig:**
- Drum Machine implementiert bewusst **die gleiche API wie Sampler**:
  - `trigger_note()`, `note_on()`, `pull()`
- Dadurch funktioniert sie sofort mit:
  - **Note‑Preview** (MainWindow → SamplerRegistry → `trigger_note`)
  - **Arranger‑Playback** (PreparedMidiEvent → SamplerRegistry → `note_on`)

**Widget:** `pydaw/plugins/drum_machine/drum_widget.py`
- registriert Pull‑Source **mit Wrapper‑Funktion** (kein bound method!)
- setzt `pull_fn._pydaw_track_id = lambda: self.track_id`

---

## 5) Warum schlagen Sampler/Drums im Mixer nur dann aus, wenn `_pydaw_track_id` stimmt?

### 5.1 Pull‑Sources
Die Pro‑Instrumente liefern Audio nicht als „Clip“, sondern als **Pull‑Source**:

- `AudioEngine.register_pull_source(name, fn)`
- `fn(frames, sr)` → `np.ndarray (frames,2) float32`

### 5.2 Track‑aware Mixing
Damit Pull‑Audio **in den richtigen Track‑Kanal** geht, muss der Audio‑Callback wissen:
> „Zu welcher Track‑ID gehört dieses Pull‑Signal?“

Das passiert über das optionale Attribut:
- `fn._pydaw_track_id` (String ODER Callable → String)

Wenn dieses Tag fehlt:
- Pull‑Audio wird als „global“ behandelt und landet (historisch) im Master
- Track‑VU bleibt tot
- Track‑Fader greifen nicht korrekt

### 5.3 Wo wird das angewandt?
- `pydaw/audio/audio_engine.py`
  - Legacy sounddevice arrangement callback: **track‑aware Pull mixing** (v0.0.20.52)
  - schreibt `AudioEngine._direct_peaks[track_id]`
- `pydaw/audio/hybrid_engine.py`
  - HybridAudioCallback + `render_for_jack()` mischen Pull‑Sources ebenfalls track‑aware

---

## 6) VU‑Meter: Datenweg (verlässlichster Pfad)

### 6.1 AudioThread schreibt Peaks
Datei: `pydaw/audio/audio_engine.py`

- In Realtime‑Callbacks werden Peaks direkt geschrieben:
  - Master: `_direct_peaks["__master__"] = (l, r)`
  - Track: `_direct_peaks[track_id] = (l, r)`

### 6.2 GUI liest Peaks
Datei: `pydaw/ui/mixer.py`

- `_MixerStrip._update_vu_meter()` läuft ~30 FPS im GUI‑Thread
- Priorität:
  1) `AudioEngine.read_direct_track_peak(track_id)` / `read_master_peak()`
  2) Hybrid bridge MeterRing
  3) Bridge `read_track_peak()`
  4) Legacy `read_track_peak()`

**Merke:** Wenn du ein neues Audio‑Signal in einen Track mischst, aber nicht in `_direct_peaks` reflektierst, bleibt die Anzeige ggf. tot.

---

## 7) Editor‑Integration (Piano Roll / Notation)

### 7.1 Piano Roll — Note Preview (Mouse)
Datei: `pydaw/ui/pianoroll_canvas.py`

- Beim Klick/Setzen von Noten wird Preview getriggert:
  - `self.project.preview_note(pitch, velocity, duration_ms)`

Datei: `pydaw/services/project_service.py`
- `preview_note(...)` emittiert Qt‑Signal `note_preview(pitch, vel, ms)`

Datei: `pydaw/ui/main_window.py`
- `note_preview` wird geroutet zu:
  - `SamplerRegistry.trigger_note(selected_track_id, pitch, ...)`

✅ Ergebnis:
- Preview geht **spurbezogen** (selected track), nicht global.

### 7.2 Notation — Live MIDI Ghost Notes
Datei: `pydaw/ui/notation/notation_view.py`

- Notation zeigt Live‑Input als **Ghost Noteheads**:
  - `handle_live_note_on/off(...)`

Live MIDI Quelle:
- `pydaw/services/midi_manager.py`
  - liest MIDI in Thread
  - emittiert `live_note_on/off` im Qt‑Thread

MainWindow verbindet:
- `self.services.midi.live_note_on.connect(self.editor_tabs.notation.handle_live_note_on)`

**Hinweis:** Notation‑Klick‑Preview (wie PianoRoll) ist aktuell nicht überall implementiert. (Kann später über `project.preview_note(...)` ergänzt werden.)

---

## 8) „Neues Instrument einbauen“ — Checkliste für Kollegen

### 8.1 Minimal‑Definition
Ein neues Instrument‑Plugin muss 3 Dinge liefern:

1) **Engine** (Audio):
- `pull(frames, sr) -> np.ndarray (frames,2) float32 | None`
- `trigger_note(pitch, velocity, duration_ms) -> bool` (für Preview)
- Optional: `note_on(pitch, velocity)`, `note_off(pitch)`

2) **Widget** (UI/Device):
- `self.engine = <EngineInstanz>`
- `set_track_context(track_id)` (oder zumindest `track_id`‑Property)

3) **Pull‑Source Registrierung** (damit Mix/VU/Fader funktionieren):
- `audio_engine.register_pull_source("<name>", pull_fn)`
- `pull_fn._pydaw_track_id = lambda: self.track_id`  (oder String)


### 8.2 Wo registriere ich das Plugin in der UI?
Datei: `pydaw/plugins/registry.py`

- `get_instruments()` liefert Liste von `InstrumentSpec`
- Füge neuen Eintrag hinzu:
  - `plugin_id` eindeutig
  - `factory(project_service, audio_engine) -> QWidget`


### 8.3 Wo wird die Engine „track‑fähig“ gemacht?
- `pydaw/ui/device_panel.py`
  - ruft `spec.factory(...)`
  - setzt `w.track_id = track_id` (wenn existiert)
  - ruft `w.set_track_context(track_id)` (wenn existiert)

- `pydaw/ui/main_window.py` (`_add_instrument_to_device`)
  - registriert automatisch jedes Device mit `.engine` + `trigger_note` in der `SamplerRegistry`


### 8.4 Typische Fehler (und Fix)

❌ **Fehler:** `'_method' object has no attribute '_pydaw_track_id'`
- Ursache: `self.engine.pull` ist bound method, kann keine Attribute tragen.
- Fix: Wrapper‑Funktion definieren:
  ```python
  def pull_fn(frames, sr):
      return self.engine.pull(frames, sr)
  pull_fn._pydaw_track_id = lambda: self.track_id
  audio_engine.register_pull_source("MyInstrument", pull_fn)
  ```

❌ **Fehler:** Track‑VU bleibt tot
- Ursache: Pull‑Source hat kein `_pydaw_track_id` oder Track‑ID ist leer.
- Fix: Track‑Context setzen und `_pydaw_track_id` taggen.

❌ **Fehler:** Instrument spielt im Arranger nicht
- Ursache 1: Engine nicht in `SamplerRegistry` registriert.
  - Fix: `.engine` + `trigger_note` bereitstellen, Device über DevicePanel hinzufügen.
- Ursache 2: Track ist kein `kind="instrument"`.
  - Fix: Track‑Typ prüfen.

---

## 9) Ordner‑Konventionen (Plugins / Presets / FX)

Aktuell im Repo:
- Instrument‑Plugins: `pydaw/plugins/<name>/`
  - `sampler/`
  - `drum_machine/`

Empfohlene Erweiterung (für Kollegen‑Konvention, noch nicht überall genutzt):
- Effekte: `pydaw/plugins_fx/<fx_name>/` oder `pydaw/plugins/effects/<fx_name>/`
- Presets: `pydaw/presets/<plugin_id>/...`
- Factory‑Registrierung:
  - Instruments: `pydaw/plugins/registry.py`
  - (später) FX Registry: z. B. `pydaw/plugins_fx/registry.py`

---

## 10) Relevante Dateien — Quick Map

### Audio Core
- `pydaw/audio/audio_engine.py` — Backends, Callback, Pull‑Sources, Peaks
- `pydaw/audio/hybrid_engine.py` — HybridAudioCallback, Bridge, Track‑Mixing
- `pydaw/audio/arrangement_renderer.py` — Prepare, Clips, MIDI‑Events
- `pydaw/audio/midi_render.py` — SF2 Render‑to‑WAV über fluidsynth
- `pydaw/audio/ring_buffer.py` — lock‑free Param/Meter Ringe

### Plugins
- `pydaw/plugins/registry.py` — Instrument‑Registry
- `pydaw/plugins/sampler/*` — Pro Audio Sampler
- `pydaw/plugins/drum_machine/*` — Pro Drum Machine

### UI / Routing
- `pydaw/ui/device_panel.py` — Device‑Chain pro Track (Factory + set_track_context)
- `pydaw/ui/main_window.py` — SamplerRegistry wiring + note_preview routing
- `pydaw/ui/mixer.py` — VU‑Meter Anzeige + Fader UI
- `pydaw/ui/pianoroll_canvas.py` — Note preview (Mouse)
- `pydaw/ui/notation/notation_view.py` — Ghost Notes + Notation Rendering

### Services
- `pydaw/services/project_service.py` — `note_preview` Signal
- `pydaw/services/midi_manager.py` — Live MIDI + Recording

