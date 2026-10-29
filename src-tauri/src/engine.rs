/// Python engine IPC — stdin/stdout JSON Lines pipe.
///
/// One shared `EngineState` (Tauri managed state). Requests are serialized via
/// a Mutex so only one JSON line is in-flight at a time; streaming delta events
/// arrive on the same stdout and are routed by the `id` field.
use std::{
    collections::HashMap,
    io::Write,
    sync::{Arc, Mutex},
};

use serde_json::Value;
use tauri::{ipc::Channel, AppHandle};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

type DeltaCallback = Box<dyn Fn(Value) + Send + 'static>;

struct EngineInner {
    child: CommandChild,
    pending: HashMap<String, DeltaCallback>,
}

#[derive(Clone)]
pub struct EngineState(Arc<Mutex<EngineInner>>);

impl EngineState {
    /// Spawn the sidecar and start the stdout reader task.
    pub fn spawn(app: &AppHandle) -> Result<Self, String> {
        let shell = app.shell();
        let (mut rx, child) = shell
            .sidecar("solaris-engine")
            .map_err(|e| e.to_string())?
            .spawn()
            .map_err(|e| e.to_string())?;

        let state = EngineState(Arc::new(Mutex::new(EngineInner {
            child,
            pending: HashMap::new(),
        })));

        let state_clone = state.clone();
        tauri::async_runtime::spawn(async move {
            use tauri_plugin_shell::process::CommandEvent;
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        let text = String::from_utf8_lossy(&line);
                        if let Ok(val) = serde_json::from_str::<Value>(text.trim()) {
                            let id = val["id"].as_str().unwrap_or("").to_string();
                            let ev_type = val["type"].as_str().unwrap_or("").to_string();

                            let cb = {
                                let guard = state_clone.0.lock().unwrap();
                                if ev_type == "chat_done"
                                    || ev_type == "chat_error"
                                    || ev_type.ends_with("_result")
                                    || ev_type.ends_with("_done")
                                    || ev_type == "error"
                                {
                                    // terminal event — take the callback out
                                    drop(guard);
                                    let mut guard2 = state_clone.0.lock().unwrap();
                                    guard2.pending.remove(&id)
                                } else {
                                    guard.pending.get(&id).map(|cb| {
                                        // non-owning call — clone the Arc trick via unsafe isn't
                                        // needed; we just call through the guard
                                        cb(val.clone());
                                        None::<DeltaCallback>
                                    }).flatten()
                                }
                            };

                            // For delta events, call while still holding nothing
                            if ev_type == "chat_delta" {
                                let guard = state_clone.0.lock().unwrap();
                                if let Some(cb) = guard.pending.get(&id) {
                                    cb(val);
                                }
                            } else if let Some(cb) = cb {
                                cb(val);
                            }
                        }
                    }
                    CommandEvent::Terminated(_) => break,
                    _ => {}
                }
            }
        });

        Ok(state)
    }

    /// Send a request JSON and register a callback for responses keyed by id.
    pub fn send(
        &self,
        req: Value,
        callback: impl Fn(Value) + Send + 'static,
    ) -> Result<(), String> {
        let id = req["id"].as_str().unwrap_or("").to_string();
        let mut line = serde_json::to_string(&req).map_err(|e| e.to_string())?;
        line.push('\n');

        let mut guard = self.0.lock().unwrap();
        guard.pending.insert(id, Box::new(callback));
        guard
            .child
            .write(line.as_bytes())
            .map_err(|e| e.to_string())?;
        Ok(())
    }

    pub fn kill(&self) {
        if let Ok(mut guard) = self.0.lock() {
            let _ = guard.child.kill();
        }
    }
}
