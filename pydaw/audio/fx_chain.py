# -*- coding: utf-8 -*-
"""Audio FX Chain (serielle Effekte + Container mit Mix/WetGain).

Engine-first MVP:
- JSON-safe chain spec lives in Track.audio_fx_chain
- HybridAudioCallback applies per-track chain BEFORE volume/pan and BEFORE peaks.
- Also applies to Pull Sources (Sampler/Drum live audio).

Spec (Track.audio_fx_chain):
{
  "type": "chain",
  "mix": 1.0,          # 0..1
  "wet_gain": 1.0,     # linear
  "devices": [
     {"plugin_id":"chrono.fx.gain","id":"afx_xxx","enabled":true,"params":{"gain":1.0}},
     ...
  ]
}

Notes:
- Real-time safety: no allocations in the audio callback.
- All scratch buffers are preallocated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore


def _clamp01(x: float) -> float:
    try:
        x = float(x)
    except Exception:
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _rt_get_smooth(rt, key: str, default: float = 0.0) -> float:
    """Read a realtime parameter value in a version-tolerant way."""
    try:
        if rt is None:
            return float(default)
        if hasattr(rt, "get_smooth"):
            return float(rt.get_smooth(key, default))
        if hasattr(rt, "get_param"):
            return float(rt.get_param(key, default))
        if hasattr(rt, "get_target"):
            return float(rt.get_target(key, default))
    except Exception:
        pass
    return float(default)


def _gain_from_params(params: dict, default: float = 1.0) -> float:
    """Return linear gain from a device params dict (supports gain_db)."""
    try:
        if not isinstance(params, dict):
            return float(default)
        if "gain" in params:
            return float(params.get("gain", default) or default)
        if "gain_db" in params:
            db = float(params.get("gain_db", 0.0) or 0.0)
            db = max(-120.0, min(24.0, db))
            return float(10.0 ** (db / 20.0))
    except Exception:
        pass
    return float(default)


class AudioFxBase:

    """Base class for audio FX (in-place)."""

    def process_inplace(self, buf, frames: int, sr: int) -> None:  # noqa: ANN001
        raise NotImplementedError


@dataclass
class GainFx(AudioFxBase):
    """Simple linear gain effect (no dB conversion in RT)."""

    gain_key: str
    rt_params: Any

    def process_inplace(self, buf, frames: int, sr: int) -> None:  # noqa: ANN001
        if np is None:
            return
        try:
            g = float(_rt_get_smooth(self.rt_params, self.gain_key, 1.0))
        except Exception:
            g = 1.0
        if g == 1.0:
            return
        try:
            # buf shape: (frames, 2)
            np.multiply(buf[:frames, :], g, out=buf[:frames, :])
        except Exception:
            return




@dataclass
class DistortionFx(AudioFxBase):
    """Simple waveshaper distortion (tanh) with drive + mix.

    drive: 0..1  (0 = none)
    mix:   0..1
    """

    drive_key: str
    mix_key: str
    rt_params: Any

    def process_inplace(self, buf, frames: int, sr: int) -> None:  # noqa: ANN001
        if np is None:
            return
        try:
            drive = float(_rt_get_smooth(self.rt_params, self.drive_key, 0.25))
        except Exception:
            drive = 0.25
        try:
            mix = _clamp01(float(_rt_get_smooth(self.rt_params, self.mix_key, 1.0)))
        except Exception:
            mix = 1.0
        if drive <= 0.0001 or mix <= 0.0001:
            return
        try:
            # pre-emphasis gain
            k = 1.0 + 20.0 * max(0.0, min(1.0, drive))
            wet = np.tanh(buf[:frames, :] * k)
            if mix >= 0.999:
                np.copyto(buf[:frames, :], wet)
            else:
                dry_scale = (1.0 - mix)
                np.multiply(buf[:frames, :], dry_scale, out=buf[:frames, :])
                np.add(buf[:frames, :], wet * mix, out=buf[:frames, :])
        except Exception:
            return


# ── v0.0.20.530: Device Containers (Bitwig-Style) ──────────────────────

class FxLayerContainer(AudioFxBase):
    """Parallel FX Layer — N layers processed independently, then mixed.

    Bitwig calls this "FX Layer": audio is split into N parallel paths,
    each path has its own serial device chain, results are summed.

    Data format in audio_fx_chain.devices[]:
    {
      "plugin_id": "chrono.container.fx_layer",
      "id": "afx_xxx",
      "enabled": true,
      "params": {"mix": 1.0},
      "layers": [
        {"name": "Layer 1", "enabled": true, "volume": 1.0, "devices": [...]},
        {"name": "Layer 2", "enabled": true, "volume": 1.0, "devices": [...]},
      ]
    }
    """

    def __init__(self, track_id: str, device_id: str, layers_spec: List[dict],
                 rt_params: Any, max_frames: int = 8192, sr: int = 48000):
        self.track_id = str(track_id or "")
        self.device_id = str(device_id or "")
        self.rt_params = rt_params
        self._sr = int(sr) if sr else 48000
        self.mix_key = f"afx:{self.track_id}:{self.device_id}:layer_mix"
        self._layers: List[_FxLayer] = []
        self._layer_buf = None
        self._sum_buf = None

        # Ensure mix RT param
        try:
            if hasattr(rt_params, "ensure"):
                rt_params.ensure(self.mix_key, 1.0)
        except Exception:
            pass

        # Preallocate buffers
        if np is not None:
            try:
                self._layer_buf = np.zeros((int(max_frames), 2), dtype=np.float32)
                self._sum_buf = np.zeros((int(max_frames), 2), dtype=np.float32)
            except Exception:
                pass

        # Compile layers
        if isinstance(layers_spec, list):
            for i, lspec in enumerate(layers_spec):
                if not isinstance(lspec, dict):
                    continue
                if lspec.get("enabled", True) is False:
                    continue
                layer_devices_spec = lspec.get("devices", [])
                vol = float(lspec.get("volume", 1.0) or 1.0)
                name = str(lspec.get("name", f"Layer {i + 1}"))
                # Each layer is a mini ChainFx with its own device list
                try:
                    layer_chain = ChainFx(
                        track_id=track_id,
                        chain_spec={"type": "chain", "mix": 1.0, "wet_gain": 1.0, "devices": layer_devices_spec},
                        rt_params=rt_params,
                        max_frames=max_frames,
                        sr=sr,
                    )
                    self._layers.append(_FxLayer(name=name, volume=vol, chain=layer_chain))
                except Exception:
                    continue

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if np is None or not self._layers or self._sum_buf is None or self._layer_buf is None:
            return
        frames = int(frames)
        if frames <= 0 or frames > self._sum_buf.shape[0]:
            return

        mix = _clamp01(float(_rt_get_smooth(self.rt_params, self.mix_key, 1.0)))
        if mix <= 0.001:
            return  # fully dry — no parallel processing needed

        # Zero the sum buffer
        self._sum_buf[:frames, :] = 0.0

        n_active = 0
        for layer in self._layers:
            try:
                # Copy input into layer scratch
                np.copyto(self._layer_buf[:frames, :], buf[:frames, :])
                # Process layer's serial chain
                layer.chain.process_inplace(self._layer_buf, frames, sr)
                # Add to sum with layer volume
                if layer.volume != 1.0:
                    self._sum_buf[:frames, :] += self._layer_buf[:frames, :] * layer.volume
                else:
                    self._sum_buf[:frames, :] += self._layer_buf[:frames, :]
                n_active += 1
            except Exception:
                continue

        if n_active == 0:
            return

        # Normalize by number of active layers to prevent clipping
        if n_active > 1:
            self._sum_buf[:frames, :] /= float(n_active)

        # Blend: buf = dry*(1-mix) + sum*mix
        if mix >= 0.999:
            np.copyto(buf[:frames, :], self._sum_buf[:frames, :])
        else:
            dry_scale = 1.0 - mix
            np.multiply(buf[:frames, :], dry_scale, out=buf[:frames, :])
            np.add(buf[:frames, :], self._sum_buf[:frames, :] * mix, out=buf[:frames, :])


@dataclass
class _FxLayer:
    """One layer inside an FxLayerContainer."""
    name: str = "Layer"
    volume: float = 1.0
    chain: Any = None  # ChainFx


class ChainContainerFx(AudioFxBase):
    """Serial sub-chain that acts as a single device in the parent chain.

    Bitwig calls this simply "Chain": a group of FX in series collapsed into one card.
    Useful for organisation and for saving device-chain presets.

    Data format:
    {
      "plugin_id": "chrono.container.chain",
      "id": "afx_xxx",
      "enabled": true,
      "params": {"mix": 1.0},
      "devices": [...]
    }
    """

    def __init__(self, track_id: str, device_id: str, devices_spec: List[dict],
                 params: dict, rt_params: Any, max_frames: int = 8192, sr: int = 48000):
        self.track_id = str(track_id or "")
        self.device_id = str(device_id or "")
        self.rt_params = rt_params
        self.mix_key = f"afx:{self.track_id}:{self.device_id}:chain_mix"
        self._inner: Optional[ChainFx] = None

        # Ensure mix RT param
        mix_val = float(params.get("mix", 1.0) if isinstance(params, dict) else 1.0)
        try:
            if hasattr(rt_params, "ensure"):
                rt_params.ensure(self.mix_key, mix_val)
        except Exception:
            pass

        # Compile inner chain
        try:
            self._inner = ChainFx(
                track_id=track_id,
                chain_spec={"type": "chain", "mix": 1.0, "wet_gain": 1.0, "devices": devices_spec or []},
                rt_params=rt_params,
                max_frames=max_frames,
                sr=sr,
            )
        except Exception:
            self._inner = None

        # Preallocate dry buffer for mix
        self._dry = None
        if np is not None:
            try:
                self._dry = np.zeros((int(max_frames), 2), dtype=np.float32)
            except Exception:
                pass

    def process_inplace(self, buf, frames: int, sr: int) -> None:
        if self._inner is None or not self._inner.devices:
            return
        mix = _clamp01(float(_rt_get_smooth(self.rt_params, self.mix_key, 1.0)))
        if mix <= 0.001:
            return
        if np is None:
            return
        frames = int(frames)
        if frames <= 0:
            return

        if mix >= 0.999:
            # Fully wet — just run inner chain
            self._inner.process_inplace(buf, frames, sr)
            return

        # Partial mix: save dry, process, blend
        if self._dry is not None and frames <= self._dry.shape[0]:
            np.copyto(self._dry[:frames, :], buf[:frames, :])
            self._inner.process_inplace(buf, frames, sr)
            dry_scale = 1.0 - mix
            np.multiply(self._dry[:frames, :], dry_scale, out=self._dry[:frames, :])
            np.multiply(buf[:frames, :], mix, out=buf[:frames, :])
            np.add(buf[:frames, :], self._dry[:frames, :], out=buf[:frames, :])
        else:
            self._inner.process_inplace(buf, frames, sr)


class ChainFx:
    """Container that runs devices in series on wet buffer and blends with dry."""

    def __init__(self, track_id: str, chain_spec: Any, rt_params: Any, max_frames: int = 8192, sr: int = 48000):
        self.track_id = str(track_id or "")
        self.rt_params = rt_params
        self._sr = int(sr) if sr else 48000
        self.devices: List[AudioFxBase] = []
        self.enabled: bool = True
        # v0.0.20.380: Instrument devices (skipped from FX processing,
        # created as Vst3InstrumentEngine by AudioEngine instead)
        self.instrument_device_specs: List[dict] = []

        # track-level container keys (optional live automation later)
        self.mix_key = f"afxchain:{self.track_id}:mix"
        self.wet_gain_key = f"afxchain:{self.track_id}:wet_gain"

        # defaults from spec
        mix = 1.0
        wet_gain = 1.0
        devices_spec = []
        if isinstance(chain_spec, dict):
            self.enabled = bool(chain_spec.get("enabled", True))
            mix = float(chain_spec.get("mix", 1.0) or 1.0)
            wet_gain = float(chain_spec.get("wet_gain", 1.0) or 1.0)
            devices_spec = chain_spec.get("devices", []) or []
        elif isinstance(chain_spec, list):
            devices_spec = chain_spec

        # ensure RT defaults exist
        try:
            if hasattr(self.rt_params, "ensure"):
                self.rt_params.ensure(self.mix_key, float(mix))
                self.rt_params.ensure(self.wet_gain_key, float(wet_gain))
        except Exception:
            pass

        # preallocate wet buffer
        self._wet = None
        if np is not None:
            try:
                self._wet = np.zeros((int(max_frames), 2), dtype=np.float32)
            except Exception:
                self._wet = None

        # v0.0.20.641: Sidechain buffer (AP5 Phase 5B)
        # Set by HybridEngineBridge before process_inplace if sidechain routing exists.
        # Devices can read self._sidechain_buf to access the key signal.
        self._sidechain_buf = None  # numpy (frames, 2) or None

        # compile devices
        self._compile_devices(devices_spec)

    # --- v0.0.20.701: Plugin Sandbox (opt-in, crash-safe) --------------------

    @staticmethod
    def _is_sandbox_enabled() -> bool:
        """Check if plugin sandboxing is enabled in settings."""
        try:
            from pydaw.core.settings import SettingsKeys, get_value
            raw = get_value(SettingsKeys.audio_plugin_sandbox_enabled, None)
            if raw is None:
                return False  # default OFF
            if isinstance(raw, str):
                return raw.lower() in ("true", "1", "yes", "on")
            return bool(raw)
        except Exception:
            return False

    def _try_sandbox_fx(
        self, pid: str, did: str, plugin_path: str,
        plugin_name: str, plugin_type: str, params: dict,
    ) -> Optional[Any]:
        """Try to load a plugin via sandbox. Returns FX object or None.

        If sandbox is disabled or spawn fails → returns None (caller
        falls through to existing in-process loading code).

        v0.0.20.709: Checks per-plugin override (P6C) before global setting.
        """
        # v0.0.20.709: Per-plugin sandbox override (P6C)
        try:
            from pydaw.services.sandbox_overrides import should_sandbox
            global_on = self._is_sandbox_enabled()
            if not should_sandbox(plugin_type, plugin_path, global_on):
                return None
        except ImportError:
            if not self._is_sandbox_enabled():
                return None
        try:
            from pydaw.services.sandboxed_fx import SandboxedFx
            fx = SandboxedFx.create(
                track_id=self.track_id,
                slot_id=did,
                plugin_path=plugin_path,
                plugin_name=plugin_name,
                plugin_type=plugin_type,
                sample_rate=self._sr,
                block_size=int(self._wet.shape[0]) if self._wet is not None else 8192,
                channels=2,
            )
            if fx is not None:
                # Restore parameters
                for k, v in params.items():
                    if not k.startswith("__"):
                        try:
                            fx.set_param(str(k), float(v))
                        except (ValueError, TypeError):
                            pass
                return fx
        except Exception as e:
            import sys
            print(f"[SANDBOX] Fallback to in-process for {plugin_type}:{plugin_path}: {e}",
                  file=sys.stderr, flush=True)
        return None

    def _compile_devices(self, devices_spec: Any) -> None:
        self.devices = []
        if not isinstance(devices_spec, list):
            return
        for dev in devices_spec:
            if not isinstance(dev, dict):
                continue
            if dev.get("enabled", True) is False:
                continue
            pid = str(dev.get("plugin_id") or dev.get("type") or "")
            did = str(dev.get("id") or dev.get("device_id") or "")
            params = dev.get("params", {}) if isinstance(dev.get("params", {}), dict) else {}
            # v0.0.20.530: Device Containers — recognised before any other plugin type
            if pid == "chrono.container.fx_layer":
                try:
                    layers_spec = dev.get("layers", []) or []
                    fx = FxLayerContainer(
                        track_id=self.track_id, device_id=did,
                        layers_spec=layers_spec, rt_params=self.rt_params,
                        max_frames=self._wet.shape[0] if self._wet is not None else 8192,
                        sr=self._sr,
                    )
                    if fx._layers:
                        self.devices.append(fx)
                except Exception:
                    pass
                continue
            if pid == "chrono.container.chain":
                try:
                    inner_devices = dev.get("devices", []) or []
                    fx = ChainContainerFx(
                        track_id=self.track_id, device_id=did,
                        devices_spec=inner_devices, params=params,
                        rt_params=self.rt_params,
                        max_frames=self._wet.shape[0] if self._wet is not None else 8192,
                        sr=self._sr,
                    )
                    if fx._inner and fx._inner.devices:
                        self.devices.append(fx)
                except Exception:
                    pass
                continue
            # v0.0.20.536: Instrument Layer — treated as FX Layer in the audio chain
            # (parallel processing). The MIDI dispatch to multiple instruments is
            # handled separately by the audio engine; here we only process the
            # per-layer audio FX chains.
            if pid == "chrono.container.instrument_layer":
                try:
                    layers_spec = dev.get("layers", []) or []
                    fx = FxLayerContainer(
                        track_id=self.track_id, device_id=did,
                        layers_spec=layers_spec, rt_params=self.rt_params,
                        max_frames=self._wet.shape[0] if self._wet is not None else 8192,
                        sr=self._sr,
                    )
                    if fx._layers:
                        self.devices.append(fx)
                except Exception:
                    pass
                continue
            if pid.startswith("ext.lv2:"):
                uri = pid.split(":", 1)[1] if ":" in pid else ""
                try:
                    from pydaw.audio.lv2_host import describe_controls
                    ctrls = describe_controls(uri)
                    prefix = f"afx:{self.track_id}:{did}:lv2:"
                    for c in ctrls:
                        try:
                            sym = str(getattr(c, "symbol", "") or "")
                            if not sym:
                                continue
                            dv = float(getattr(c, "default", 0.0))
                            if isinstance(params, dict) and sym in params and isinstance(params.get(sym), (int, float)):
                                dv = float(params.get(sym))
                            if hasattr(self.rt_params, "ensure"):
                                self.rt_params.ensure(prefix + sym, dv)
                        except Exception:
                            continue
                except Exception:
                    pass
            if pid in ("chrono.fx.gain", "gain", "GainFx"):
                # store linear gain in RT store
                gain_key = f"afx:{self.track_id}:{did}:gain"
                default_gain = _gain_from_params(params, 1.0)
                try:
                    if hasattr(self.rt_params, "ensure"):
                        self.rt_params.ensure(gain_key, default_gain)
                except Exception:
                    pass
                self.devices.append(GainFx(gain_key=gain_key, rt_params=self.rt_params))
            elif pid in ("chrono.fx.distortion", "distortion", "DistortionFx"):
                drive_key = f"afx:{self.track_id}:{did}:drive"
                mix_key = f"afx:{self.track_id}:{did}:mix"
                # defaults from params
                drive = float(params.get("drive", 0.25) or 0.25)
                mix = float(params.get("mix", 1.0) or 1.0)
                try:
                    if hasattr(self.rt_params, "ensure"):
                        self.rt_params.ensure(drive_key, drive)
                        self.rt_params.ensure(mix_key, mix)
                except Exception:
                    pass
                self.devices.append(DistortionFx(drive_key=drive_key, mix_key=mix_key, rt_params=self.rt_params))

            # v0.0.20.642: Built-in Essential FX (AP8 Phase 8A)
            elif pid in ("chrono.fx.eq5", "chrono.fx.eq", "eq"):
                try:
                    from pydaw.audio.builtin_fx import ParametricEqFx
                    fx = ParametricEqFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.compressor", "compressor"):
                try:
                    from pydaw.audio.builtin_fx import CompressorFx
                    fx = CompressorFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr, chain_ref=self)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.reverb", "reverb"):
                try:
                    from pydaw.audio.builtin_fx import ReverbFx
                    fx = ReverbFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.delay2", "chrono.fx.delay", "delay"):
                try:
                    from pydaw.audio.builtin_fx import DelayFx
                    fx = DelayFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.peak_limiter", "chrono.fx.limiter", "limiter"):
                try:
                    from pydaw.audio.builtin_fx import LimiterFx
                    fx = LimiterFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass

            # v0.0.20.643: Creative FX with Scrawl curves (AP8 Phase 8B)
            elif pid in ("chrono.fx.chorus", "chorus"):
                try:
                    from pydaw.audio.creative_fx import ChorusFx
                    fx = ChorusFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.flanger", "flanger"):
                try:
                    from pydaw.audio.creative_fx import FlangerFx
                    fx = FlangerFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.distortion_plus", "distortion_plus"):
                try:
                    from pydaw.audio.creative_fx import DistortionPlusFx
                    fx = DistortionPlusFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.tremolo", "tremolo"):
                try:
                    from pydaw.audio.creative_fx import TremoloFx
                    fx = TremoloFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.filter_plus",):
                try:
                    from pydaw.audio.creative_fx import PhaserFx
                    fx = PhaserFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass

            # v0.0.20.644: Utility FX (AP8 Phase 8C)
            elif pid in ("chrono.fx.gate", "gate"):
                try:
                    from pydaw.audio.utility_fx import GateFx
                    fx = GateFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr, chain_ref=self)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.de_esser", "de_esser"):
                try:
                    from pydaw.audio.utility_fx import DeEsserFx
                    fx = DeEsserFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.stereo_widener", "stereo_widener"):
                try:
                    from pydaw.audio.utility_fx import StereoWidenerFx
                    fx = StereoWidenerFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.utility", "utility"):
                try:
                    from pydaw.audio.utility_fx import UtilityFx
                    fx = UtilityFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass
            elif pid in ("chrono.fx.spectrum_analyzer", "spectrum_analyzer"):
                try:
                    from pydaw.audio.utility_fx import SpectrumAnalyzerFx
                    fx = SpectrumAnalyzerFx(track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr)
                    self.devices.append(fx)
                except Exception:
                    pass

            elif pid.startswith("ext.lv2:"):
                # External LV2 Audio-FX (optional; requires python-lilv)
                uri = pid.split(":", 1)[1] if ":" in pid else ""
                # v0.0.20.701: Try sandbox first
                _sbx = self._try_sandbox_fx(pid, did, uri, uri, "lv2", params)
                if _sbx is not None:
                    self.devices.append(_sbx)
                    continue
                try:
                    from pydaw.audio.lv2_host import Lv2Fx
                    fx = Lv2Fx(uri=uri, track_id=self.track_id, device_id=did, rt_params=self.rt_params, params=params, sr=self._sr, max_frames=int(self._wet.shape[0]) if self._wet is not None else 8192)
                    # Even if instantiate fails, Lv2Fx is safe no-op; keep it only if it has audio IO
                    if getattr(fx, "_ok", False):
                        self.devices.append(fx)
                except Exception:
                    pass
            elif pid.startswith("ext.ladspa:") or pid.startswith("ext.dssi:"):
                # External LADSPA/DSSI Audio-FX (via ctypes)
                so_path = pid.split(":", 1)[1] if ":" in pid else ""
                # v0.0.20.701: Try sandbox first
                _sbx = self._try_sandbox_fx(pid, did, so_path, so_path, "ladspa", params)
                if _sbx is not None:
                    self.devices.append(_sbx)
                    continue
                try:
                    from pydaw.audio.ladspa_host import LadspaFx, _resolve_plugin_index
                    plugin_idx = _resolve_plugin_index(so_path, pid)
                    fx = LadspaFx(
                        path=so_path,
                        plugin_index=plugin_idx,
                        track_id=self.track_id,
                        device_id=did,
                        rt_params=self.rt_params,
                        params=params,
                        sr=self._sr,
                        max_frames=int(self._wet.shape[0]) if self._wet is not None else 8192,
                    )
                    if getattr(fx, "_ok", False):
                        self.devices.append(fx)
                    else:
                        import sys
                        _err = getattr(fx, "_err", "unknown")
                        print(f"[LADSPA] FX not ok for {so_path}: {_err}", file=sys.stderr, flush=True)
                except Exception as _ladspa_exc:
                    import sys, traceback
                    print(f"[LADSPA] COMPILE ERROR for {so_path}: {_ladspa_exc}", file=sys.stderr, flush=True)
                    traceback.print_exc(file=sys.stderr)
            elif pid.startswith("ext.vst3:"):
                # External VST3 (via pedalboard)
                vst_ref = pid.split(":", 1)[1] if ":" in pid else ""
                vst_ref = str(params.get("__ext_ref") or vst_ref)
                vst_plugin_name = str(params.get("__ext_plugin_name") or "")

                # v0.0.20.725: Skip blacklisted plugins (crash-prone)
                try:
                    from pydaw.services.plugin_probe import is_blacklisted
                    if is_blacklisted(vst_ref, "vst3", vst_plugin_name):
                        import sys
                        print(f"[VST3-FX] Skipping blacklisted plugin: {vst_ref}",
                              file=sys.stderr, flush=True)
                        continue
                except ImportError:
                    pass

                # v0.0.20.701: Try sandbox first (only for FX, not instruments)
                _is_inst_hint = bool(params.get("__ext_is_instrument", False))
                if not _is_inst_hint:
                    _sbx = self._try_sandbox_fx(pid, did, vst_ref, vst_plugin_name, "vst3", params)
                    if _sbx is not None:
                        self.devices.append(_sbx)
                        continue
                try:
                    from pydaw.audio.vst3_host import Vst3Fx, build_plugin_reference, resolve_plugin_reference, is_vst_instrument
                    ref_path, ref_name = resolve_plugin_reference(vst_ref, vst_plugin_name)
                    display_ref = build_plugin_reference(ref_path or vst_ref, ref_name)

                    # v0.0.20.380: Check if this is an INSTRUMENT (MIDI→Audio)
                    _is_inst = bool(params.get("__ext_is_instrument", False))
                    if not _is_inst:
                        try:
                            _is_inst = is_vst_instrument(vst_ref, vst_plugin_name)
                        except Exception:
                            _is_inst = False
                    if _is_inst:
                        import sys
                        print(f"[VST3] INSTRUMENT detected: {display_ref} — skipping FX chain, will be hosted as pull source",
                              file=sys.stderr, flush=True)
                        self.instrument_device_specs.append({
                            "plugin_id": pid,
                            "id": did,
                            "params": dict(params),
                            "vst_ref": vst_ref,
                            "vst_plugin_name": vst_plugin_name,
                        })
                        continue

                    # Normal Audio-FX path
                    fx = Vst3Fx(
                        path=vst_ref,
                        plugin_name=vst_plugin_name,
                        track_id=self.track_id,
                        device_id=did,
                        rt_params=self.rt_params,
                        params=params,
                        sr=self._sr,
                        max_frames=int(self._wet.shape[0]) if self._wet is not None else 8192,
                    )
                    if getattr(fx, "_ok", False):
                        self.devices.append(fx)
                    else:
                        import sys
                        _err = getattr(fx, "_err", "unknown")
                        print(f"[VST3] FX not ok for {display_ref}: {_err}", file=sys.stderr, flush=True)
                except Exception as _vst3_exc:
                    import sys, traceback
                    print(f"[VST3] COMPILE ERROR for {vst_ref}: {_vst3_exc}", file=sys.stderr, flush=True)
                    traceback.print_exc(file=sys.stderr)

            elif pid.startswith("ext.vst2:"):
                # v0.0.20.392: External VST2 via native ctypes host
                vst_ref = pid.split(":", 1)[1] if ":" in pid else ""
                vst_ref = str(params.get("__ext_ref") or vst_ref)
                vst_plugin_name = str(params.get("__ext_plugin_name") or "")

                # v0.0.20.725: Skip blacklisted plugins (crash-prone)
                try:
                    from pydaw.services.plugin_probe import is_blacklisted
                    if is_blacklisted(vst_ref, "vst2", vst_plugin_name):
                        import sys
                        print(f"[VST2-FX] Skipping blacklisted plugin: {vst_ref}",
                              file=sys.stderr, flush=True)
                        continue
                except ImportError:
                    pass

                # v0.0.20.701: Try sandbox first (only for FX, not instruments)
                _is_inst_hint = bool(params.get("__ext_is_instrument", False))
                if not _is_inst_hint:
                    _sbx = self._try_sandbox_fx(pid, did, vst_ref, vst_plugin_name, "vst2", params)
                    if _sbx is not None:
                        self.devices.append(_sbx)
                        continue
                try:
                    from pydaw.audio.vst2_host import Vst2Fx, is_vst2_instrument

                    # Check if instrument
                    _is_inst = bool(params.get("__ext_is_instrument", False))
                    if not _is_inst:
                        try:
                            _is_inst = is_vst2_instrument(vst_ref)
                        except Exception:
                            _is_inst = False
                    if _is_inst:
                        import sys
                        print(f"[VST2] INSTRUMENT detected: {vst_ref} — skipping FX chain, will be hosted as pull source",
                              file=sys.stderr, flush=True)
                        self.instrument_device_specs.append({
                            "plugin_id": pid,
                            "id": did,
                            "params": dict(params),
                            "vst_ref": vst_ref,
                            "vst_plugin_name": vst_plugin_name,
                        })
                        continue

                    # Normal Audio-FX path
                    fx = Vst2Fx(
                        path=vst_ref,
                        plugin_name=vst_plugin_name,
                        track_id=self.track_id,
                        device_id=did,
                        rt_params=self.rt_params,
                        params=params,
                        sr=self._sr,
                        max_frames=int(self._wet.shape[0]) if self._wet is not None else 8192,
                    )
                    if getattr(fx, "_ok", False):
                        self.devices.append(fx)
                    else:
                        import sys
                        _err = getattr(fx, "_err", "unknown")
                        print(f"[VST2] FX not ok for {vst_ref}: {_err}", file=sys.stderr, flush=True)
                except Exception as _vst2_exc:
                    import sys, traceback
                    print(f"[VST2] COMPILE ERROR for {vst_ref}: {_vst2_exc}", file=sys.stderr, flush=True)
                    traceback.print_exc(file=sys.stderr)

            elif pid.startswith("ext.clap:"):
                # v0.0.20.457: External CLAP via native ctypes host
                clap_ref = pid.split(":", 1)[1] if ":" in pid else ""
                clap_ref = str(params.get("__ext_ref") or clap_ref)
                clap_plugin_id = str(params.get("__ext_plugin_name") or "")

                # v0.0.20.725: Skip blacklisted plugins (crash-prone)
                try:
                    from pydaw.services.plugin_probe import is_blacklisted
                    _clap_path_check = clap_ref.split("::")[0].strip() if "::" in clap_ref else clap_ref
                    if is_blacklisted(_clap_path_check, "clap", clap_plugin_id):
                        import sys
                        print(f"[CLAP-FX] Skipping blacklisted plugin: {clap_ref}",
                              file=sys.stderr, flush=True)
                        continue
                except ImportError:
                    pass

                # v0.0.20.701: Try sandbox first (only for FX, not instruments)
                _is_inst_hint = bool(params.get("__ext_is_instrument", False))
                if not _is_inst_hint:
                    _sbx = self._try_sandbox_fx(pid, did, clap_ref, clap_plugin_id, "clap", params)
                    if _sbx is not None:
                        self.devices.append(_sbx)
                        continue
                try:
                    from pydaw.audio.clap_host import ClapFx, is_clap_instrument, split_plugin_reference

                    # Split reference into path + plugin_id
                    clap_path, clap_pid = split_plugin_reference(clap_ref)
                    if not clap_pid:
                        clap_pid = clap_plugin_id

                    # Check if instrument
                    _is_inst = bool(params.get("__ext_is_instrument", False))
                    if not _is_inst and clap_path and clap_pid:
                        try:
                            _is_inst = is_clap_instrument(clap_path, clap_pid)
                        except Exception:
                            _is_inst = False
                    if _is_inst:
                        import sys
                        print(f"[CLAP] INSTRUMENT detected: {clap_ref} — skipping FX chain, will be hosted as pull source",
                              file=sys.stderr, flush=True)
                        self.instrument_device_specs.append({
                            "plugin_id": pid,
                            "id": did,
                            "params": dict(params),
                            "clap_ref": clap_ref,
                            "clap_plugin_id": clap_pid,
                        })
                        continue

                    # Normal Audio-FX path
                    fx = ClapFx(
                        path=clap_path,
                        plugin_id=clap_pid,
                        track_id=self.track_id,
                        device_id=did,
                        rt_params=self.rt_params,
                        params=params,
                        sr=self._sr,
                        max_frames=int(self._wet.shape[0]) if self._wet is not None else 8192,
                    )
                    if getattr(fx, "_ok", False):
                        self.devices.append(fx)
                    else:
                        import sys
                        _err = getattr(fx, "_err", "unknown")
                        print(f"[CLAP] FX not ok for {clap_ref}: {_err}", file=sys.stderr, flush=True)
                except Exception as _clap_exc:
                    import sys, traceback
                    print(f"[CLAP] COMPILE ERROR for {clap_ref}: {_clap_exc}", file=sys.stderr, flush=True)
                    traceback.print_exc(file=sys.stderr)
            else:
                # ── v106: Neue Bitwig-Style Effekte via fx_processors ──
                try:
                    from pydaw.audio.fx_processors import create_fx_processor
                    prefix = f"afx:{self.track_id}:{did}"
                    fx = create_fx_processor(pid, prefix, self.rt_params, params)
                    if fx is not None:
                        # RT-Defaults für alle numerischen Params registrieren
                        try:
                            if hasattr(self.rt_params, "ensure"):
                                for k, v in params.items():
                                    if isinstance(v, (int, float)):
                                        self.rt_params.ensure(f"{prefix}:{k}", float(v))
                        except Exception:
                            pass
                        self.devices.append(fx)
                        continue
                except Exception:
                    pass
                continue

    def set_sidechain_buffer(self, buf) -> None:
        """Set the sidechain key signal buffer for this processing block.

        v0.0.20.641 (AP5 Phase 5B): Called by HybridEngineBridge before
        process_inplace. The buffer is a numpy (frames, 2) float32 array
        containing the pre-fader audio of the sidechain source track.
        Devices that support sidechain (compressor, gate, ducker) can
        read self._sidechain_buf during their process_inplace call.
        """
        self._sidechain_buf = buf

    def process_inplace(self, buf, frames: int, sr: int) -> None:  # noqa: ANN001
        if np is None:
            return
        if not self.enabled:
            return
        if not self.devices:
            return
        if self._wet is None:
            return

        frames = int(frames)
        if frames <= 0:
            return
        if frames > self._wet.shape[0]:
            frames = self._wet.shape[0]

        # Read container params
        try:
            mix = _clamp01(float(_rt_get_smooth(self.rt_params, self.mix_key, 1.0)))
        except Exception:
            mix = 1.0
        try:
            wet_gain = float(_rt_get_smooth(self.rt_params, self.wet_gain_key, 1.0))
        except Exception:
            wet_gain = 1.0

        # Wet path (process on copy)
        wet = self._wet
        try:
            np.copyto(wet[:frames, :], buf[:frames, :])
        except Exception:
            return
        for fx in self.devices:
            try:
                fx.process_inplace(wet, frames, sr)
            except Exception:
                continue
        if wet_gain != 1.0:
            try:
                np.multiply(wet[:frames, :], wet_gain, out=wet[:frames, :])
            except Exception:
                pass

        # Blend back to buf
        if mix >= 0.999:
            try:
                np.copyto(buf[:frames, :], wet[:frames, :])
            except Exception:
                pass
            return

        if mix <= 0.001:
            # keep dry (buf already dry)
            return

        try:
            # buf = dry*(1-mix) + wet*mix
            dry_scale = (1.0 - mix)
            np.multiply(buf[:frames, :], dry_scale, out=buf[:frames, :])
            np.add(buf[:frames, :], wet[:frames, :] * mix, out=buf[:frames, :])
        except Exception:
            return



def ensure_track_fx_params(project: Any, rt_params: Any) -> None:
    """Ensure RTParamStore keys exist for all Audio-FX chains.

    This is called from the GUI thread when a project snapshot changes,
    BEFORE compiled ChainFx objects are pushed to the audio thread.

    Keys (current MVP):
    - afxchain:{track_id}:mix
    - afxchain:{track_id}:wet_gain
    - afx:{track_id}:{device_id}:gain  (for chrono.fx.gain)
    """
    if rt_params is None:
        return
    try:
        tracks = getattr(project, "tracks", []) or []
    except Exception:
        tracks = []
    for t in tracks:
        try:
            tid = str(getattr(t, "id", ""))
        except Exception:
            tid = ""
        if not tid:
            continue
        chain = getattr(t, "audio_fx_chain", None)
        if not isinstance(chain, dict):
            continue
        mix = float(chain.get("mix", 1.0) or 1.0)
        wet_gain = float(chain.get("wet_gain", 1.0) or 1.0)
        try:
            if hasattr(rt_params, "ensure"):
                rt_params.ensure(f"afxchain:{tid}:mix", mix)
                rt_params.ensure(f"afxchain:{tid}:wet_gain", wet_gain)
        except Exception:
            pass

        devices = chain.get("devices", []) or []
        if not isinstance(devices, list):
            continue
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            pid = str(dev.get("plugin_id") or dev.get("type") or "")
            did = str(dev.get("id") or dev.get("device_id") or "")
            params = dev.get("params", {}) if isinstance(dev.get("params", {}), dict) else {}
            if not did:
                continue
            # v0.0.20.530: Device Container RT params
            if pid == "chrono.container.fx_layer":
                try:
                    if hasattr(rt_params, "ensure"):
                        rt_params.ensure(f"afx:{tid}:{did}:layer_mix", float(params.get("mix", 1.0) or 1.0))
                except Exception:
                    pass
                continue
            if pid == "chrono.container.chain":
                try:
                    if hasattr(rt_params, "ensure"):
                        rt_params.ensure(f"afx:{tid}:{did}:chain_mix", float(params.get("mix", 1.0) or 1.0))
                except Exception:
                    pass
                continue
            # v0.0.20.536: Instrument Layer RT params (same as FX Layer)
            if pid == "chrono.container.instrument_layer":
                try:
                    if hasattr(rt_params, "ensure"):
                        rt_params.ensure(f"afx:{tid}:{did}:layer_mix", float(params.get("mix", 1.0) or 1.0))
                except Exception:
                    pass
                continue
            if pid in ("chrono.fx.gain", "gain", "GainFx"):
                default_gain = _gain_from_params(params, 1.0)
                try:
                    if hasattr(rt_params, "ensure"):
                        rt_params.ensure(f"afx:{tid}:{did}:gain", default_gain)
                except Exception:
                    pass
            elif pid.startswith("ext.ladspa:") or pid.startswith("ext.dssi:"):
                # Register LADSPA control port values
                try:
                    if hasattr(rt_params, "ensure"):
                        for k, v in params.items():
                            if isinstance(v, (int, float)):
                                try:
                                    # Key format: afx:{track}:{device}:ladspa:{port_index}
                                    int(k)  # Only numeric keys are port indices
                                    rt_params.ensure(f"afx:{tid}:{did}:ladspa:{k}", float(v))
                                except ValueError:
                                    pass  # Skip non-numeric keys like __ext_kind
                except Exception:
                    pass
            elif pid.startswith("ext.vst3:") or pid.startswith("ext.vst2:"):
                # Register VST3/VST2 parameter values in RT store
                try:
                    vst_path = pid.split(":", 1)[1] if ":" in pid else ""
                    _vst_type = "vst2" if pid.startswith("ext.vst2:") else "vst3"
                    if hasattr(rt_params, "ensure") and vst_path:
                        prefix = f"afx:{tid}:{did}:{_vst_type}:"
                        for k, v in params.items():
                            if isinstance(v, (int, float)) and not k.startswith("__"):
                                rt_params.ensure(f"{prefix}{k}", float(v))
                except Exception:
                    pass
            elif pid.startswith("ext.clap:"):
                # v0.0.20.457: Register CLAP parameter values in RT store
                try:
                    if hasattr(rt_params, "ensure"):
                        prefix = f"afx:{tid}:{did}:clap:"
                        for k, v in params.items():
                            if isinstance(v, (int, float)) and not k.startswith("__"):
                                rt_params.ensure(f"{prefix}{k}", float(v))
                except Exception:
                    pass
            else:
                try:
                    from pydaw.audio.fx_processors import FX_PROCESSOR_MAP
                    if pid in FX_PROCESSOR_MAP and hasattr(rt_params, "ensure"):
                        prefix = f"afx:{tid}:{did}"
                        for k, v in params.items():
                            if isinstance(v, (int, float)):
                                rt_params.ensure(f"{prefix}:{k}", float(v))
                except Exception:
                    pass


def build_track_fx_map(project: Any, rt_params: Any, max_frames: int = 8192, sr: int = 48000) -> Dict[str, Optional[ChainFx]]:
    """Compile per-track ChainFx objects from a Project snapshot."""
    fx_map: Dict[str, Optional[ChainFx]] = {}
    try:
        tracks = getattr(project, "tracks", []) or []
    except Exception:
        tracks = []
    for t in tracks:
        try:
            tid = str(getattr(t, "id", ""))
        except Exception:
            tid = ""
        if not tid:
            continue
        chain = getattr(t, "audio_fx_chain", None)
        try:
            fx_map[tid] = ChainFx(track_id=tid, chain_spec=chain, rt_params=rt_params, max_frames=int(max_frames), sr=int(sr) if sr else 48000)
        except Exception:
            fx_map[tid] = None
    return fx_map