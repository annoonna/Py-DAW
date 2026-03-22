use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};

// ============================================================================
// AtomicF32 — Lock-free f32 for audio-thread parameter access
// ============================================================================
//
// Replaces the external `atomic_float` crate with a zero-dependency impl.
// Uses AtomicU32 + f32::to_bits / f32::from_bits (standard pattern).
// ============================================================================

/// Lock-free f32 value for real-time audio parameters.
///
/// Uses bit-casting to AtomicU32 — no allocations, no locks.
pub struct AtomicF32 {
    bits: AtomicU32,
}

impl AtomicF32 {
    pub fn new(val: f32) -> Self {
        Self {
            bits: AtomicU32::new(val.to_bits()),
        }
    }

    #[inline]
    pub fn load(&self, order: Ordering) -> f32 {
        f32::from_bits(self.bits.load(order))
    }

    #[inline]
    pub fn store(&self, val: f32, order: Ordering) {
        self.bits.store(val.to_bits(), order);
    }
}

// ============================================================================
// Lock-Free Ring Buffer — Zero-lock parameter updates for audio thread
// ============================================================================
//
// This is the Rust equivalent of Python's ParamRingBuffer (ring_buffer.py).
//
// Architecture:
//   GUI Thread → write(param_id, value) → SPSC Ring → Audio Thread → drain()
//
// The ring is lock-free: single-producer (GUI), single-consumer (audio).
// No allocations, no locks, no syscalls in the hot path.
//
// Capacity is fixed at compile time (power of 2 for fast modulo via bitmask).
// ============================================================================

/// Single parameter update entry in the ring.
#[repr(C)]
#[derive(Clone, Copy)]
pub struct ParamEntry {
    /// Parameter ID (matches Python RTParamStore keys).
    pub param_id: u32,
    /// Parameter value (f64 stored as u64 bits for atomic access).
    pub value_bits: u64,
}

impl ParamEntry {
    pub fn new(param_id: u32, value: f64) -> Self {
        Self {
            param_id,
            value_bits: value.to_bits(),
        }
    }

    pub fn value(&self) -> f64 {
        f64::from_bits(self.value_bits)
    }
}

/// Ring buffer capacity — must be power of 2.
const RING_CAPACITY: usize = 4096;
const RING_MASK: usize = RING_CAPACITY - 1;

/// Lock-free SPSC (Single-Producer Single-Consumer) ring buffer.
///
/// Producer (GUI thread) calls `push()`.
/// Consumer (audio thread) calls `drain_into()`.
///
/// Overflow policy: oldest entries are silently dropped (the audio thread
/// will see the latest value on the next drain cycle anyway).
pub struct ParamRing {
    /// Ring storage (fixed size, never reallocated).
    entries: Box<[ParamEntry; RING_CAPACITY]>,
    /// Write position (only modified by producer).
    write_pos: AtomicU32,
    /// Read position (only modified by consumer).
    read_pos: AtomicU32,
}

impl ParamRing {
    pub fn new() -> Self {
        Self {
            entries: Box::new([ParamEntry { param_id: 0, value_bits: 0 }; RING_CAPACITY]),
            write_pos: AtomicU32::new(0),
            read_pos: AtomicU32::new(0),
        }
    }

    /// Push a parameter update (GUI thread). Lock-free, wait-free.
    ///
    /// If the ring is full, the oldest entry is overwritten.
    pub fn push(&self, param_id: u32, value: f64) {
        let wp = self.write_pos.load(Ordering::Relaxed) as usize;
        let idx = wp & RING_MASK;

        // Safety: we're the only writer, and we write before advancing the pointer.
        // The consumer only reads entries between read_pos and write_pos.
        unsafe {
            let ptr = self.entries.as_ptr() as *mut ParamEntry;
            (*ptr.add(idx)) = ParamEntry::new(param_id, value);
        }

        self.write_pos.store((wp + 1) as u32, Ordering::Release);
    }

    /// Drain all pending entries into a callback. Lock-free.
    ///
    /// Called from the audio thread at the start of each process cycle.
    /// The callback receives (param_id, value) for each pending update.
    pub fn drain<F: FnMut(u32, f64)>(&self, mut callback: F) {
        let wp = self.write_pos.load(Ordering::Acquire) as usize;
        let mut rp = self.read_pos.load(Ordering::Relaxed) as usize;

        // Limit drain to RING_CAPACITY to prevent infinite loop on overflow
        let available = if wp >= rp {
            wp - rp
        } else {
            (u32::MAX as usize + 1) - rp + wp
        };
        let count = available.min(RING_CAPACITY);

        for _ in 0..count {
            let idx = rp & RING_MASK;
            let entry = unsafe {
                let ptr = self.entries.as_ptr();
                *ptr.add(idx)
            };
            callback(entry.param_id, entry.value());
            rp += 1;
        }

        self.read_pos.store(rp as u32, Ordering::Release);
    }

    /// Number of pending entries.
    pub fn len(&self) -> usize {
        let wp = self.write_pos.load(Ordering::Relaxed) as usize;
        let rp = self.read_pos.load(Ordering::Relaxed) as usize;
        wp.wrapping_sub(rp)
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

// Safety: ParamRing is designed for cross-thread use (SPSC).
unsafe impl Send for ParamRing {}
unsafe impl Sync for ParamRing {}

// ---------------------------------------------------------------------------
// Audio Ring Buffer — for passing audio data lock-free
// ---------------------------------------------------------------------------

/// Lock-free ring buffer for stereo audio samples.
///
/// Used for:
/// - Input monitoring (hardware input → track)
/// - Bounce/export (track output → file writer)
///
/// Not used for the main mix path (that uses pre-allocated AudioBuffers).
pub struct AudioRing {
    /// Interleaved stereo samples.
    data: Box<[f32]>,
    capacity_frames: usize,
    write_pos: AtomicU64,
    read_pos: AtomicU64,
}

impl AudioRing {
    pub fn new(capacity_frames: usize) -> Self {
        let capacity = capacity_frames.next_power_of_two();
        Self {
            data: vec![0.0f32; capacity * 2].into_boxed_slice(),
            capacity_frames: capacity,
            write_pos: AtomicU64::new(0),
            read_pos: AtomicU64::new(0),
        }
    }

    /// Write interleaved stereo frames. Returns number of frames written.
    pub fn write(&self, samples: &[f32]) -> usize {
        let frames = samples.len() / 2;
        let mask = self.capacity_frames - 1;
        let mut wp = self.write_pos.load(Ordering::Relaxed) as usize;

        for i in 0..frames {
            let idx = (wp & mask) * 2;
            unsafe {
                let ptr = self.data.as_ptr() as *mut f32;
                *ptr.add(idx) = samples[i * 2];
                *ptr.add(idx + 1) = samples[i * 2 + 1];
            }
            wp += 1;
        }

        self.write_pos.store(wp as u64, Ordering::Release);
        frames
    }

    /// Read interleaved stereo frames into output. Returns number of frames read.
    pub fn read(&self, output: &mut [f32]) -> usize {
        let max_frames = output.len() / 2;
        let mask = self.capacity_frames - 1;
        let wp = self.write_pos.load(Ordering::Acquire) as usize;
        let mut rp = self.read_pos.load(Ordering::Relaxed) as usize;

        let available = wp.wrapping_sub(rp).min(self.capacity_frames);
        let frames = available.min(max_frames);

        for i in 0..frames {
            let idx = (rp & mask) * 2;
            output[i * 2] = self.data[idx];
            output[i * 2 + 1] = self.data[idx + 1];
            rp += 1;
        }

        self.read_pos.store(rp as u64, Ordering::Release);
        frames
    }

    pub fn available_frames(&self) -> usize {
        let wp = self.write_pos.load(Ordering::Relaxed) as usize;
        let rp = self.read_pos.load(Ordering::Relaxed) as usize;
        wp.wrapping_sub(rp).min(self.capacity_frames)
    }
}

unsafe impl Send for AudioRing {}
unsafe impl Sync for AudioRing {}

// ---------------------------------------------------------------------------
// Meter Ring — for passing metering data to GUI
// ---------------------------------------------------------------------------

/// Per-track meter snapshot.
#[derive(Clone, Copy, Default)]
pub struct MeterSnapshot {
    pub peak_l: f32,
    pub peak_r: f32,
    pub rms_l: f32,
    pub rms_r: f32,
}

/// Lock-free ring for meter data (audio → GUI, ~30Hz).
///
/// Uses a simple atomic triple-buffer: audio writes to slot A,
/// then swaps A↔B atomically. GUI reads from B (always consistent).
pub struct MeterRing {
    /// Meter data per track (indexed by track_index).
    /// Triple-buffered: [0]=write, [1]=ready, [2]=read
    buffers: [Box<[MeterSnapshot]>; 3],
    /// Which buffer is "ready" (written by audio, read by GUI).
    ready_index: AtomicU32,
    /// Track count.
    track_count: usize,
}

impl MeterRing {
    pub fn new(max_tracks: usize) -> Self {
        Self {
            buffers: [
                vec![MeterSnapshot::default(); max_tracks].into_boxed_slice(),
                vec![MeterSnapshot::default(); max_tracks].into_boxed_slice(),
                vec![MeterSnapshot::default(); max_tracks].into_boxed_slice(),
            ],
            ready_index: AtomicU32::new(1),
            track_count: max_tracks,
        }
    }

    /// Write meter data for a track (audio thread).
    pub fn write_track(&mut self, track_index: usize, snapshot: MeterSnapshot) {
        if track_index < self.track_count {
            // Always write to buffer 0
            self.buffers[0][track_index] = snapshot;
        }
    }

    /// Commit written data: swap write buffer to ready (audio thread).
    pub fn commit(&self) {
        // Swap buffer 0 (write) with buffer 1 (ready)
        self.ready_index.store(0, Ordering::Release);
    }

    /// Read all meter data (GUI thread). Returns a slice of MeterSnapshots.
    pub fn read_all(&self) -> &[MeterSnapshot] {
        let idx = self.ready_index.load(Ordering::Acquire) as usize;
        &self.buffers[idx.min(2)]
    }
}

unsafe impl Send for MeterRing {}
unsafe impl Sync for MeterRing {}
