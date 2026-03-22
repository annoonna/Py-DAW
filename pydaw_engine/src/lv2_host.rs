// ============================================================================
// LV2 Plugin Host — Phase P7C (Real FFI via libloading + lilv)
// ============================================================================
//
// Hosts LV2 plugins using the lilv C library loaded at runtime via libloading.
//
// Architecture:
//   1. Load liblilv-0.so dynamically (no compile-time linking needed)
//   2. Scanner: lilv_world_load_all → iterate plugins → metadata
//   3. Instance: lilv_plugin_instantiate → connect ports → activate
//   4. Process: lilv_instance_run(frames) on audio thread — zero-alloc
//   5. Ports: audio (f32 buffers), control (f32 values), atom (MIDI)
//
// LV2 is Linux-native:
//   - Turtle/RDF metadata → rich discovery without loading .so
//   - Port-based: audio, control, MIDI (atom), CV
//   - Extensions via URIs
//
// If liblilv-0.so is not installed, scanning returns empty results.
//
// v0.0.20.716 — Phase P7C (Claude Opus 4.6, 2026-03-21)
// ============================================================================

use std::collections::HashMap;
use std::ffi::{c_void, CStr, CString};
use std::os::raw::c_char;
use std::ptr;
use std::sync::OnceLock;

use libloading::Library;
use log::{info, warn};
use serde::{Deserialize, Serialize};

use crate::audio_graph::AudioBuffer;
use crate::plugin_host::AudioPlugin;

// ============================================================================
// Lilv FFI — dynamically loaded function pointers
// ============================================================================
//
// All lilv types are opaque pointers. We load functions at runtime so the
// engine compiles even without lilv installed.

type LilvWorld = c_void;
type LilvPlugin = c_void;
type LilvPlugins = c_void;
type LilvInstance = c_void;
type LilvNode = c_void;
type LilvIter = c_void;
type LilvPort = c_void;

/// Runtime-loaded lilv function table.
/// Loaded once via OnceLock on first use.
struct LilvApi {
    _lib: Library,

    // World
    world_new: unsafe extern "C" fn() -> *mut LilvWorld,
    world_free: unsafe extern "C" fn(*mut LilvWorld),
    world_load_all: unsafe extern "C" fn(*mut LilvWorld),
    world_get_all_plugins: unsafe extern "C" fn(*const LilvWorld) -> *const LilvPlugins,

    // Plugins iteration
    plugins_size: unsafe extern "C" fn(*const LilvPlugins) -> u32,
    plugins_begin: unsafe extern "C" fn(*const LilvPlugins) -> *mut LilvIter,
    plugins_next: unsafe extern "C" fn(*const LilvPlugins, *mut LilvIter) -> *mut LilvIter,
    plugins_is_end: unsafe extern "C" fn(*const LilvPlugins, *const LilvIter) -> bool,
    plugins_get: unsafe extern "C" fn(*const LilvPlugins, *const LilvIter) -> *const LilvPlugin,

    // Plugin metadata
    plugin_get_uri: unsafe extern "C" fn(*const LilvPlugin) -> *const LilvNode,
    plugin_get_name: unsafe extern "C" fn(*const LilvPlugin) -> *mut LilvNode,
    plugin_get_author_name: unsafe extern "C" fn(*const LilvPlugin) -> *mut LilvNode,
    plugin_get_num_ports: unsafe extern "C" fn(*const LilvPlugin) -> u32,
    plugin_get_port_by_index: unsafe extern "C" fn(*const LilvPlugin, u32) -> *const LilvPort,

    // Port queries
    port_is_a: unsafe extern "C" fn(*const LilvPlugin, *const LilvPort, *const LilvNode) -> bool,
    port_get_name: unsafe extern "C" fn(*const LilvPlugin, *const LilvPort) -> *mut LilvNode,

    // Plugin instantiation
    plugin_instantiate: unsafe extern "C" fn(
        *const LilvPlugin, f64, *const *const Lv2Feature,
    ) -> *mut LilvInstance,
    instance_free: unsafe extern "C" fn(*mut LilvInstance),

    // Instance methods (via descriptor)
    instance_get_descriptor: unsafe extern "C" fn(*const LilvInstance) -> *const Lv2Descriptor,
    instance_get_handle: unsafe extern "C" fn(*const LilvInstance) -> *mut c_void,

    // Node utilities
    new_uri: unsafe extern "C" fn(*mut LilvWorld, *const c_char) -> *mut LilvNode,
    node_as_string: unsafe extern "C" fn(*const LilvNode) -> *const c_char,
    node_free: unsafe extern "C" fn(*mut LilvNode),
}

// LV2 core structs

#[repr(C)]
struct Lv2Feature {
    uri: *const c_char,
    data: *mut c_void,
}

#[repr(C)]
struct Lv2Descriptor {
    uri: *const c_char,
    instantiate: *const c_void,
    connect_port: unsafe extern "C" fn(handle: *mut c_void, port: u32, data: *mut c_void),
    activate: unsafe extern "C" fn(handle: *mut c_void),
    run: unsafe extern "C" fn(handle: *mut c_void, n_samples: u32),
    deactivate: unsafe extern "C" fn(handle: *mut c_void),
    cleanup: unsafe extern "C" fn(handle: *mut c_void),
    extension_data: unsafe extern "C" fn(uri: *const c_char) -> *const c_void,
}

/// Load lilv dynamically. Returns None if liblilv is not installed.
fn load_lilv_api() -> Option<LilvApi> {
    // Try common library names
    let lib = unsafe {
        Library::new("liblilv-0.so.0")
            .or_else(|_| Library::new("liblilv-0.so"))
            .or_else(|_| Library::new("liblilv.so"))
    };

    let lib = match lib {
        Ok(l) => l,
        Err(e) => {
            warn!("liblilv not found (LV2 scanning disabled): {}", e);
            return None;
        }
    };

    macro_rules! load_fn {
        ($lib:expr, $name:literal) => {
            match unsafe { $lib.get::<*const c_void>($name) } {
                Ok(sym) => unsafe { std::mem::transmute(*sym) },
                Err(e) => {
                    warn!("lilv symbol {} not found: {}", stringify!($name), e);
                    return None;
                }
            }
        };
    }

    Some(LilvApi {
        world_new: load_fn!(lib, b"lilv_world_new\0"),
        world_free: load_fn!(lib, b"lilv_world_free\0"),
        world_load_all: load_fn!(lib, b"lilv_world_load_all\0"),
        world_get_all_plugins: load_fn!(lib, b"lilv_world_get_all_plugins\0"),
        plugins_size: load_fn!(lib, b"lilv_plugins_size\0"),
        plugins_begin: load_fn!(lib, b"lilv_plugins_begin\0"),
        plugins_next: load_fn!(lib, b"lilv_plugins_next\0"),
        plugins_is_end: load_fn!(lib, b"lilv_plugins_is_end\0"),
        plugins_get: load_fn!(lib, b"lilv_plugins_get\0"),
        plugin_get_uri: load_fn!(lib, b"lilv_plugin_get_uri\0"),
        plugin_get_name: load_fn!(lib, b"lilv_plugin_get_name\0"),
        plugin_get_author_name: load_fn!(lib, b"lilv_plugin_get_author_name\0"),
        plugin_get_num_ports: load_fn!(lib, b"lilv_plugin_get_num_ports\0"),
        plugin_get_port_by_index: load_fn!(lib, b"lilv_plugin_get_port_by_index\0"),
        port_is_a: load_fn!(lib, b"lilv_port_is_a\0"),
        port_get_name: load_fn!(lib, b"lilv_port_get_name\0"),
        plugin_instantiate: load_fn!(lib, b"lilv_plugin_instantiate\0"),
        instance_free: load_fn!(lib, b"lilv_instance_free\0"),
        instance_get_descriptor: load_fn!(lib, b"lilv_instance_get_descriptor\0"),
        instance_get_handle: load_fn!(lib, b"lilv_instance_get_handle\0"),
        new_uri: load_fn!(lib, b"lilv_new_uri\0"),
        node_as_string: load_fn!(lib, b"lilv_node_as_string\0"),
        node_free: load_fn!(lib, b"lilv_node_free\0"),
        _lib: lib,
    })
}

static LILV_API: OnceLock<Option<LilvApi>> = OnceLock::new();

fn get_lilv() -> Option<&'static LilvApi> {
    LILV_API.get_or_init(load_lilv_api).as_ref()
}

// ============================================================================
// Helper
// ============================================================================

unsafe fn node_to_string(api: &LilvApi, node: *const LilvNode) -> String {
    if node.is_null() { return String::new(); }
    let s = (api.node_as_string)(node);
    if s.is_null() { return String::new(); }
    CStr::from_ptr(s).to_string_lossy().to_string()
}

unsafe fn node_to_string_free(api: &LilvApi, node: *mut LilvNode) -> String {
    if node.is_null() { return String::new(); }
    let s = node_to_string(api, node);
    (api.node_free)(node);
    s
}

// ============================================================================
// LV2 Port Info
// ============================================================================

/// Port direction
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PortDirection { Input, Output }

/// Port type
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PortType { Audio, Control, Atom, Unknown }

/// Metadata for one port
#[derive(Debug, Clone)]
pub struct PortInfo {
    pub index: u32,
    pub name: String,
    pub direction: PortDirection,
    pub port_type: PortType,
    pub default_value: f32,
}

// ============================================================================
// LV2 Plugin Scanner
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Lv2PluginInfo {
    pub uri: String,
    pub name: String,
    pub author: String,
    pub num_ports: u32,
    pub audio_inputs: u32,
    pub audio_outputs: u32,
    pub control_inputs: u32,
}

#[derive(Debug, Default)]
pub struct Lv2ScanResult {
    pub plugins: Vec<Lv2PluginInfo>,
    pub errors: Vec<String>,
    pub scan_time_ms: u64,
}

/// Scan all installed LV2 plugins using lilv.
pub fn scan_lv2_plugins() -> Lv2ScanResult {
    let start = std::time::Instant::now();
    let mut result = Lv2ScanResult::default();

    let api = match get_lilv() {
        Some(a) => a,
        None => {
            result.errors.push("liblilv not available".to_string());
            return result;
        }
    };

    // Create world and load all plugins
    let world = unsafe { (api.world_new)() };
    if world.is_null() {
        result.errors.push("lilv_world_new failed".to_string());
        return result;
    }

    unsafe { (api.world_load_all)(world) };

    let plugins = unsafe { (api.world_get_all_plugins)(world) };
    if plugins.is_null() {
        unsafe { (api.world_free)(world) };
        return result;
    }

    // Create URI nodes for port type checking
    let audio_uri = CString::new("http://lv2plug.in/ns/lv2core#AudioPort").unwrap();
    let control_uri = CString::new("http://lv2plug.in/ns/lv2core#ControlPort").unwrap();
    let input_uri = CString::new("http://lv2plug.in/ns/lv2core#InputPort").unwrap();
    let output_uri = CString::new("http://lv2plug.in/ns/lv2core#OutputPort").unwrap();

    let audio_node = unsafe { (api.new_uri)(world, audio_uri.as_ptr()) };
    let control_node = unsafe { (api.new_uri)(world, control_uri.as_ptr()) };
    let input_node = unsafe { (api.new_uri)(world, input_uri.as_ptr()) };
    let output_node = unsafe { (api.new_uri)(world, output_uri.as_ptr()) };

    // Iterate plugins
    let mut iter = unsafe { (api.plugins_begin)(plugins) };
    while !unsafe { (api.plugins_is_end)(plugins, iter) } {
        let plugin = unsafe { (api.plugins_get)(plugins, iter) };
        if !plugin.is_null() {
            let uri_node = unsafe { (api.plugin_get_uri)(plugin) };
            let uri = unsafe { node_to_string(api, uri_node) };
            let name = unsafe { node_to_string_free(api, (api.plugin_get_name)(plugin)) };
            let author = unsafe { node_to_string_free(api, (api.plugin_get_author_name)(plugin)) };
            let num_ports = unsafe { (api.plugin_get_num_ports)(plugin) };

            // Count port types
            let mut audio_in = 0u32;
            let mut audio_out = 0u32;
            let mut ctrl_in = 0u32;

            for p in 0..num_ports {
                let port = unsafe { (api.plugin_get_port_by_index)(plugin, p) };
                if port.is_null() { continue; }

                let is_audio = unsafe { (api.port_is_a)(plugin, port, audio_node) };
                let is_control = unsafe { (api.port_is_a)(plugin, port, control_node) };
                let is_input = unsafe { (api.port_is_a)(plugin, port, input_node) };
                let is_output = unsafe { (api.port_is_a)(plugin, port, output_node) };

                if is_audio && is_input { audio_in += 1; }
                if is_audio && is_output { audio_out += 1; }
                if is_control && is_input { ctrl_in += 1; }
            }

            result.plugins.push(Lv2PluginInfo {
                uri, name, author, num_ports,
                audio_inputs: audio_in,
                audio_outputs: audio_out,
                control_inputs: ctrl_in,
            });
        }
        iter = unsafe { (api.plugins_next)(plugins, iter) };
    }

    // Cleanup
    unsafe {
        (api.node_free)(audio_node);
        (api.node_free)(control_node);
        (api.node_free)(input_node);
        (api.node_free)(output_node);
        (api.world_free)(world);
    }

    result.scan_time_ms = start.elapsed().as_millis() as u64;
    info!("LV2 scan: {} plugins in {}ms", result.plugins.len(), result.scan_time_ms);
    result
}

// ============================================================================
// LV2 Plugin Instance — Real FFI
// ============================================================================

pub struct Lv2Instance {
    info: Lv2PluginInfo,
    /// lilv instance handle
    instance: *mut LilvInstance,
    /// LV2 descriptor (for connect_port, run, etc.)
    descriptor: *const Lv2Descriptor,
    /// Plugin handle (passed to descriptor functions)
    handle: *mut c_void,
    /// World must stay alive as long as instance exists
    world: *mut LilvWorld,

    sample_rate: f64,
    is_active: bool,

    /// Port metadata
    ports: Vec<PortInfo>,
    /// Control port values: port_index → value
    controls: HashMap<u32, f32>,
    /// Parameter names (control input ports only): sequential index → (port_index, name)
    param_map: Vec<(u32, String)>,

    /// Pre-allocated audio buffers for non-interleaved processing
    audio_in_l: Vec<f32>,
    audio_in_r: Vec<f32>,
    audio_out_l: Vec<f32>,
    audio_out_r: Vec<f32>,

    saved_state: Vec<u8>,
}

unsafe impl Send for Lv2Instance {}

impl Lv2Instance {
    /// Load an LV2 plugin by URI.
    pub fn load(uri: &str, sample_rate: f64, max_block_size: u32) -> Result<Self, String> {
        let api = get_lilv().ok_or("liblilv not available")?;

        let world = unsafe { (api.world_new)() };
        if world.is_null() { return Err("world_new failed".into()); }
        unsafe { (api.world_load_all)(world) };

        let plugins = unsafe { (api.world_get_all_plugins)(world) };
        if plugins.is_null() {
            unsafe { (api.world_free)(world) };
            return Err("No plugins".into());
        }

        // Find plugin by URI
        let target_uri = CString::new(uri).map_err(|_| "Invalid URI")?;
        let target_node = unsafe { (api.new_uri)(world, target_uri.as_ptr()) };

        let mut found_plugin: *const LilvPlugin = ptr::null();

        let mut iter = unsafe { (api.plugins_begin)(plugins) };
        while !unsafe { (api.plugins_is_end)(plugins, iter) } {
            let p = unsafe { (api.plugins_get)(plugins, iter) };
            if !p.is_null() {
                let p_uri = unsafe { node_to_string(api, (api.plugin_get_uri)(p)) };
                if p_uri == uri {
                    found_plugin = p;
                    break;
                }
            }
            iter = unsafe { (api.plugins_next)(plugins, iter) };
        }

        unsafe { (api.node_free)(target_node) };

        if found_plugin.is_null() {
            unsafe { (api.world_free)(world) };
            return Err(format!("Plugin {} not found", uri));
        }

        // Create type nodes for port analysis
        let audio_uri_c = CString::new("http://lv2plug.in/ns/lv2core#AudioPort").unwrap();
        let control_uri_c = CString::new("http://lv2plug.in/ns/lv2core#ControlPort").unwrap();
        let input_uri_c = CString::new("http://lv2plug.in/ns/lv2core#InputPort").unwrap();
        let output_uri_c = CString::new("http://lv2plug.in/ns/lv2core#OutputPort").unwrap();
        let atom_uri_c = CString::new("http://lv2plug.in/ns/ext/atom#AtomPort").unwrap();

        let audio_node = unsafe { (api.new_uri)(world, audio_uri_c.as_ptr()) };
        let control_node = unsafe { (api.new_uri)(world, control_uri_c.as_ptr()) };
        let input_node = unsafe { (api.new_uri)(world, input_uri_c.as_ptr()) };
        let output_node = unsafe { (api.new_uri)(world, output_uri_c.as_ptr()) };
        let atom_node = unsafe { (api.new_uri)(world, atom_uri_c.as_ptr()) };

        // Analyze ports
        let num_ports = unsafe { (api.plugin_get_num_ports)(found_plugin) };
        let mut ports = Vec::new();
        let mut param_map = Vec::new();

        for i in 0..num_ports {
            let port = unsafe { (api.plugin_get_port_by_index)(found_plugin, i) };
            if port.is_null() { continue; }

            let name = unsafe { node_to_string_free(api, (api.port_get_name)(found_plugin, port)) };
            let is_input = unsafe { (api.port_is_a)(found_plugin, port, input_node) };
            let _is_output = unsafe { (api.port_is_a)(found_plugin, port, output_node) };
            let is_audio = unsafe { (api.port_is_a)(found_plugin, port, audio_node) };
            let is_control = unsafe { (api.port_is_a)(found_plugin, port, control_node) };
            let is_atom = unsafe { (api.port_is_a)(found_plugin, port, atom_node) };

            let direction = if is_input { PortDirection::Input } else { PortDirection::Output };
            let port_type = if is_audio { PortType::Audio }
                else if is_control { PortType::Control }
                else if is_atom { PortType::Atom }
                else { PortType::Unknown };

            if is_control && is_input {
                param_map.push((i, name.clone()));
            }

            ports.push(PortInfo {
                index: i, name, direction, port_type, default_value: 0.0,
            });
        }

        // Cleanup type nodes
        unsafe {
            (api.node_free)(audio_node);
            (api.node_free)(control_node);
            (api.node_free)(input_node);
            (api.node_free)(output_node);
            (api.node_free)(atom_node);
        }

        // Instantiate (NULL features for basic plugins)
        let null_feature: *const Lv2Feature = ptr::null();
        let features: [*const Lv2Feature; 1] = [null_feature];

        let instance = unsafe {
            (api.plugin_instantiate)(found_plugin, sample_rate, features.as_ptr())
        };
        if instance.is_null() {
            unsafe { (api.world_free)(world) };
            return Err("instantiate failed".into());
        }

        let descriptor = unsafe { (api.instance_get_descriptor)(instance) };
        let handle = unsafe { (api.instance_get_handle)(instance) };

        if descriptor.is_null() || handle.is_null() {
            unsafe { (api.instance_free)(instance); (api.world_free)(world); }
            return Err("No descriptor/handle".into());
        }

        // Build info
        let info_name = unsafe { node_to_string_free(api, (api.plugin_get_name)(found_plugin)) };
        let info_author = unsafe { node_to_string_free(api, (api.plugin_get_author_name)(found_plugin)) };

        let info = Lv2PluginInfo {
            uri: uri.to_string(),
            name: info_name,
            author: info_author,
            num_ports,
            audio_inputs: ports.iter().filter(|p| p.port_type == PortType::Audio && p.direction == PortDirection::Input).count() as u32,
            audio_outputs: ports.iter().filter(|p| p.port_type == PortType::Audio && p.direction == PortDirection::Output).count() as u32,
            control_inputs: param_map.len() as u32,
        };

        let bs = max_block_size as usize;
        let mut controls = HashMap::new();
        for pi in &ports {
            if pi.port_type == PortType::Control {
                controls.insert(pi.index, pi.default_value);
            }
        }

        let mut inst = Self {
            info, instance, descriptor, handle, world,
            sample_rate, is_active: false,
            ports, controls, param_map,
            audio_in_l: vec![0.0; bs],
            audio_in_r: vec![0.0; bs],
            audio_out_l: vec![0.0; bs],
            audio_out_r: vec![0.0; bs],
            saved_state: Vec::new(),
        };

        // Connect control ports to our values
        inst.connect_control_ports();

        // Activate
        unsafe { ((*descriptor).activate)(handle) };
        inst.is_active = true;

        info!("LV2 ready: {} @ {}Hz", inst.info.name, sample_rate);
        Ok(inst)
    }

    fn connect_control_ports(&mut self) {
        for pi in &self.ports {
            if pi.port_type == PortType::Control {
                if let Some(val) = self.controls.get_mut(&pi.index) {
                    unsafe {
                        ((*self.descriptor).connect_port)(
                            self.handle, pi.index, val as *mut f32 as *mut c_void,
                        );
                    }
                }
            }
        }
    }
}

impl AudioPlugin for Lv2Instance {
    fn process(&mut self, buffer: &mut AudioBuffer, _sample_rate: u32) {
        if !self.is_active || self.descriptor.is_null() { return; }

        let frames = buffer.frames;
        let ch = buffer.channels.min(2);

        // Resize if needed
        if self.audio_in_l.len() < frames {
            self.audio_in_l.resize(frames, 0.0);
            self.audio_in_r.resize(frames, 0.0);
            self.audio_out_l.resize(frames, 0.0);
            self.audio_out_r.resize(frames, 0.0);
        }

        // Deinterleave
        for i in 0..frames {
            self.audio_in_l[i] = buffer.data[i * buffer.channels];
            self.audio_in_r[i] = if ch > 1 { buffer.data[i * buffer.channels + 1] } else { 0.0 };
        }
        // Clear output
        for i in 0..frames {
            self.audio_out_l[i] = 0.0;
            self.audio_out_r[i] = 0.0;
        }

        // Connect audio ports
        let mut audio_in_idx = 0u32;
        let mut audio_out_idx = 0u32;
        for pi in &self.ports {
            match (pi.port_type, pi.direction) {
                (PortType::Audio, PortDirection::Input) => {
                    let buf = if audio_in_idx == 0 { self.audio_in_l.as_mut_ptr() }
                              else { self.audio_in_r.as_mut_ptr() };
                    unsafe {
                        ((*self.descriptor).connect_port)(self.handle, pi.index, buf as *mut c_void);
                    }
                    audio_in_idx += 1;
                }
                (PortType::Audio, PortDirection::Output) => {
                    let buf = if audio_out_idx == 0 { self.audio_out_l.as_mut_ptr() }
                              else { self.audio_out_r.as_mut_ptr() };
                    unsafe {
                        ((*self.descriptor).connect_port)(self.handle, pi.index, buf as *mut c_void);
                    }
                    audio_out_idx += 1;
                }
                _ => {}
            }
        }

        // Run
        unsafe { ((*self.descriptor).run)(self.handle, frames as u32) };

        // Reinterleave from output
        for i in 0..frames {
            buffer.data[i * buffer.channels] = self.audio_out_l[i];
            if ch > 1 {
                buffer.data[i * buffer.channels + 1] = self.audio_out_r[i];
            }
        }
    }

    fn id(&self) -> &str { &self.info.uri }
    fn name(&self) -> &str { &self.info.name }

    fn set_parameter(&mut self, index: u32, value: f64) {
        if let Some(&(port_idx, _)) = self.param_map.get(index as usize) {
            if let Some(v) = self.controls.get_mut(&port_idx) {
                *v = value as f32;
            }
        }
    }

    fn get_parameter(&self, index: u32) -> f64 {
        if let Some(&(port_idx, _)) = self.param_map.get(index as usize) {
            self.controls.get(&port_idx).map(|&v| v as f64).unwrap_or(0.0)
        } else { 0.0 }
    }

    fn parameter_count(&self) -> u32 { self.param_map.len() as u32 }

    fn parameter_name(&self, index: u32) -> String {
        self.param_map.get(index as usize)
            .map(|(_, name)| name.clone())
            .unwrap_or_default()
    }

    fn save_state(&self) -> Vec<u8> {
        // TODO: LV2 State interface (lv2:state)
        self.saved_state.clone()
    }

    fn load_state(&mut self, data: &[u8]) -> Result<(), String> {
        self.saved_state = data.to_vec();
        Ok(())
    }
}

impl Drop for Lv2Instance {
    fn drop(&mut self) {
        if self.is_active && !self.descriptor.is_null() {
            unsafe { ((*self.descriptor).deactivate)(self.handle) };
        }
        if !self.instance.is_null() {
            if let Some(api) = get_lilv() {
                unsafe { (api.instance_free)(self.instance) };
            }
        }
        if !self.world.is_null() {
            if let Some(api) = get_lilv() {
                unsafe { (api.world_free)(self.world) };
            }
        }
    }
}
