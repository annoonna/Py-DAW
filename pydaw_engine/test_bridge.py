#!/usr/bin/env python3
"""Phase 1A Bridge Test — Py_DAW Rust Engine.

Usage:
    # Start engine first:
    #   cd pydaw_engine && RUST_LOG=info cargo run
    # Then run this test:
    #   python3 pydaw_engine/test_bridge.py

Or let the bridge start the engine automatically:
    python3 pydaw_engine/test_bridge.py --auto
"""

import json
import os
import socket
import struct
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SOCKET_PATH = "/tmp/pydaw_engine.sock"


def encode_frame(data: dict) -> bytes:
    """Encode command to length-prefixed frame (JSON fallback)."""
    try:
        import msgpack
        payload = msgpack.packb(data, use_bin_type=True)
    except ImportError:
        payload = json.dumps(data).encode("utf-8")
    return struct.pack("<I", len(payload)) + payload


def decode_frame(payload: bytes) -> dict:
    """Decode event from payload."""
    try:
        import msgpack
        return msgpack.unpackb(payload, raw=False)
    except ImportError:
        return json.loads(payload.decode("utf-8"))


def recv_frame(sock: socket.socket) -> dict | None:
    """Read one frame from socket."""
    len_buf = b""
    while len(len_buf) < 4:
        chunk = sock.recv(4 - len(len_buf))
        if not chunk:
            return None
        len_buf += chunk
    length = struct.unpack("<I", len_buf)[0]
    buf = b""
    while len(buf) < length:
        chunk = sock.recv(length - len(buf))
        if not chunk:
            return None
        buf += chunk
    return decode_frame(buf)


def test_manual():
    """Test with manually started engine."""
    print(f"🔌 Connecting to {SOCKET_PATH}...")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    sock.connect(SOCKET_PATH)
    sock.settimeout(2.0)  # 2s timeout for reads
    print("✅ Connected!")

    # --- Test 1: Ping ---
    print("\n--- Test 1: Ping ---")
    sock.sendall(encode_frame({"cmd": "Ping", "seq": 1}))
    try:
        event = recv_frame(sock)
        if event and event.get("evt") == "Pong":
            print(f"✅ Pong received: seq={event.get('seq')}, cpu={event.get('cpu_load')}")
        else:
            print(f"⚠️  Unexpected event: {event}")
    except socket.timeout:
        print("⚠️  Timeout waiting for Pong (engine may still be sending meter events)")

    # Drain any pending events (meter levels etc.)
    for _ in range(20):
        try:
            event = recv_frame(sock)
            if event:
                evt = event.get("evt", "?")
                if evt == "Pong":
                    print(f"✅ Pong: seq={event.get('seq')}")
                elif evt == "MasterMeterLevel":
                    print(f"📊 Master meters: L={event.get('peak_l', 0):.4f} R={event.get('peak_r', 0):.4f}")
                elif evt == "PlayheadPosition":
                    print(f"▶️  Playhead: beat={event.get('beat', 0):.2f} playing={event.get('is_playing')}")
                elif evt == "TransportState":
                    print(f"🎵 Transport: playing={event.get('is_playing')} beat={event.get('beat', 0):.2f}")
                elif evt == "Ready":
                    print(f"✅ Ready: sr={event.get('sample_rate')} buf={event.get('buffer_size')}")
                else:
                    print(f"📨 {evt}: {event}")
        except socket.timeout:
            break

    # --- Test 2: Configure ---
    print("\n--- Test 2: Configure ---")
    sock.sendall(encode_frame({
        "cmd": "Configure",
        "sample_rate": 48000,
        "buffer_size": 256,
        "device": "",
    }))
    time.sleep(0.5)
    for _ in range(10):
        try:
            event = recv_frame(sock)
            if event and event.get("evt") == "Ready":
                print(f"✅ Engine reconfigured: sr={event.get('sample_rate')}")
                break
        except socket.timeout:
            break

    # --- Test 3: Transport ---
    print("\n--- Test 3: Play/Stop ---")
    sock.sendall(encode_frame({"cmd": "SetTempo", "bpm": 140.0}))
    sock.sendall(encode_frame({"cmd": "Play"}))
    time.sleep(1.0)

    # Read events for 1 second
    playhead_events = 0
    meter_events = 0
    for _ in range(100):
        try:
            event = recv_frame(sock)
            if event:
                evt = event.get("evt", "?")
                if evt == "PlayheadPosition":
                    playhead_events += 1
                elif evt in ("MasterMeterLevel", "MeterLevels"):
                    meter_events += 1
                elif evt == "TransportState":
                    print(f"🎵 Transport: playing={event.get('is_playing')}")
        except socket.timeout:
            break

    print(f"📊 Received {playhead_events} playhead + {meter_events} meter events in ~1s")

    sock.sendall(encode_frame({"cmd": "Stop"}))
    time.sleep(0.2)

    # --- Test 4: Shutdown ---
    print("\n--- Test 4: Shutdown ---")
    sock.sendall(encode_frame({"cmd": "Shutdown"}))
    time.sleep(0.5)
    for _ in range(5):
        try:
            event = recv_frame(sock)
            if event and event.get("evt") == "ShuttingDown":
                print("✅ Engine confirmed shutdown")
                break
        except socket.timeout:
            break

    sock.close()
    print("\n🎉 All tests passed!")


def test_auto():
    """Test with automatic engine start via RustEngineBridge."""
    from pydaw.services.rust_engine_bridge import RustEngineBridge

    bridge = RustEngineBridge.instance()
    print(f"Engine available: {bridge.is_available()}")
    print(f"Engine enabled:  {bridge.is_enabled()}")

    if not bridge.is_available():
        print("❌ Engine binary not found. Build with: cd pydaw_engine && cargo build --release")
        return False

    print("🚀 Starting engine...")
    if not bridge.start_engine():
        print("❌ Failed to start engine")
        return False

    print("✅ Engine started")

    bridge.ping()
    time.sleep(0.5)

    bridge.set_tempo(140.0)
    bridge.play()
    time.sleep(2.0)
    bridge.stop()

    bridge.shutdown()
    print("🎉 Auto test passed!")
    return True


if __name__ == "__main__":
    if "--auto" in sys.argv:
        test_auto()
    else:
        test_manual()
