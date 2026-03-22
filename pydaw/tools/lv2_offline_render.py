# -*- coding: utf-8 -*-
"""LV2 offline render helper (subprocess).

Goal
----
Render an audio file through a LV2 plugin in a *separate process*.

Why?
----
Some native LV2 plugins can crash (SIGSEGV/SIGBUS) during instantiate() or run().
Python cannot catch that. By rendering in a subprocess we keep the DAW stable.

Implementation notes
-------------------
- We intentionally run with PYDAW_LV2_UNSAFE=1 inside the subprocess so that
  pydaw.audio.lv2_host will skip its Safe-Mode probe gate. If the plugin is
  broken it may crash this subprocess, but the host UI remains alive.
- The heavy lifting is delegated to pydaw.audio.lv2_host.offline_process_wav.

The program prints a single JSON object to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", required=True)
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    ap.add_argument("--controls-json", default="")
    ap.add_argument("--block", type=int, default=1024)
    ns = ap.parse_args(argv)

    # Ensure the subprocess does not block unsafe plugins (this subprocess can crash safely).
    os.environ.setdefault("PYDAW_LV2_UNSAFE", "1")

    controls = None
    try:
        if ns.controls_json:
            data = json.loads(ns.controls_json)
            if isinstance(data, dict):
                controls = {str(k): float(v) for k, v in data.items() if isinstance(v, (int, float))}
    except Exception:
        controls = None

    try:
        from pydaw.audio.lv2_host import offline_process_wav
        ok, msg = offline_process_wav(uri=str(ns.uri), in_path=str(ns.in_path), out_path=str(ns.out_path), controls=controls, block=int(ns.block))
        out = {"ok": bool(ok), "message": str(msg or "")}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.flush()
        return 0 if ok else 2
    except Exception as e:
        out = {"ok": False, "message": f"offline render failed: {type(e).__name__}: {e}"}
        try:
            sys.stdout.write(json.dumps(out, ensure_ascii=False))
            sys.stdout.flush()
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
