# -*- coding: utf-8 -*-
"""Plugin Workers — Subprocess-based plugin hosting.

v0.0.20.705 — Phase P2

Each plugin format has its own worker module that runs in a
separate subprocess for crash isolation (Bitwig-style sandboxing).

Workers communicate with the main process via:
    - SharedAudioBuffer (mmap, lock-free) for audio data
    - Unix Domain Socket + MessagePack for commands/events
"""
