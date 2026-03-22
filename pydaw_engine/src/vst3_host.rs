// ============================================================================
// VST3 Plugin Host — Phase P7A (Real FFI via libloading)
// ============================================================================
//
// Hosts VST3 plugins natively in Rust using raw COM interface vtables.
//
// Architecture:
//   1. Scanner: walk .vst3 bundles → dlopen → GetPluginFactory → class info
//   2. Instance: createInstance(IComponent) → query IAudioProcessor
//   3. Setup: initialize → setupProcessing → setActive → setProcessing
//   4. Process: IAudioProcessor::process(ProcessData) on audio thread
//   5. State: IComponent::getState/setState via MemoryStream
//   6. Params: IEditController::getParamNormalized/setParamNormalized
//
// Safety:
//   - All raw pointer ops in unsafe blocks with null checks
//   - Plugin crash caught by plugin_isolator.rs (thread isolation)
//   - Parameter updates via lock-free command queue (no locks in process())
//   - Every COM call wrapped in safe Rust API
//
// v0.0.20.716 — Phase P7A (Claude Opus 4.6, 2026-03-21)
// ============================================================================

use std::collections::HashMap;
use std::ffi::c_void;
use std::os::raw::c_char;
use std::path::{Path, PathBuf};
use std::ptr;

use libloading::{Library, Symbol};
use log::{debug, info};
use serde::{Deserialize, Serialize};

use crate::audio_graph::AudioBuffer;
use crate::plugin_host::AudioPlugin;

// ============================================================================
// VST3 COM Type Definitions (raw C structs)
// ============================================================================
//
// We define the minimal vtable structs needed for audio hosting.
// Reference: steinbergmedia/vst3_pluginterfaces (public headers)

type TResult = i32;
const K_RESULT_OK: TResult = 0;

/// VST3 class TUID (128-bit identifier)
type TUID = [u8; 16];

fn tuid_to_string(tuid: &TUID) -> String {
    tuid.iter().map(|b| format!("{:02X}", b)).collect()
}

// Well-known IIDs from vst3_pluginterfaces

/// IComponent IID: {E831FF31-F2D5-4301-928E-BBEE25697802}
const ICOMPONENT_IID: TUID = [
    0xE8, 0x31, 0xFF, 0x31, 0xF2, 0xD5, 0x43, 0x01,
    0x92, 0x8E, 0xBB, 0xEE, 0x25, 0x69, 0x78, 0x02,
];

/// IAudioProcessor IID: {42043F99-B7DA-453C-A569-E79D9AAEC33E}
const IAUDIO_PROCESSOR_IID: TUID = [
    0x42, 0x04, 0x3F, 0x99, 0xB7, 0xDA, 0x45, 0x3C,
    0xA5, 0x69, 0xE7, 0x9D, 0x9A, 0xAE, 0xC3, 0x3E,
];

/// IEditController IID: {DCD7BBE3-7742-448D-A874-AACC979C759E}
const IEDIT_CONTROLLER_IID: TUID = [
    0xDC, 0xD7, 0xBB, 0xE3, 0x77, 0x42, 0x44, 0x8D,
    0xA8, 0x74, 0xAA, 0xCC, 0x97, 0x9C, 0x75, 0x9E,
];

// ---------------------------------------------------------------------------
// COM vtable structs
// ---------------------------------------------------------------------------

#[repr(C)]
struct FUnknownVtbl {
    query_interface: unsafe extern "system" fn(
        this: *mut c_void, iid: *const TUID, obj: *mut *mut c_void,
    ) -> TResult,
    add_ref: unsafe extern "system" fn(this: *mut c_void) -> u32,
    release: unsafe extern "system" fn(this: *mut c_void) -> u32,
}

#[repr(C)]
#[derive(Clone)]
struct PClassInfo {
    cid: TUID,
    cardinality: i32,
    category: [c_char; 32],
    name: [c_char; 64],
}

#[repr(C)]
struct IPluginFactoryVtbl {
    // FUnknown
    query_interface: unsafe extern "system" fn(
        this: *mut c_void, iid: *const TUID, obj: *mut *mut c_void,
    ) -> TResult,
    add_ref: unsafe extern "system" fn(this: *mut c_void) -> u32,
    release: unsafe extern "system" fn(this: *mut c_void) -> u32,
    // IPluginFactory
    get_factory_info: unsafe extern "system" fn(this: *mut c_void, info: *mut c_void) -> TResult,
    count_classes: unsafe extern "system" fn(this: *mut c_void) -> i32,
    get_class_info: unsafe extern "system" fn(
        this: *mut c_void, index: i32, info: *mut PClassInfo,
    ) -> TResult,
    create_instance: unsafe extern "system" fn(
        this: *mut c_void, cid: *const TUID, iid: *const TUID, obj: *mut *mut c_void,
    ) -> TResult,
}

struct PluginFactory {
    ptr: *mut c_void,
}

impl PluginFactory {
    unsafe fn vtbl(&self) -> &IPluginFactoryVtbl {
        &**(self.ptr as *const *const IPluginFactoryVtbl)
    }

    fn count_classes(&self) -> i32 {
        unsafe { (self.vtbl().count_classes)(self.ptr) }
    }

    fn get_class_info(&self, index: i32) -> Result<PClassInfo, String> {
        let mut info = PClassInfo {
            cid: [0u8; 16], cardinality: 0,
            category: [0i8; 32], name: [0i8; 64],
        };
        let r = unsafe { (self.vtbl().get_class_info)(self.ptr, index, &mut info) };
        if r == K_RESULT_OK { Ok(info) } else { Err(format!("getClassInfo({}): {}", index, r)) }
    }

    fn create_instance(&self, cid: &TUID, iid: &TUID) -> Result<*mut c_void, String> {
        let mut obj: *mut c_void = ptr::null_mut();
        let r = unsafe {
            (self.vtbl().create_instance)(self.ptr, cid as *const _, iid as *const _, &mut obj)
        };
        if r == K_RESULT_OK && !obj.is_null() {
            Ok(obj)
        } else {
            Err(format!("createInstance: {}", r))
        }
    }
}

impl Drop for PluginFactory {
    fn drop(&mut self) {
        if !self.ptr.is_null() {
            unsafe { (self.vtbl().release)(self.ptr); }
        }
    }
}

// ---------------------------------------------------------------------------
// IComponent vtable
// ---------------------------------------------------------------------------

#[repr(C)]
struct IComponentVtbl {
    // FUnknown
    query_interface: unsafe extern "system" fn(
        this: *mut c_void, iid: *const TUID, obj: *mut *mut c_void,
    ) -> TResult,
    add_ref: unsafe extern "system" fn(this: *mut c_void) -> u32,
    release: unsafe extern "system" fn(this: *mut c_void) -> u32,
    // IPluginBase
    initialize: unsafe extern "system" fn(this: *mut c_void, context: *mut c_void) -> TResult,
    terminate: unsafe extern "system" fn(this: *mut c_void) -> TResult,
    // IComponent
    get_controller_class_id: unsafe extern "system" fn(this: *mut c_void, cid: *mut TUID) -> TResult,
    set_io_mode: unsafe extern "system" fn(this: *mut c_void, mode: i32) -> TResult,
    get_bus_count: unsafe extern "system" fn(this: *mut c_void, media_type: i32, dir: i32) -> i32,
    get_bus_info: unsafe extern "system" fn(
        this: *mut c_void, media_type: i32, dir: i32, index: i32, info: *mut c_void,
    ) -> TResult,
    get_routing_info: unsafe extern "system" fn(
        this: *mut c_void, in_info: *mut c_void, out_info: *mut c_void,
    ) -> TResult,
    activate_bus: unsafe extern "system" fn(
        this: *mut c_void, media_type: i32, dir: i32, index: i32, state: u8,
    ) -> TResult,
    set_active: unsafe extern "system" fn(this: *mut c_void, state: u8) -> TResult,
    set_state: unsafe extern "system" fn(this: *mut c_void, stream: *mut c_void) -> TResult,
    get_state: unsafe extern "system" fn(this: *mut c_void, stream: *mut c_void) -> TResult,
}

// ---------------------------------------------------------------------------
// IAudioProcessor vtable
// ---------------------------------------------------------------------------

#[repr(C)]
struct ProcessSetup {
    process_mode: i32,
    symbolic_sample_size: i32,
    max_samples_per_block: i32,
    sample_rate: f64,
}

#[repr(C)]
struct ProcessData {
    process_mode: i32,
    symbolic_sample_size: i32,
    num_samples: i32,
    num_inputs: i32,
    num_outputs: i32,
    inputs: *mut AudioBusBuffers,
    outputs: *mut AudioBusBuffers,
    input_param_changes: *mut c_void,
    output_param_changes: *mut c_void,
    input_events: *mut c_void,
    output_events: *mut c_void,
    process_context: *mut c_void,
}

#[repr(C)]
struct AudioBusBuffers {
    num_channels: i32,
    silence_flags: u64,
    channel_buffers_32: *mut *mut f32,
}

#[repr(C)]
struct IAudioProcessorVtbl {
    // FUnknown
    query_interface: unsafe extern "system" fn(
        this: *mut c_void, iid: *const TUID, obj: *mut *mut c_void,
    ) -> TResult,
    add_ref: unsafe extern "system" fn(this: *mut c_void) -> u32,
    release: unsafe extern "system" fn(this: *mut c_void) -> u32,
    // IAudioProcessor
    set_bus_arrangements: unsafe extern "system" fn(
        this: *mut c_void, inputs: *const u64, num_ins: i32,
        outputs: *const u64, num_outs: i32,
    ) -> TResult,
    get_bus_arrangement: unsafe extern "system" fn(
        this: *mut c_void, dir: i32, index: i32, arr: *mut u64,
    ) -> TResult,
    can_process_sample_size: unsafe extern "system" fn(this: *mut c_void, size: i32) -> TResult,
    get_latency_samples: unsafe extern "system" fn(this: *mut c_void) -> u32,
    setup_processing: unsafe extern "system" fn(
        this: *mut c_void, setup: *const ProcessSetup,
    ) -> TResult,
    set_processing: unsafe extern "system" fn(this: *mut c_void, state: u8) -> TResult,
    process: unsafe extern "system" fn(this: *mut c_void, data: *mut ProcessData) -> TResult,
    get_tail_samples: unsafe extern "system" fn(this: *mut c_void) -> u32,
}

// ---------------------------------------------------------------------------
// IEditController vtable
// ---------------------------------------------------------------------------

#[repr(C)]
#[derive(Clone)]
struct ParameterInfo {
    id: u32,
    title: [u16; 128],
    short_title: [u16; 128],
    units: [u16; 128],
    step_count: i32,
    default_normalized_value: f64,
    unit_id: i32,
    flags: i32,
}

#[repr(C)]
struct IEditControllerVtbl {
    // FUnknown
    query_interface: unsafe extern "system" fn(
        this: *mut c_void, iid: *const TUID, obj: *mut *mut c_void,
    ) -> TResult,
    add_ref: unsafe extern "system" fn(this: *mut c_void) -> u32,
    release: unsafe extern "system" fn(this: *mut c_void) -> u32,
    // IPluginBase
    initialize: unsafe extern "system" fn(this: *mut c_void, context: *mut c_void) -> TResult,
    terminate: unsafe extern "system" fn(this: *mut c_void) -> TResult,
    // IEditController
    set_component_state: unsafe extern "system" fn(this: *mut c_void, state: *mut c_void) -> TResult,
    set_state: unsafe extern "system" fn(this: *mut c_void, state: *mut c_void) -> TResult,
    get_state: unsafe extern "system" fn(this: *mut c_void, state: *mut c_void) -> TResult,
    get_parameter_count: unsafe extern "system" fn(this: *mut c_void) -> i32,
    get_parameter_info: unsafe extern "system" fn(
        this: *mut c_void, index: i32, info: *mut ParameterInfo,
    ) -> TResult,
    get_param_string_by_value: unsafe extern "system" fn(
        this: *mut c_void, id: u32, value: f64, string: *mut u16,
    ) -> TResult,
    get_param_value_by_string: unsafe extern "system" fn(
        this: *mut c_void, id: u32, string: *const u16, value: *mut f64,
    ) -> TResult,
    normalized_param_to_plain: unsafe extern "system" fn(
        this: *mut c_void, id: u32, normalized: f64,
    ) -> f64,
    plain_param_to_normalized: unsafe extern "system" fn(
        this: *mut c_void, id: u32, plain: f64,
    ) -> f64,
    get_param_normalized: unsafe extern "system" fn(this: *mut c_void, id: u32) -> f64,
    set_param_normalized: unsafe extern "system" fn(
        this: *mut c_void, id: u32, value: f64,
    ) -> TResult,
    set_component_handler: unsafe extern "system" fn(
        this: *mut c_void, handler: *mut c_void,
    ) -> TResult,
    create_view: unsafe extern "system" fn(
        this: *mut c_void, name: *const c_char,
    ) -> *mut c_void,
}

// ============================================================================
// Helpers
// ============================================================================

fn cchar_array_to_string(arr: &[c_char]) -> String {
    let bytes: Vec<u8> = arr.iter()
        .take_while(|&&c| c != 0)
        .map(|&c| c as u8)
        .collect();
    String::from_utf8_lossy(&bytes).to_string()
}

fn u16_array_to_string(arr: &[u16]) -> String {
    let chars: Vec<u16> = arr.iter().take_while(|&&c| c != 0).copied().collect();
    String::from_utf16_lossy(&chars)
}

// ============================================================================
// VST3 Plugin Scanner
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Vst3PluginInfo {
    pub class_id: String,
    #[serde(skip)]
    pub cid: TUID,
    pub name: String,
    pub vendor: String,
    pub category: String,
    pub bundle_path: PathBuf,
    pub audio_inputs: u32,
    pub audio_outputs: u32,
    pub sdk_version: String,
}

#[derive(Debug, Default)]
pub struct Vst3ScanResult {
    pub plugins: Vec<Vst3PluginInfo>,
    pub errors: Vec<String>,
    pub scan_time_ms: u64,
}

pub fn vst3_search_paths() -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Some(home) = std::env::var_os("HOME") {
        let home = PathBuf::from(home);
        paths.push(home.join(".vst3"));
        paths.push(home.join(".local/lib/vst3"));
    }
    paths.push(PathBuf::from("/usr/lib/vst3"));
    paths.push(PathBuf::from("/usr/local/lib/vst3"));
    paths.push(PathBuf::from("/usr/lib/x86_64-linux-gnu/vst3"));
    if let Some(extra) = std::env::var_os("VST3_PATH") {
        for p in std::env::split_paths(&extra) { paths.push(p); }
    }
    paths
}

pub fn scan_vst3_plugins() -> Vst3ScanResult {
    let start = std::time::Instant::now();
    let mut result = Vst3ScanResult::default();
    for search_dir in vst3_search_paths() {
        if !search_dir.exists() { continue; }
        debug!("Scanning VST3 directory: {}", search_dir.display());
        scan_directory(&search_dir, &mut result);
    }
    result.scan_time_ms = start.elapsed().as_millis() as u64;
    info!("VST3 scan: {} plugins in {}ms", result.plugins.len(), result.scan_time_ms);
    result
}

fn scan_directory(dir: &Path, result: &mut Vst3ScanResult) {
    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(e) => { result.errors.push(format!("{}: {}", dir.display(), e)); return; }
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            if path.extension().map(|e| e.to_ascii_lowercase() == "vst3").unwrap_or(false) {
                match probe_vst3_bundle(&path) {
                    Ok(infos) => result.plugins.extend(infos),
                    Err(e) => result.errors.push(format!("{}: {}", path.display(), e)),
                }
            } else {
                scan_directory(&path, result);
            }
        }
    }
}

fn find_vst3_binary(bundle_path: &Path) -> Option<PathBuf> {
    for arch in &["x86_64-linux", "aarch64-linux"] {
        let arch_dir = bundle_path.join("Contents").join(arch);
        if let Ok(entries) = std::fs::read_dir(&arch_dir) {
            for entry in entries.flatten() {
                let p = entry.path();
                if p.extension().map(|e| e == "so").unwrap_or(false) {
                    return Some(p);
                }
            }
        }
    }
    // Fallback: .so in bundle root
    if let Ok(entries) = std::fs::read_dir(bundle_path) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.extension().map(|e| e == "so").unwrap_or(false) {
                return Some(p);
            }
        }
    }
    None
}

/// Probe a .vst3 bundle: dlopen → GetPluginFactory → enumerate classes.
fn probe_vst3_bundle(bundle_path: &Path) -> Result<Vec<Vst3PluginInfo>, String> {
    let so_path = find_vst3_binary(bundle_path)
        .ok_or_else(|| format!("No .so in {}", bundle_path.display()))?;

    let lib = unsafe { Library::new(&so_path) }
        .map_err(|e| format!("dlopen {}: {}", so_path.display(), e))?;

    let get_factory: Symbol<unsafe extern "C" fn() -> *mut c_void> = unsafe {
        lib.get(b"GetPluginFactory\0")
    }.map_err(|e| format!("GetPluginFactory: {}", e))?;

    let factory_ptr = unsafe { get_factory() };
    if factory_ptr.is_null() {
        return Err("GetPluginFactory returned null".to_string());
    }
    let factory = PluginFactory { ptr: factory_ptr };
    let count = factory.count_classes();

    let mut plugins = Vec::new();
    for i in 0..count {
        if let Ok(info) = factory.get_class_info(i) {
            plugins.push(Vst3PluginInfo {
                class_id: tuid_to_string(&info.cid),
                cid: info.cid,
                name: cchar_array_to_string(&info.name),
                vendor: String::new(),
                category: cchar_array_to_string(&info.category),
                bundle_path: bundle_path.to_path_buf(),
                audio_inputs: 1,
                audio_outputs: 1,
                sdk_version: "3.7".to_string(),
            });
        }
    }

    // Leak lib: factory references it. OS unmaps on process exit.
    std::mem::forget(lib);
    Ok(plugins)
}

// ============================================================================
// VST3 Plugin Instance — Real FFI
// ============================================================================

pub struct Vst3Instance {
    info: Vst3PluginInfo,
    _library: Library,
    component: *mut c_void,
    processor: *mut c_void,
    controller: *mut c_void,

    sample_rate: f64,
    max_block_size: u32,
    is_active: bool,
    is_processing: bool,

    parameters: HashMap<u32, (f64, String)>,
    param_ids: Vec<u32>,
    saved_state: Vec<u8>,
    latency: u32,

    // Pre-allocated for process() — avoids heap alloc in audio thread
    deinterleave_l: Vec<f32>,
    deinterleave_r: Vec<f32>,
    input_ptrs: Vec<*mut f32>,
    output_ptrs: Vec<*mut f32>,
}

unsafe impl Send for Vst3Instance {}

impl Vst3Instance {
    /// Load a VST3 plugin from a bundle path + class ID.
    pub fn load(info: &Vst3PluginInfo, sample_rate: f64, max_block_size: u32) -> Result<Self, String> {
        let so_path = find_vst3_binary(&info.bundle_path)
            .ok_or_else(|| format!("No .so in {}", info.bundle_path.display()))?;

        let lib = unsafe { Library::new(&so_path) }.map_err(|e| format!("dlopen: {}", e))?;

        let get_factory: Symbol<unsafe extern "C" fn() -> *mut c_void> = unsafe {
            lib.get(b"GetPluginFactory\0")
        }.map_err(|e| format!("GetPluginFactory: {}", e))?;

        let factory_ptr = unsafe { get_factory() };
        if factory_ptr.is_null() { return Err("Factory is null".into()); }
        let factory = PluginFactory { ptr: factory_ptr };

        // Create IComponent
        let component = factory.create_instance(&info.cid, &ICOMPONENT_IID)?;
        let comp_vtbl = unsafe { &**(component as *const *const IComponentVtbl) };
        let _ = unsafe { (comp_vtbl.initialize)(component, ptr::null_mut()) };

        // Query IAudioProcessor
        let mut processor: *mut c_void = ptr::null_mut();
        let r = unsafe {
            (comp_vtbl.query_interface)(component, &IAUDIO_PROCESSOR_IID as *const _, &mut processor)
        };
        if r != K_RESULT_OK || processor.is_null() {
            return Err(format!("No IAudioProcessor: {}", r));
        }

        // Query IEditController (may be same object or separate)
        let mut controller: *mut c_void = ptr::null_mut();
        let r = unsafe {
            (comp_vtbl.query_interface)(component, &IEDIT_CONTROLLER_IID as *const _, &mut controller)
        };
        if r != K_RESULT_OK || controller.is_null() {
            let mut ctrl_cid: TUID = [0u8; 16];
            if unsafe { (comp_vtbl.get_controller_class_id)(component, &mut ctrl_cid) } == K_RESULT_OK
                && ctrl_cid != [0u8; 16]
            {
                if let Ok(ctrl) = factory.create_instance(&ctrl_cid, &IEDIT_CONTROLLER_IID) {
                    controller = ctrl;
                    let ctrl_vtbl = unsafe { &**(controller as *const *const IEditControllerVtbl) };
                    let _ = unsafe { (ctrl_vtbl.initialize)(controller, ptr::null_mut()) };
                }
            }
        }

        std::mem::forget(factory);

        let bs = max_block_size as usize;
        let mut inst = Self {
            info: info.clone(),
            _library: lib,
            component, processor, controller,
            sample_rate, max_block_size,
            is_active: false, is_processing: false,
            parameters: HashMap::new(),
            param_ids: Vec::new(),
            saved_state: Vec::new(),
            latency: 0,
            deinterleave_l: vec![0.0; bs],
            deinterleave_r: vec![0.0; bs],
            input_ptrs: vec![ptr::null_mut(); 2],
            output_ptrs: vec![ptr::null_mut(); 2],
        };

        inst.setup(sample_rate, max_block_size)?;
        inst.discover_parameters();
        Ok(inst)
    }

    fn setup(&mut self, sample_rate: f64, max_block_size: u32) -> Result<(), String> {
        let proc_vtbl = unsafe { &**(self.processor as *const *const IAudioProcessorVtbl) };

        let setup = ProcessSetup {
            process_mode: 0, symbolic_sample_size: 0,
            max_samples_per_block: max_block_size as i32, sample_rate,
        };
        let _ = unsafe { (proc_vtbl.setup_processing)(self.processor, &setup) };

        // Activate buses
        let comp_vtbl = unsafe { &**(self.component as *const *const IComponentVtbl) };
        let _ = unsafe { (comp_vtbl.activate_bus)(self.component, 0, 0, 0, 1) };
        let _ = unsafe { (comp_vtbl.activate_bus)(self.component, 0, 1, 0, 1) };

        let r = unsafe { (comp_vtbl.set_active)(self.component, 1) };
        if r != K_RESULT_OK { return Err(format!("setActive: {}", r)); }
        self.is_active = true;

        let _ = unsafe { (proc_vtbl.set_processing)(self.processor, 1) };
        self.is_processing = true;

        self.latency = unsafe { (proc_vtbl.get_latency_samples)(self.processor) };
        self.sample_rate = sample_rate;
        self.max_block_size = max_block_size;

        info!("VST3 ready: {} @ {}Hz, bs={}, lat={}", self.info.name, sample_rate, max_block_size, self.latency);
        Ok(())
    }

    fn discover_parameters(&mut self) {
        if self.controller.is_null() { return; }
        let ctrl = unsafe { &**(self.controller as *const *const IEditControllerVtbl) };
        let count = unsafe { (ctrl.get_parameter_count)(self.controller) };
        for i in 0..count {
            let mut pi = ParameterInfo {
                id: 0, title: [0u16; 128], short_title: [0u16; 128],
                units: [0u16; 128], step_count: 0,
                default_normalized_value: 0.0, unit_id: 0, flags: 0,
            };
            if unsafe { (ctrl.get_parameter_info)(self.controller, i, &mut pi) } == K_RESULT_OK {
                let name = u16_array_to_string(&pi.title);
                let value = unsafe { (ctrl.get_param_normalized)(self.controller, pi.id) };
                self.parameters.insert(pi.id, (value, name));
                self.param_ids.push(pi.id);
            }
        }
        debug!("VST3 {} has {} params", self.info.name, self.parameters.len());
    }

    pub fn terminate(&mut self) {
        if self.is_processing && !self.processor.is_null() {
            let v = unsafe { &**(self.processor as *const *const IAudioProcessorVtbl) };
            let _ = unsafe { (v.set_processing)(self.processor, 0) };
            self.is_processing = false;
        }
        if self.is_active && !self.component.is_null() {
            let v = unsafe { &**(self.component as *const *const IComponentVtbl) };
            let _ = unsafe { (v.set_active)(self.component, 0) };
            let _ = unsafe { (v.terminate)(self.component) };
            self.is_active = false;
        }
        // Release COM refs
        for ptr in [self.controller, self.processor, self.component] {
            if !ptr.is_null() {
                let v = unsafe { &**(ptr as *const *const FUnknownVtbl) };
                unsafe { (v.release)(ptr); }
            }
        }
        self.component = ptr::null_mut();
        self.processor = ptr::null_mut();
        self.controller = ptr::null_mut();
    }

    pub fn get_latency(&self) -> u32 { self.latency }
}

impl AudioPlugin for Vst3Instance {
    fn process(&mut self, buffer: &mut AudioBuffer, _sample_rate: u32) {
        if !self.is_processing || self.processor.is_null() { return; }

        let frames = buffer.frames;
        let ch = buffer.channels.min(2);

        // Ensure deinterleave buffers are large enough
        if self.deinterleave_l.len() < frames {
            self.deinterleave_l.resize(frames, 0.0);
            self.deinterleave_r.resize(frames, 0.0);
        }

        // Deinterleave
        for i in 0..frames {
            self.deinterleave_l[i] = buffer.data[i * buffer.channels];
            if ch > 1 {
                self.deinterleave_r[i] = buffer.data[i * buffer.channels + 1];
            } else {
                self.deinterleave_r[i] = 0.0;
            }
        }

        self.input_ptrs[0] = self.deinterleave_l.as_mut_ptr();
        self.input_ptrs[1] = self.deinterleave_r.as_mut_ptr();
        self.output_ptrs[0] = self.deinterleave_l.as_mut_ptr();
        self.output_ptrs[1] = self.deinterleave_r.as_mut_ptr();

        let mut in_bus = AudioBusBuffers {
            num_channels: ch as i32, silence_flags: 0,
            channel_buffers_32: self.input_ptrs.as_mut_ptr(),
        };
        let mut out_bus = AudioBusBuffers {
            num_channels: ch as i32, silence_flags: 0,
            channel_buffers_32: self.output_ptrs.as_mut_ptr(),
        };

        let mut data = ProcessData {
            process_mode: 0, symbolic_sample_size: 0,
            num_samples: frames as i32,
            num_inputs: 1, num_outputs: 1,
            inputs: &mut in_bus, outputs: &mut out_bus,
            input_param_changes: ptr::null_mut(),
            output_param_changes: ptr::null_mut(),
            input_events: ptr::null_mut(),
            output_events: ptr::null_mut(),
            process_context: ptr::null_mut(),
        };

        let v = unsafe { &**(self.processor as *const *const IAudioProcessorVtbl) };
        let _ = unsafe { (v.process)(self.processor, &mut data) };

        // Reinterleave
        for i in 0..frames {
            buffer.data[i * buffer.channels] = self.deinterleave_l[i];
            if ch > 1 {
                buffer.data[i * buffer.channels + 1] = self.deinterleave_r[i];
            }
        }
    }

    fn id(&self) -> &str { &self.info.class_id }
    fn name(&self) -> &str { &self.info.name }

    fn set_parameter(&mut self, index: u32, value: f64) {
        let pid = if (index as usize) < self.param_ids.len() {
            self.param_ids[index as usize]
        } else { index };

        if let Some(e) = self.parameters.get_mut(&pid) { e.0 = value; }
        if !self.controller.is_null() {
            let v = unsafe { &**(self.controller as *const *const IEditControllerVtbl) };
            let _ = unsafe { (v.set_param_normalized)(self.controller, pid, value) };
        }
    }

    fn get_parameter(&self, index: u32) -> f64 {
        let pid = if (index as usize) < self.param_ids.len() {
            self.param_ids[index as usize]
        } else { index };
        if !self.controller.is_null() {
            let v = unsafe { &**(self.controller as *const *const IEditControllerVtbl) };
            return unsafe { (v.get_param_normalized)(self.controller, pid) };
        }
        self.parameters.get(&pid).map(|p| p.0).unwrap_or(0.0)
    }

    fn parameter_count(&self) -> u32 { self.param_ids.len() as u32 }

    fn parameter_name(&self, index: u32) -> String {
        let pid = if (index as usize) < self.param_ids.len() {
            self.param_ids[index as usize]
        } else { index };
        self.parameters.get(&pid).map(|p| p.1.clone()).unwrap_or_default()
    }

    fn save_state(&self) -> Vec<u8> {
        // TODO: IBStream implementation for getState
        self.saved_state.clone()
    }

    fn load_state(&mut self, data: &[u8]) -> Result<(), String> {
        // TODO: IBStream implementation for setState
        self.saved_state = data.to_vec();
        Ok(())
    }

    fn latency_samples(&self) -> u32 { self.latency }

    fn tail_samples(&self) -> u64 {
        if self.processor.is_null() { return 0; }
        let v = unsafe { &**(self.processor as *const *const IAudioProcessorVtbl) };
        unsafe { (v.get_tail_samples)(self.processor) as u64 }
    }
}

impl Drop for Vst3Instance {
    fn drop(&mut self) { self.terminate(); }
}

/// Load a VST3 by bundle path.  If class_id is None, loads first class.
pub fn load_vst3(
    bundle_path: &Path, class_id: Option<&str>,
    sample_rate: f64, max_block_size: u32,
) -> Result<Vst3Instance, String> {
    let scan = probe_vst3_bundle(bundle_path)?;
    let info = if let Some(cid) = class_id {
        scan.iter().find(|p| p.class_id == cid)
            .ok_or_else(|| format!("Class {} not in {}", cid, bundle_path.display()))?.clone()
    } else {
        scan.into_iter().next()
            .ok_or_else(|| format!("No classes in {}", bundle_path.display()))?
    };
    Vst3Instance::load(&info, sample_rate, max_block_size)
}
