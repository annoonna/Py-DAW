# -*- coding: utf-8 -*-
"""LV2 probe helper (subprocess).

Why?
-----
Native LV2 plugins are arbitrary shared libraries. Some can crash the host
process during instantiate() or run(). Python cannot catch SIGSEGV/SIGBUS.

This tool is invoked by pydaw.audio.lv2_host in a separate process to decide
whether a plugin should be allowed for in-process live hosting.

It prints a single JSON object to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys

import os
import glob
import site

def _ensure_lilv() -> tuple[object|None, str]:
    """Try to import lilv; in venvs without system-site-packages add dist-packages."""
    try:
        import lilv  # type: ignore
        return lilv, ""
    except Exception as e1:
        err1 = str(e1)
    # Common Debian/Kali locations (and versioned variants).
    cand: list[str] = []
    cand += ["/usr/lib/python3/dist-packages", "/usr/local/lib/python3/dist-packages"]
    cand += sorted(glob.glob("/usr/lib/python3*/dist-packages"))
    cand += sorted(glob.glob("/usr/local/lib/python3*/dist-packages"))
    # Also try site-packages (some systems).
    cand += sorted(glob.glob("/usr/lib/python3*/site-packages"))
    cand += sorted(glob.glob("/usr/local/lib/python3*/site-packages"))
    for p in cand:
        try:
            if p and os.path.isdir(p):
                site.addsitedir(p)
        except Exception:
            continue
    try:
        import lilv  # type: ignore
        return lilv, ""
    except Exception as e2:
        # Return the second error, but include the first one for context.
        return None, (str(e2) or err1)


def _safe_str(x) -> str:
    try:
        return str(x)
    except Exception:
        return ""


def _try_instantiate(plugin, sr: int):
    attempts = []
    for label, args in (
        ("plugin.instantiate(sr, [])", (sr, [])),
        ("plugin.instantiate(sr, None)", (sr, None)),
        ("plugin.instantiate(sr)", (sr,)),
    ):
        try:
            inst = plugin.instantiate(*args)
            if inst is not None:
                return inst, label
            attempts.append(f"{label} -> None")
        except TypeError as e:
            attempts.append(f"{label} -> TypeError: {e}")
        except Exception as e:
            attempts.append(f"{label} -> {type(e).__name__}: {e}")
    try:
        lilv, imp_err = _ensure_lilv()
        if lilv is None:
            attempts.append(f"import lilv failed: {imp_err}")
            raise RuntimeError("no lilv")

        if hasattr(lilv, "Instance"):
            for label, args in (
                ("lilv.Instance(plugin, sr, [])", (plugin, sr, [])),
                ("lilv.Instance(plugin, sr, None)", (plugin, sr, None)),
                ("lilv.Instance(plugin, sr)", (plugin, sr)),
            ):
                try:
                    inst = lilv.Instance(*args)  # type: ignore[attr-defined]
                    if inst is not None:
                        return inst, label
                    attempts.append(f"{label} -> None")
                except TypeError as e:
                    attempts.append(f"{label} -> TypeError: {e}")
                except Exception as e:
                    attempts.append(f"{label} -> {type(e).__name__}: {e}")
    except Exception:
        pass

    dbg = "; ".join(attempts[:6])
    if len(attempts) > 6:
        dbg += f"; …(+{len(attempts) - 6} more)"
    return None, dbg


def probe(uri: str, sr: int = 48000, frames: int = 64) -> dict:
    lilv, imp_err = _ensure_lilv()
    if lilv is None:
        return {"ok": False, "error": f"python-lilv import failed: {imp_err}"}
    try:
        import numpy as np  # type: ignore
    except Exception as e:
        return {"ok": False, "error": f"numpy import failed: {e}"}

    uri = str(uri or "")
    if not uri:
        return {"ok": False, "error": "empty uri"}

    w = lilv.World()
    w.load_all()
    plugins = w.get_all_plugins()
    p = plugins.get_by_uri(w.new_uri(uri))
    if p is None:
        return {"ok": False, "error": f"plugin not found: {uri}"}

    inst, how = _try_instantiate(p, int(sr))
    if inst is None:
        # Required features (if exposed)
        req = []
        try:
            for n in p.get_required_features():
                s = _safe_str(n)
                if s:
                    req.append(s)
        except Exception:
            req = []
        msg = "instantiate failed"
        if req:
            msg += "; required features: " + ", ".join(req[:8])
        if how:
            msg += f"; {how}"
        return {"ok": False, "error": msg}

    # Connect ports (audio in/out + control in)
    ns = getattr(w, "ns", None)
    audio_in = []
    audio_out = []
    ctl_in = []  # list[(port_index, default_value)]
    nports = int(p.get_num_ports())
    for i in range(nports):
        port = p.get_port_by_index(i)
        if port is None:
            continue
        try:
            if ns is not None and port.is_a(ns.lv2.AudioPort):
                if port.is_a(ns.lv2.InputPort):
                    audio_in.append(i)
                elif port.is_a(ns.lv2.OutputPort):
                    audio_out.append(i)
                continue
        except Exception:
            pass
        try:
            if ns is not None and port.is_a(ns.lv2.ControlPort) and port.is_a(ns.lv2.InputPort):
                dv = 0.0
                try:
                    _mn, _mx, _df = p.get_port_ranges_float(port)
                    if _df is not None:
                        dv = float(_df)
                except Exception:
                    dv = 0.0
                ctl_in.append((i, dv))
        except Exception:
            continue

    # Need at least 1 in and 1 out to be useful for Audio-FX.
    if not audio_in or not audio_out:
        return {"ok": False, "error": "no audio I/O ports"}

    max_frames = max(256, int(frames))
    bufs = {}
    try:
        for idx in audio_in:
            b = np.zeros((max_frames,), dtype=np.float32)
            inst.connect_port(int(idx), b)
            bufs[f"ain{idx}"] = b
        for idx in audio_out:
            b = np.zeros((max_frames,), dtype=np.float32)
            inst.connect_port(int(idx), b)
            bufs[f"aout{idx}"] = b
        for idx, dv in ctl_in[:64]:
            b = np.zeros((1,), dtype=np.float32)
            try:
                b[0] = np.float32(float(dv))
            except Exception:
                pass
            inst.connect_port(int(idx), b)
            bufs[f"ctl{idx}"] = b
    except Exception as e:
        return {"ok": False, "error": f"connect_port failed: {e}"}

    # Activate + run a small block.
    try:
        try:
            inst.activate()
        except Exception:
            pass

        # Provide a non-zero input signal for some plugins.
        try:
            for k, b in bufs.items():
                if k.startswith("ain"):
                    b[: int(frames)] = 0.25
        except Exception:
            pass

        inst.run(int(frames))
    except Exception as e:
        return {"ok": False, "error": f"run failed: {type(e).__name__}: {e}"}
    finally:
        try:
            inst.deactivate()
        except Exception:
            pass

    return {"ok": True, "message": "OK", "how": how, "audio_in": len(audio_in), "audio_out": len(audio_out)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", required=True)
    ap.add_argument("--sr", type=int, default=48000)
    ap.add_argument("--frames", type=int, default=64)
    args = ap.parse_args(argv)

    res = probe(args.uri, sr=int(args.sr), frames=int(args.frames))
    sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
    return 0 if bool(res.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())