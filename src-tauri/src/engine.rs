/// Python engine IPC — stdin/stdout JSON Lines pipe.
///
/// One shared `EngineState` (Tauri managed state). Requests carry an `id`;
/// every response line (deltas and the terminal event) is routed back to the
/// callback registered for that id.
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};

use serde_json::Value;
use tauri::AppHandle;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

type ResponseCallback = Arc<dyn Fn(Value) + Send + Sync + 'static>;

struct EngineInner {
    // Option porque `CommandChild::kill` consome o processo.
    child: Option<CommandChild>,
    pending: HashMap<String, ResponseCallback>,
}

#[derive(Clone)]
pub struct EngineState(Arc<Mutex<EngineInner>>);

fn is_terminal(ev_type: &str) -> bool {
    ev_type == "chat_done"
        || ev_type == "chat_error"
        || ev_type == "error"
        || ev_type.ends_with("_result")
        || ev_type.ends_with("_done")
}

impl EngineState {
    /// Spawn the sidecar and start the stdout reader task.
    pub fn spawn(app: &AppHandle) -> Result<Self, String> {
        let (mut rx, child) = app
            .shell()
            .sidecar("solaris-engine")
            .map_err(|e| e.to_string())?
            .spawn()
            .map_err(|e| e.to_string())?;

        let state = EngineState(Arc::new(Mutex::new(EngineInner {
            child: Some(child),
            pending: HashMap::new(),
        })));

        let state_clone = state.clone();
        tauri::async_runtime::spawn(async move {
            use tauri_plugin_shell::process::CommandEvent;
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        let text = String::from_utf8_lossy(&line);
                        let Ok(val) = serde_json::from_str::<Value>(text.trim()) else {
                            continue;
                        };
                        let id = val["id"].as_str().unwrap_or("").to_string();
                        let terminal = is_terminal(val["type"].as_str().unwrap_or(""));

                        // Clona o callback e solta o lock antes de chamá-lo,
                        // para o callback poder usar o engine sem deadlock.
                        let cb = {
                            let mut guard = state_clone.0.lock().unwrap();
                            if terminal {
                                guard.pending.remove(&id)
                            } else {
                                guard.pending.get(&id).cloned()
                            }
                        };
                        if let Some(cb) = cb {
                            cb(val);
                        }
                    }
                    CommandEvent::Terminated(_) => {
                        let callbacks = {
                            let mut guard = state_clone.0.lock().unwrap();
                            guard.child = None;
                            std::mem::take(&mut guard.pending)
                        };
                        for (id, callback) in callbacks {
                            callback(
                                serde_json::json!({"id": id, "type": "error", "message": "O motor foi encerrado."}),
                            );
                        }
                        break;
                    }
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
        callback: impl Fn(Value) + Send + Sync + 'static,
    ) -> Result<(), String> {
        let id = req["id"].as_str().unwrap_or("").to_string();
        let mut line = serde_json::to_string(&req).map_err(|e| e.to_string())?;
        line.push('\n');

        let mut guard = self.0.lock().unwrap();
        let child = guard
            .child
            .as_mut()
            .ok_or_else(|| "engine encerrado".to_string())?;
        child.write(line.as_bytes()).map_err(|e| e.to_string())?;
        guard.pending.insert(id, Arc::new(callback));
        Ok(())
    }

    pub fn kill(&self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(child) = guard.child.take() {
                let _ = child.kill();
            }
        }
    }
}
