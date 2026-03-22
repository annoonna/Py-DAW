"""Service container wiring (v0.0.15.8 + fix11)."""

from __future__ import annotations

from dataclasses import dataclass
import os

from pydaw.core.threading import ThreadPoolService
from pydaw.services.project_service import ProjectService
from pydaw.audio.audio_engine import AudioEngine
from pydaw.services.transport_service import TransportService
from pydaw.services.launcher_service import LauncherService
from pydaw.services.cliplauncher_playback import ClipLauncherPlaybackService
from pydaw.services.metronome_service import MetronomeService
from pydaw.services.midi_service import MidiService
from pydaw.services.jack_client_service import JackClientService
from pydaw.services.recording_service import RecordingService
from pydaw.services.take_service import TakeService
from pydaw.services.fluidsynth_service import FluidSynthService
from pydaw.utils.logging_setup import get_logger

from pydaw.core.settings_store import get_value
from pydaw.core.settings import SettingsKeys
from pydaw.services.midi_mapping_service import MidiMappingService
from pydaw.services.automation_playback import AutomationPlaybackService
from pydaw.audio.automatable_parameter import AutomationManager
from pydaw.services.prewarm_service import PrewarmService
from pydaw.services.clip_context_service import ClipContextService
from pydaw.services.project_tab_service import ProjectTabService
from pydaw.services.editor_timeline_adapter import EditorTimelineAdapter

log = get_logger(__name__)


@dataclass
class ServiceContainer:
    threadpool: ThreadPoolService
    project: ProjectService
    audio_engine: AudioEngine
    transport: TransportService
    launcher: LauncherService
    metronome: MetronomeService
    midi: MidiService
    midi_mapping: MidiMappingService
    jack: JackClientService
    automation_playback: AutomationPlaybackService
    automation_manager: AutomationManager
    recording: RecordingService
    take: TakeService
    fluidsynth: FluidSynthService
    prewarm: PrewarmService
    clip_context: ClipContextService
    project_tabs: ProjectTabService
    # v0.0.20.612: Dual-Clock Phase C — Zeitadapter für Editoren
    editor_timeline: EditorTimelineAdapter | None = None

    @classmethod
    def create_default(cls) -> "ServiceContainer":
        threadpool = ThreadPoolService.create_default()
        project = ProjectService(threadpool=threadpool)

        audio_engine = AudioEngine()
        # forward engine status to the app status bus
        try:
            audio_engine.status.connect(lambda m: project.status.emit(m))
            audio_engine.error.connect(lambda m: project.error.emit(m))
        except Exception:
            pass
        # v0.0.20.428: Give ProjectService access to running VST engines for Bounce
        try:
            project._audio_engine_ref = audio_engine
        except Exception:
            pass
        transport = TransportService(
            bpm=project.ctx.project.bpm,
            time_signature=getattr(project.ctx.project, "time_signature", "4/4"),
        )

        # Binde AudioEngine an Project/Transport und starte/stopp-e
        # Arrangement-Playback, wenn der Transport spielt.
        try:
            audio_engine.bind_transport(project, transport)
        except Exception:
            # Fallback: AudioEngine bleibt im "none"/"silence"-Modus.
            pass
        launcher = LauncherService(project=project, transport=transport)

        # ClipLauncher realtime playback (AudioEvents/Loop) – optional service.
        try:
            cliplauncher_playback = ClipLauncherPlaybackService(
                project=project,
                transport=transport,
                audio_engine=audio_engine,
            )
            project.bind_cliplauncher_playback(cliplauncher_playback)
        except Exception:
            pass

        # Automation playback (read mode -> applies volume/pan curves while playing)
        automation_playback = AutomationPlaybackService(project=project, transport=transport)

        # Realtime parameter store lives on the AudioEngine. Mirror automation values
        # into the same RT store so DSP/FX can see timeline automation without any
        # direct GUI-thread writes into engine internals.
        rt_params = getattr(audio_engine, "rt_params", None)

        # Central Automation Manager (v0.0.20.89: Bitwig-style parameter automation)
        automation_manager = AutomationManager(rt_params=rt_params)

        # v0.0.20.173: Wire automation persistence (save/load) through ProjectService.
        # This keeps automation lanes across project reloads.
        try:
            setattr(project, 'automation_manager', automation_manager)
            # Import lanes when a project is opened/created
            project.project_opened.connect(lambda: project.load_automation_manager_from_project())
        except Exception:
            pass

        # Prewarm: prepare visible/active audio clips on BPM change (background).
        prewarm = PrewarmService(threadpool=threadpool, project_service=project, transport_service=transport)
        try:
            prewarm.status.connect(lambda m: project.status.emit(m))
            prewarm.error.connect(lambda m: project.error.emit(m))
        except Exception:
            pass

        metronome = MetronomeService(on_status=lambda m: project.status.emit(m))
        midi = MidiService(status_cb=lambda m: project.status.emit(m), project_service=project, transport=transport)

        # v0.0.20.422: Auto-connect all available MIDI inputs at startup.
        # Users often forget to manually connect controllers via MIDI Settings.
        try:
            _midi_inputs = midi.list_inputs()
            for _inp in _midi_inputs:
                try:
                    # Skip virtual/through ports — only connect real hardware
                    _inp_lower = _inp.lower()
                    if "through" in _inp_lower or "virmidi" in _inp_lower:
                        continue
                    midi.connect_input(_inp)
                except Exception:
                    pass
            if _midi_inputs:
                _connected = midi.connected_inputs()
                if _connected:
                    log.info("MIDI: Auto-connected %d input(s): %s", len(_connected), ", ".join(_connected))
        except Exception:
            pass

        jack = JackClientService(status_cb=lambda m: project.status.emit(m))
        try:
            audio_engine.bind_jack(jack)
        except Exception:
            pass

        midi_mapping = MidiMappingService(
            project=project,
            transport=transport,
            status_cb=lambda m: project.status.emit(m),
        )
        try:
            midi.message_obj.connect(midi_mapping.handle_mido_message)
        except Exception:
            pass

        # v0.0.20.416: Bridge MidiMappingService → AutomationManager for live slider updates.
        # Emit parameter_changed directly — FX widgets listen for their parameter_id.
        try:
            def _bridge_mapping_to_am(_tid, param_id, value):
                try:
                    automation_manager.parameter_changed.emit(str(param_id), float(value))
                except Exception:
                    pass
            midi_mapping.value_applied.connect(_bridge_mapping_to_am)
        except Exception:
            pass

        # v0.0.20.397: Also route MIDI CC to AutomationManager for knob MIDI Learn
        try:
            midi.message_obj.connect(automation_manager.handle_midi_message)
        except Exception:
            pass

        # v0.0.20.431: Give MidiMappingService direct access to AutomationManager
        # so that MIDI-recorded automation points land in the SAME store
        # as UI-drawn points (fixes invisible recorded automation bug).
        try:
            midi_mapping.set_automation_manager(automation_manager)
        except Exception:
            pass

        # v0.0.20.433: Give AutomationManager access to transport + project
        # so that Fast Path MIDI Learn (CC→Knob) can also record automation.
        try:
            automation_manager.set_transport(transport)
            automation_manager.set_project(project)
        except Exception:
            pass

        # v0.0.20.440: Auto-thin recorded lanes when transport stops
        try:
            def _on_playing_changed_thin(is_playing):
                if not is_playing:
                    try:
                        removed = automation_manager.thin_recorded_lanes()
                        if removed > 0:
                            project.status.emit(f"Auto-Thin: {removed} redundante Punkte entfernt")
                    except Exception:
                        pass
            transport.playing_changed.connect(_on_playing_changed_thin)
        except Exception:
            pass

        # Try to register a visible JACK/PipeWire client (non-fatal if unavailable)
        # NOTE: This is intentionally independent from the engine backend.
        # Many users want sounddevice (PortAudio) for playback, but still want a JACK
        # client so PyDAW is visible in qpwgraph for routing/recording.
        keys = SettingsKeys()
        enable_jack = os.environ.get("PYDAW_ENABLE_JACK", "0") in ("1", "true", "True", "yes", "on")
        if enable_jack and JackClientService.probe_available():
            try:
                jack.start_async(
                    in_ports=get_value(keys.jack_in_ports, 2),
                    out_ports=get_value(keys.jack_out_ports, 2),
                    monitor_inputs_to_outputs=get_value(keys.jack_input_monitor, False),
                )
            except Exception:
                pass
        elif enable_jack and (not JackClientService.probe_available()):
            log.warning(
                "JACK client enabled, but JACK server is not reachable. "
                "Tip: start via 'pw-jack python3 main.py' or ensure PipeWire-JACK/JACK is active."
            )

        # Initialize recording service (PipeWire/JACK support)
        recording = RecordingService()
        # v0.0.20.636: Wire buffer size from audio settings (AP2 Phase 2B)
        try:
            _keys = SettingsKeys()
            _buf = int(get_value(_keys.buffer_size, 512))
            recording.set_buffer_size(_buf)
        except Exception:
            pass
        log.info("Recording service initialized (backend: %s, buffer: %d)",
                 recording.get_backend(), recording.get_buffer_size())

        # v0.0.20.638: Load punch crossfade from settings into AudioConfig
        try:
            from pydaw.core.audio_config import audio_config
            _keys2 = SettingsKeys()
            _cf_ms = float(get_value(_keys2.punch_crossfade_ms, 10.0))
            audio_config.set_punch_crossfade_ms(_cf_ms)
        except Exception:
            pass

        # v0.0.20.639: TakeService for comping / take-lanes (AP2 Phase 2D)
        take_service = TakeService(project_service=project)
        log.info("TakeService initialized")
        
        # Initialize FluidSynth service (optional - won't crash if unavailable)
        fluidsynth = FluidSynthService()
        try:
            fluidsynth.error.connect(lambda m: project.error.emit(m))
            fluidsynth.status.connect(lambda m: project.status.emit(m))
        except Exception:
            pass
        
        if fluidsynth.is_available():
            log.info("FluidSynth service initialized")
        else:
            log.warning("FluidSynth service not available (optional feature)")

        # ClipContextService für Slot → Editor Integration
        clip_context = ClipContextService(project_service=project)

        # v0.0.20.612: Dual-Clock Phase C — EditorTimelineAdapter
        try:
            editor_timeline = EditorTimelineAdapter(
                transport=transport,
                launcher_playback=cliplauncher_playback,
            )
            # Brücke: ClipContextService → Adapter
            clip_context.editor_focus_changed.connect(editor_timeline.set_focus)
        except Exception as exc:
            log.warning("EditorTimelineAdapter not available: %s", exc)
            editor_timeline = None

        # Multi-Project Tab Service (Bitwig-Style multi-project tabs)
        project_tabs = ProjectTabService()
        try:
            project_tabs.status.connect(lambda m: project.status.emit(m))
            project_tabs.error.connect(lambda m: project.error.emit(m))
        except Exception:
            pass

        return cls(
            threadpool=threadpool,
            project=project,
            audio_engine=audio_engine,
            transport=transport,
            launcher=launcher,
            metronome=metronome,
            midi=midi,
            midi_mapping=midi_mapping,
            jack=jack,
            automation_playback=automation_playback,
            automation_manager=automation_manager,
            recording=recording,
            take=take_service,
            fluidsynth=fluidsynth,
            prewarm=prewarm,
            clip_context=clip_context,
            project_tabs=project_tabs,
            editor_timeline=editor_timeline,
        )


    def shutdown(self) -> None:
        """Best-effort shutdown for background audio/jack/transport resources."""
        # v0.0.20.612: EditorTimelineAdapter aufräumen
        try:
            if self.editor_timeline is not None:
                self.editor_timeline.shutdown()
        except Exception:
            pass
        # Stop recording if active
        try:
            if self.recording.is_recording():
                self.recording.stop_recording()
            self.recording.cleanup()
        except Exception:
            pass
        # Cleanup FluidSynth
        try:
            self.fluidsynth.cleanup()
        except Exception:
            pass
        # Stop transport timer first (it can trigger callbacks into other services).
        try:
            self.transport.stop()
        except Exception:
            pass
        # Stop launcher watchers.
        try:
            self.launcher.stop()
        except Exception:
            pass
        # Stop JACK client thread (if enabled).
        try:
            self.jack.stop()
        except Exception:
            pass
        # Stop audio engine stream.
        try:
            self.audio_engine.stop()
        except Exception:
            pass
        # Stop background workers.
        try:
            self.threadpool.shutdown()
        except Exception:
            pass