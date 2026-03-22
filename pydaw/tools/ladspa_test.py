#!/usr/bin/env python3
"""Quick LADSPA diagnostic tool.

Usage:
    python3 -m pydaw.tools.ladspa_test /usr/lib/ladspa/am_pitchshift_1433.so
    python3 -m pydaw.tools.ladspa_test  # tests first 5 .so files found
"""
import sys
import os
import glob


def test_plugin(path: str) -> None:
    print(f"\n{'='*60}")
    print(f"Testing: {path}")
    print(f"{'='*60}")

    # Step 1: Can we load the .so?
    import ctypes
    try:
        lib = ctypes.CDLL(path)
        print(f"  ✅ ctypes.CDLL loaded OK")
    except Exception as e:
        print(f"  ❌ ctypes.CDLL FAILED: {e}")
        return

    # Step 2: Does it export ladspa_descriptor?
    try:
        func = lib.ladspa_descriptor
        print(f"  ✅ ladspa_descriptor symbol found")
    except Exception as e:
        print(f"  ❌ ladspa_descriptor NOT FOUND: {e}")
        return

    # Step 3: Can we call it?
    try:
        from pydaw.audio.ladspa_host import LADSPA_Descriptor, _get_descriptor
        desc_ptr = _get_descriptor(lib, 0)
        if desc_ptr is None:
            print(f"  ❌ ladspa_descriptor(0) returned NULL")
            return
        print(f"  ✅ ladspa_descriptor(0) returned valid pointer")
    except Exception as e:
        print(f"  ❌ ladspa_descriptor(0) CRASHED: {e}")
        return

    # Step 4: Can we read the struct?
    try:
        desc = desc_ptr.contents
        uid = int(desc.UniqueID)
        label = (desc.Label or b"").decode("utf-8", errors="replace")
        name = (desc.Name or b"").decode("utf-8", errors="replace")
        nports = int(desc.PortCount)
        props = int(desc.Properties)
        print(f"  ✅ Struct OK: ID={uid} Label='{label}' Name='{name}' Ports={nports} Props={props}")
    except Exception as e:
        print(f"  ❌ Struct read FAILED: {e}")
        return

    # Step 5: Can we read ports?
    try:
        from pydaw.audio.ladspa_host import (
            LADSPA_PORT_AUDIO, LADSPA_PORT_CONTROL,
            LADSPA_PORT_INPUT, LADSPA_PORT_OUTPUT
        )
        for i in range(nports):
            pd = int(desc.PortDescriptors[i])
            pname = ""
            try:
                raw = desc.PortNames[i]
                pname = raw.decode("utf-8", errors="replace") if raw else f"port_{i}"
            except Exception:
                pname = f"port_{i}"

            flags = []
            if pd & LADSPA_PORT_AUDIO:
                flags.append("AUDIO")
            if pd & LADSPA_PORT_CONTROL:
                flags.append("CONTROL")
            if pd & LADSPA_PORT_INPUT:
                flags.append("INPUT")
            if pd & LADSPA_PORT_OUTPUT:
                flags.append("OUTPUT")

            hint = 0
            lo = 0.0
            hi = 1.0
            try:
                h = desc.PortRangeHints[i]
                hint = int(h.HintDescriptor)
                lo = float(h.LowerBound)
                hi = float(h.UpperBound)
            except Exception:
                pass

            print(f"    Port {i}: '{pname}' [{' | '.join(flags)}] hint={hint:#x} range=[{lo}, {hi}]")
    except Exception as e:
        print(f"  ❌ Port read FAILED: {e}")
        return

    # Step 6: Full describe_plugin test
    try:
        from pydaw.audio.ladspa_host import describe_plugin
        info = describe_plugin(path, 0)
        if info is None:
            print(f"  ❌ describe_plugin returned None")
        else:
            n_ain = sum(1 for p in info.ports if p.is_audio and p.is_input)
            n_aout = sum(1 for p in info.ports if p.is_audio and p.is_output)
            n_cin = sum(1 for p in info.ports if p.is_control and p.is_input)
            print(f"  ✅ describe_plugin OK: ain={n_ain} aout={n_aout} ctl_in={n_cin}")
    except Exception as e:
        print(f"  ❌ describe_plugin FAILED: {e}")

    print()


def main():
    if len(sys.argv) > 1:
        for path in sys.argv[1:]:
            test_plugin(path)
    else:
        # Auto-find some LADSPA plugins
        paths = sorted(glob.glob("/usr/lib/ladspa/*.so"))[:5]
        if not paths:
            paths = sorted(glob.glob("/usr/local/lib/ladspa/*.so"))[:5]
        if not paths:
            print("No LADSPA .so files found in /usr/lib/ladspa/ or /usr/local/lib/ladspa/")
            return
        print(f"Found {len(paths)} LADSPA .so files, testing first 5:")
        for p in paths:
            test_plugin(p)


if __name__ == "__main__":
    main()
