// ============================================================================
// CLAP Plugin Host — Phase P7B (Real FFI via libloading)
// ============================================================================
//
// Hosts CLAP plugins natively in Rust using the raw C API structs.
//
// CLAP is a pure C API — no COM, no C++ ABI issues.  Ideal for Rust FFI.
//
// Architecture:
//   1. Scanner: dlopen .clap → dlsym("clap_entry") → get_factory → descriptors
//   2. Instance: factory.create_plugin → init → activate → start_processing
//   3. Process: clap_plugin.process(&clap_process) on audio thread
//   4. State: clap_plugin_state extension (save/load via stream)
//   5. Params: clap_plugin_params extension (count, info, get_value, ...)
//
// v0.0.20.716 — Phase P7B (Claude Opus 4.6, 2026-03-21)
// ============================================================================

use std::collections::HashMap;
use std::ffi::{c_void, CStr, CString};
use std::os::raw::c_char;
use std::path::{Path, PathBuf};
use std::ptr;

use libloading::{Library, Symbol};
use log::{debug, info, warn};
use serde::{Deserialize, Serialize};

use crate::audio_graph::AudioBuffer;
use crate::plugin_host::AudioPlugin;

// ============================================================================
// CLAP C API Type Definitions
// ============================================================================
//
// Reference: https://github.com/free-audio/clap/blob/main/include/clap/

const CLAP_PLUGIN_FACTORY_ID: &[u8] = b"clap.plugin-factory\0";

// ---------------------------------------------------------------------------
// clap_version
// ---------------------------------------------------------------------------

#[repr(C)]
#[derive(Clone, Copy)]
struct ClapVersion {
    major: u32,
    minor: u32,
    revision: u32,
}

const CLAP_VERSION: ClapVersion = ClapVersion { major: 1, minor: 2, revision: 2 };

// ---------------------------------------------------------------------------
// clap_host — provided by us to plugins
// ---------------------------------------------------------------------------

#[repr(C)]
struct ClapHost {
    clap_version: ClapVersion,
    host_data: *mut c_void,
    name: *const c_char,
    vendor: *const c_char,
    url: *const c_char,
    version: *const c_char,
    get_extension: unsafe extern "C" fn(host: *const ClapHost, extension_id: *const c_char) -> *const c_void,
    request_restart: unsafe extern "C" fn(host: *const ClapHost),
    request_process: unsafe extern "C" fn(host: *const ClapHost),
    request_callback: unsafe extern "C" fn(host: *const ClapHost),
}

// Host callback stubs — minimal implementation
unsafe extern "C" fn host_get_extension(_host: *const ClapHost, _id: *const c_char) -> *const c_void {
    ptr::null()
}
unsafe extern "C" fn host_request_restart(_host: *const ClapHost) {}
unsafe extern "C" fn host_request_process(_host: *const ClapHost) {}
unsafe extern "C" fn host_request_callback(_host: *const ClapHost) {}

// ---------------------------------------------------------------------------
// clap_plugin_entry
// ---------------------------------------------------------------------------

#[repr(C)]
struct ClapPluginEntry {
    clap_version: ClapVersion,
    init: unsafe extern "C" fn(plugin_path: *const c_char) -> bool,
    deinit: unsafe extern "C" fn(),
    get_factory: unsafe extern "C" fn(factory_id: *const c_char) -> *const c_void,
}

// ---------------------------------------------------------------------------
// clap_plugin_factory
// ---------------------------------------------------------------------------

#[repr(C)]
struct ClapPluginFactory {
    get_plugin_count: unsafe extern "C" fn(factory: *const ClapPluginFactory) -> u32,
    get_plugin_descriptor: unsafe extern "C" fn(
        factory: *const ClapPluginFactory, index: u32,
    ) -> *const ClapPluginDescriptor,
    create_plugin: unsafe extern "C" fn(
        factory: *const ClapPluginFactory,
        host: *const ClapHost,
        plugin_id: *const c_char,
    ) -> *const ClapPlugin,
}

// ---------------------------------------------------------------------------
// clap_plugin_descriptor
// ---------------------------------------------------------------------------

#[repr(C)]
struct ClapPluginDescriptor {
    clap_version: ClapVersion,
    id: *const c_char,
    name: *const c_char,
    vendor: *const c_char,
    url: *const c_char,
    manual_url: *const c_char,
    support_url: *const c_char,
    version: *const c_char,
    description: *const c_char,
    features: *const *const c_char, // NULL-terminated array
}

// ---------------------------------------------------------------------------
// clap_plugin
// ---------------------------------------------------------------------------

#[repr(C)]
struct ClapPlugin {
    desc: *const ClapPluginDescriptor,
    plugin_data: *mut c_void,
    init: unsafe extern "C" fn(plugin: *const ClapPlugin) -> bool,
    destroy: unsafe extern "C" fn(plugin: *const ClapPlugin),
    activate: unsafe extern "C" fn(
        plugin: *const ClapPlugin, sample_rate: f64,
        min_frames: u32, max_frames: u32,
    ) -> bool,
    deactivate: unsafe extern "C" fn(plugin: *const ClapPlugin),
    start_processing: unsafe extern "C" fn(plugin: *const ClapPlugin) -> bool,
    stop_processing: unsafe extern "C" fn(plugin: *const ClapPlugin),
    reset: unsafe extern "C" fn(plugin: *const ClapPlugin),
    process: unsafe extern "C" fn(
        plugin: *const ClapPlugin, process: *const ClapProcess,
    ) -> ClapProcessStatus,
    get_extension: unsafe extern "C" fn(
        plugin: *const ClapPlugin, id: *const c_char,
    ) -> *const c_void,
    on_main_thread: unsafe extern "C" fn(plugin: *const ClapPlugin),
}

// ---------------------------------------------------------------------------
// clap_process
// ---------------------------------------------------------------------------

type ClapProcessStatus = i32;
const CLAP_PROCESS_CONTINUE: ClapProcessStatus = 0;
#[allow(dead_code)]
const CLAP_PROCESS_CONTINUE_IF_NOT_QUIET: ClapProcessStatus = 1;
#[allow(dead_code)]
const CLAP_PROCESS_TAIL: ClapProcessStatus = 2;
#[allow(dead_code)]
const CLAP_PROCESS_SLEEP: ClapProcessStatus = 3;

#[repr(C)]
struct ClapProcess {
    steady_time: i64,
    frames_count: u32,
    transport: *const c_void, // clap_event_transport (nullable)
    audio_inputs: *const ClapAudioBuffer,
    audio_outputs: *mut ClapAudioBuffer,
    audio_inputs_count: u32,
    audio_outputs_count: u32,
    in_events: *const ClapInputEvents,
    out_events: *const ClapOutputEvents,
}

#[repr(C)]
struct ClapAudioBuffer {
    data32: *mut *mut f32,
    data64: *mut *mut f64,
    channel_count: u32,
    latency: u32,
    constant_mask: u64,
}

// ---------------------------------------------------------------------------
// Minimal event list stubs (empty for now)
// ---------------------------------------------------------------------------

#[repr(C)]
struct ClapInputEvents {
    ctx: *mut c_void,
    size: unsafe extern "C" fn(list: *const ClapInputEvents) -> u32,
    get: unsafe extern "C" fn(list: *const ClapInputEvents, index: u32) -> *const c_void,
}

#[repr(C)]
struct ClapOutputEvents {
    ctx: *mut c_void,
    try_push: unsafe extern "C" fn(list: *const ClapOutputEvents, event: *const c_void) -> bool,
}

// Empty event list callbacks
unsafe extern "C" fn empty_in_size(_list: *const ClapInputEvents) -> u32 { 0 }
unsafe extern "C" fn empty_in_get(_list: *const ClapInputEvents, _index: u32) -> *const c_void { ptr::null() }
unsafe extern "C" fn empty_out_push(_list: *const ClapOutputEvents, _event: *const c_void) -> bool { true }

// ---------------------------------------------------------------------------
// clap_plugin_params extension
// ---------------------------------------------------------------------------

const CLAP_EXT_PARAMS: &[u8] = b"clap.params\0";

#[repr(C)]
struct ClapPluginParams {
    count: unsafe extern "C" fn(plugin: *const ClapPlugin) -> u32,
    get_info: unsafe extern "C" fn(
        plugin: *const ClapPlugin, index: u32, info: *mut ClapParamInfo,
    ) -> bool,
    get_value: unsafe extern "C" fn(
        plugin: *const ClapPlugin, param_id: u32, value: *mut f64,
    ) -> bool,
    value_to_text: unsafe extern "C" fn(
        plugin: *const ClapPlugin, param_id: u32, value: f64,
        display: *mut c_char, size: u32,
    ) -> bool,
    text_to_value: unsafe extern "C" fn(
        plugin: *const ClapPlugin, param_id: u32, display: *const c_char,
        value: *mut f64,
    ) -> bool,
    flush: unsafe extern "C" fn(
        plugin: *const ClapPlugin,
        in_events: *const ClapInputEvents,
        out_events: *const ClapOutputEvents,
    ),
}

#[repr(C)]
struct ClapParamInfo {
    id: u32,
    flags: u32,
    cookie: *mut c_void,
    name: [c_char; 256],
    module: [c_char; 1024],
    min_value: f64,
    max_value: f64,
    default_value: f64,
}

// ---------------------------------------------------------------------------
// clap_plugin_state extension
// ---------------------------------------------------------------------------

const CLAP_EXT_STATE: &[u8] = b"clap.state\0";

#[repr(C)]
struct ClapPluginState {
    save: unsafe extern "C" fn(plugin: *const ClapPlugin, stream: *const ClapOStream) -> bool,
    load: unsafe extern "C" fn(plugin: *const ClapPlugin, stream: *const ClapIStream) -> bool,
}

#[repr(C)]
struct ClapIStream {
    ctx: *mut c_void,
    read: unsafe extern "C" fn(stream: *const ClapIStream, buffer: *mut c_void, size: u64) -> i64,
}

#[repr(C)]
struct ClapOStream {
    ctx: *mut c_void,
    write: unsafe extern "C" fn(stream: *const ClapOStream, buffer: *const c_void, size: u64) -> i64,
}

// ============================================================================
// Helpers
// ============================================================================

unsafe fn cstr_to_string(ptr: *const c_char) -> String {
    if ptr.is_null() { return String::new(); }
    CStr::from_ptr(ptr).to_string_lossy().to_string()
}

unsafe fn read_features(features: *const *const c_char) -> Vec<String> {
    let mut result = Vec::new();
    if features.is_null() { return result; }
    let mut i = 0;
    loop {
        let ptr = *features.add(i);
        if ptr.is_null() { break; }
        result.push(CStr::from_ptr(ptr).to_string_lossy().to_string());
        i += 1;
    }
    result
}

fn cchar_array_to_string(arr: &[c_char]) -> String {
    let bytes: Vec<u8> = arr.iter()
        .take_while(|&&c| c != 0)
        .map(|&c| c as u8)
        .collect();
    String::from_utf8_lossy(&bytes).to_string()
}

// ============================================================================
// CLAP Plugin Scanner
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClapPluginInfo {
    pub plugin_id: String,
    pub name: String,
    pub vendor: String,
    pub description: String,
    pub url: String,
    pub version: String,
    pub features: Vec<String>,
    pub file_path: PathBuf,
}

impl ClapPluginInfo {
    pub fn is_instrument(&self) -> bool {
        self.features.iter().any(|f| f == "instrument" || f == "synthesizer" || f == "sampler")
    }
    pub fn is_effect(&self) -> bool {
        self.features.iter().any(|f| {
            f == "audio-effect" || f == "analyzer" || f == "delay"
                || f == "reverb" || f == "compressor" || f == "equalizer"
        })
    }
}

#[derive(Debug, Default)]
pub struct ClapScanResult {
    pub plugins: Vec<ClapPluginInfo>,
    pub errors: Vec<String>,
    pub scan_time_ms: u64,
}

pub fn clap_search_paths() -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Some(home) = std::env::var_os("HOME") {
        let home = PathBuf::from(home);
        paths.push(home.join(".clap"));
    }
    paths.push(PathBuf::from("/usr/lib/clap"));
    paths.push(PathBuf::from("/usr/local/lib/clap"));
    paths.push(PathBuf::from("/usr/lib/x86_64-linux-gnu/clap"));
    if let Some(extra) = std::env::var_os("CLAP_PATH") {
        for p in std::env::split_paths(&extra) { paths.push(p); }
    }
    paths
}

pub fn scan_clap_plugins() -> ClapScanResult {
    let start = std::time::Instant::now();
    let mut result = ClapScanResult::default();
    for search_dir in clap_search_paths() {
        if !search_dir.exists() { continue; }
        debug!("Scanning CLAP directory: {}", search_dir.display());
        scan_clap_directory(&search_dir, &mut result);
    }
    result.scan_time_ms = start.elapsed().as_millis() as u64;
    info!("CLAP scan: {} plugins in {}ms", result.plugins.len(), result.scan_time_ms);
    result
}

fn scan_clap_directory(dir: &Path, result: &mut ClapScanResult) {
    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(e) => { result.errors.push(format!("{}: {}", dir.display(), e)); return; }
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() && path.extension().map(|e| e.to_ascii_lowercase() == "clap").unwrap_or(false) {
            match probe_clap_file(&path) {
                Ok(infos) => result.plugins.extend(infos),
                Err(e) => result.errors.push(format!("{}: {}", path.display(), e)),
            }
        } else if path.is_dir() {
            scan_clap_directory(&path, result);
        }
    }
}

/// Probe a .clap file: dlopen → clap_entry → factory → enumerate descriptors.
fn probe_clap_file(file_path: &Path) -> Result<Vec<ClapPluginInfo>, String> {
    let lib = unsafe { Library::new(file_path) }
        .map_err(|e| format!("dlopen {}: {}", file_path.display(), e))?;

    let entry: Symbol<*const ClapPluginEntry> = unsafe {
        lib.get(b"clap_entry\0")
    }.map_err(|e| format!("clap_entry: {}", e))?;

    let entry = unsafe { &**entry };

    // Initialize entry
    let path_cstr = CString::new(file_path.to_string_lossy().as_bytes())
        .map_err(|_| "Invalid path".to_string())?;

    if !unsafe { (entry.init)(path_cstr.as_ptr()) } {
        return Err("clap_entry.init() failed".to_string());
    }

    // Get plugin factory
    let factory_ptr = unsafe { (entry.get_factory)(CLAP_PLUGIN_FACTORY_ID.as_ptr() as *const c_char) };
    if factory_ptr.is_null() {
        unsafe { (entry.deinit)() };
        return Err("get_factory returned null".to_string());
    }

    let factory = factory_ptr as *const ClapPluginFactory;
    let count = unsafe { ((*factory).get_plugin_count)(factory) };

    let mut plugins = Vec::new();
    for i in 0..count {
        let desc = unsafe { ((*factory).get_plugin_descriptor)(factory, i) };
        if desc.is_null() { continue; }
        let desc = unsafe { &*desc };

        plugins.push(ClapPluginInfo {
            plugin_id: unsafe { cstr_to_string(desc.id) },
            name: unsafe { cstr_to_string(desc.name) },
            vendor: unsafe { cstr_to_string(desc.vendor) },
            description: unsafe { cstr_to_string(desc.description) },
            url: unsafe { cstr_to_string(desc.url) },
            version: unsafe { cstr_to_string(desc.version) },
            features: unsafe { read_features(desc.features) },
            file_path: file_path.to_path_buf(),
        });
    }

    // Don't deinit yet — instances may need the entry alive.
    // Leak lib to keep .so mapped.
    std::mem::forget(lib);

    Ok(plugins)
}

// ============================================================================
// CLAP Plugin Instance — Real FFI
// ============================================================================

/// Keep host data alive for the lifetime of the plugin.
struct HostData {
    _name: CString,
    _vendor: CString,
    _url: CString,
    _version: CString,
    host: Box<ClapHost>,
}

pub struct ClapInstance {
    info: ClapPluginInfo,
    _library: Library,
    _host_data: HostData,
    plugin: *const ClapPlugin,
    params_ext: *const ClapPluginParams,
    state_ext: *const ClapPluginState,

    sample_rate: f64,
    max_block_size: u32,
    is_active: bool,
    is_processing: bool,

    parameters: HashMap<u32, (f64, String)>,
    param_ids: Vec<u32>,
    saved_state: Vec<u8>,
    latency: u32,

    // Pre-allocated for process()
    deinterleave_l: Vec<f32>,
    deinterleave_r: Vec<f32>,
    input_ptrs: Vec<*mut f32>,
    output_ptrs: Vec<*mut f32>,
}

unsafe impl Send for ClapInstance {}

impl ClapInstance {
    /// Load a CLAP plugin instance.
    pub fn load(info: &ClapPluginInfo, sample_rate: f64, max_block_size: u32) -> Result<Self, String> {
        let lib = unsafe { Library::new(&info.file_path) }
            .map_err(|e| format!("dlopen: {}", e))?;

        let entry: Symbol<*const ClapPluginEntry> = unsafe {
            lib.get(b"clap_entry\0")
        }.map_err(|e| format!("clap_entry: {}", e))?;
        let entry = unsafe { &**entry };

        let path_cstr = CString::new(info.file_path.to_string_lossy().as_bytes())
            .map_err(|_| "Invalid path".to_string())?;
        if !unsafe { (entry.init)(path_cstr.as_ptr()) } {
            return Err("init failed".into());
        }

        let factory_ptr = unsafe {
            (entry.get_factory)(CLAP_PLUGIN_FACTORY_ID.as_ptr() as *const c_char)
        };
        if factory_ptr.is_null() { return Err("No factory".into()); }
        let factory = factory_ptr as *const ClapPluginFactory;

        // Build host struct
        let host_name = CString::new("Py_DAW").unwrap();
        let host_vendor = CString::new("ChronoScaleStudio").unwrap();
        let host_url = CString::new("https://github.com/pydaw").unwrap();
        let host_version = CString::new("0.0.20").unwrap();

        let host = Box::new(ClapHost {
            clap_version: CLAP_VERSION,
            host_data: ptr::null_mut(),
            name: host_name.as_ptr(),
            vendor: host_vendor.as_ptr(),
            url: host_url.as_ptr(),
            version: host_version.as_ptr(),
            get_extension: host_get_extension,
            request_restart: host_request_restart,
            request_process: host_request_process,
            request_callback: host_request_callback,
        });

        let host_data = HostData {
            _name: host_name,
            _vendor: host_vendor,
            _url: host_url,
            _version: host_version,
            host,
        };

        // Create plugin
        let plugin_id = CString::new(info.plugin_id.as_bytes())
            .map_err(|_| "Invalid plugin_id".to_string())?;
        let plugin = unsafe {
            ((*factory).create_plugin)(factory, &*host_data.host as *const _, plugin_id.as_ptr())
        };
        if plugin.is_null() { return Err("create_plugin returned null".into()); }

        // init
        if !unsafe { ((*plugin).init)(plugin) } {
            unsafe { ((*plugin).destroy)(plugin) };
            return Err("plugin.init() failed".into());
        }

        // Get extensions
        let params_id = CString::new(CLAP_EXT_PARAMS).unwrap();
        let params_ext = unsafe {
            ((*plugin).get_extension)(plugin, params_id.as_ptr())
        } as *const ClapPluginParams;

        let state_id = CString::new(CLAP_EXT_STATE).unwrap();
        let state_ext = unsafe {
            ((*plugin).get_extension)(plugin, state_id.as_ptr())
        } as *const ClapPluginState;

        let bs = max_block_size as usize;
        let mut inst = Self {
            info: info.clone(),
            _library: lib,
            _host_data: host_data,
            plugin, params_ext, state_ext,
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

        inst.activate(sample_rate, max_block_size)?;
        inst.discover_parameters();
        Ok(inst)
    }

    fn activate(&mut self, sample_rate: f64, max_block_size: u32) -> Result<(), String> {
        if !unsafe { ((*self.plugin).activate)(self.plugin, sample_rate, 1, max_block_size) } {
            return Err("activate failed".into());
        }
        self.is_active = true;

        if !unsafe { ((*self.plugin).start_processing)(self.plugin) } {
            warn!("CLAP start_processing failed (non-fatal)");
        } else {
            self.is_processing = true;
        }

        self.sample_rate = sample_rate;
        self.max_block_size = max_block_size;
        info!("CLAP ready: {} @ {}Hz, bs={}", self.info.name, sample_rate, max_block_size);
        Ok(())
    }

    fn discover_parameters(&mut self) {
        if self.params_ext.is_null() { return; }
        let ext = unsafe { &*self.params_ext };
        let count = unsafe { (ext.count)(self.plugin) };
        for i in 0..count {
            let mut pi = ClapParamInfo {
                id: 0, flags: 0, cookie: ptr::null_mut(),
                name: [0; 256], module: [0; 1024],
                min_value: 0.0, max_value: 1.0, default_value: 0.0,
            };
            if unsafe { (ext.get_info)(self.plugin, i, &mut pi) } {
                let name = cchar_array_to_string(&pi.name);
                let mut value = pi.default_value;
                let _ = unsafe { (ext.get_value)(self.plugin, pi.id, &mut value) };
                self.parameters.insert(pi.id, (value, name));
                self.param_ids.push(pi.id);
            }
        }
        debug!("CLAP {} has {} params", self.info.name, self.parameters.len());
    }

    pub fn deactivate(&mut self) {
        if self.is_processing {
            unsafe { ((*self.plugin).stop_processing)(self.plugin) };
            self.is_processing = false;
        }
        if self.is_active {
            unsafe { ((*self.plugin).deactivate)(self.plugin) };
            self.is_active = false;
        }
    }
}

impl AudioPlugin for ClapInstance {
    fn process(&mut self, buffer: &mut AudioBuffer, _sample_rate: u32) {
        if !self.is_processing || self.plugin.is_null() { return; }

        let frames = buffer.frames;
        let ch = buffer.channels.min(2);

        if self.deinterleave_l.len() < frames {
            self.deinterleave_l.resize(frames, 0.0);
            self.deinterleave_r.resize(frames, 0.0);
        }

        // Deinterleave
        for i in 0..frames {
            self.deinterleave_l[i] = buffer.data[i * buffer.channels];
            self.deinterleave_r[i] = if ch > 1 { buffer.data[i * buffer.channels + 1] } else { 0.0 };
        }

        self.input_ptrs[0] = self.deinterleave_l.as_mut_ptr();
        self.input_ptrs[1] = self.deinterleave_r.as_mut_ptr();
        self.output_ptrs[0] = self.deinterleave_l.as_mut_ptr();
        self.output_ptrs[1] = self.deinterleave_r.as_mut_ptr();

        let in_buf = ClapAudioBuffer {
            data32: self.input_ptrs.as_mut_ptr(),
            data64: ptr::null_mut(),
            channel_count: ch as u32, latency: 0, constant_mask: 0,
        };
        let mut out_buf = ClapAudioBuffer {
            data32: self.output_ptrs.as_mut_ptr(),
            data64: ptr::null_mut(),
            channel_count: ch as u32, latency: 0, constant_mask: 0,
        };

        let in_events = ClapInputEvents {
            ctx: ptr::null_mut(),
            size: empty_in_size,
            get: empty_in_get,
        };
        let out_events = ClapOutputEvents {
            ctx: ptr::null_mut(),
            try_push: empty_out_push,
        };

        let process = ClapProcess {
            steady_time: -1,
            frames_count: frames as u32,
            transport: ptr::null(),
            audio_inputs: &in_buf as *const _,
            audio_outputs: &mut out_buf as *mut _,
            audio_inputs_count: 1,
            audio_outputs_count: 1,
            in_events: &in_events,
            out_events: &out_events,
        };

        let _ = unsafe { ((*self.plugin).process)(self.plugin, &process) };

        // Reinterleave
        for i in 0..frames {
            buffer.data[i * buffer.channels] = self.deinterleave_l[i];
            if ch > 1 {
                buffer.data[i * buffer.channels + 1] = self.deinterleave_r[i];
            }
        }
    }

    fn id(&self) -> &str { &self.info.plugin_id }
    fn name(&self) -> &str { &self.info.name }

    fn set_parameter(&mut self, index: u32, value: f64) {
        let pid = if (index as usize) < self.param_ids.len() {
            self.param_ids[index as usize]
        } else { index };
        if let Some(e) = self.parameters.get_mut(&pid) { e.0 = value; }
        // CLAP params are set via events in process() or flush()
        // For non-audio-thread, we can use flush:
        if !self.params_ext.is_null() {
            let in_events = ClapInputEvents {
                ctx: ptr::null_mut(), size: empty_in_size, get: empty_in_get,
            };
            let out_events = ClapOutputEvents {
                ctx: ptr::null_mut(), try_push: empty_out_push,
            };
            let ext = unsafe { &*self.params_ext };
            unsafe { (ext.flush)(self.plugin, &in_events, &out_events) };
        }
    }

    fn get_parameter(&self, index: u32) -> f64 {
        let pid = if (index as usize) < self.param_ids.len() {
            self.param_ids[index as usize]
        } else { index };
        if !self.params_ext.is_null() {
            let ext = unsafe { &*self.params_ext };
            let mut value = 0.0;
            if unsafe { (ext.get_value)(self.plugin, pid, &mut value) } {
                return value;
            }
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
        if self.state_ext.is_null() { return self.saved_state.clone(); }
        // TODO: Implement ClapOStream that writes to Vec<u8>
        self.saved_state.clone()
    }

    fn load_state(&mut self, data: &[u8]) -> Result<(), String> {
        if self.state_ext.is_null() {
            self.saved_state = data.to_vec();
            return Ok(());
        }
        // TODO: Implement ClapIStream that reads from &[u8]
        self.saved_state = data.to_vec();
        Ok(())
    }

    fn latency_samples(&self) -> u32 { self.latency }
}

impl Drop for ClapInstance {
    fn drop(&mut self) {
        self.deactivate();
        if !self.plugin.is_null() {
            unsafe { ((*self.plugin).destroy)(self.plugin) };
        }
    }
}

/// Load a CLAP plugin by file path and plugin_id.
pub fn load_clap(
    file_path: &Path, plugin_id: &str,
    sample_rate: f64, max_block_size: u32,
) -> Result<ClapInstance, String> {
    let scan = probe_clap_file(file_path)?;
    let info = scan.iter()
        .find(|p| p.plugin_id == plugin_id)
        .ok_or_else(|| format!("Plugin {} not in {}", plugin_id, file_path.display()))?
        .clone();
    ClapInstance::load(&info, sample_rate, max_block_size)
}
