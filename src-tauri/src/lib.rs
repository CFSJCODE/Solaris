mod commands;
mod db;
mod engine;

use std::path::PathBuf;
use tauri::{Manager, RunEvent};

fn storage_dir(app: &tauri::AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("storage"))
        .join("storage")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // Open SQLite DB
            let storage = storage_dir(&handle);
            let conn = db::open(&storage).expect("failed to open database");
            app.manage(db::DbState(std::sync::Mutex::new(conn)));

            // Set env var so Python engine finds storage
            std::env::set_var("SOLARIS_STORAGE", storage.to_str().unwrap_or(""));

            // Spawn Python engine sidecar
            let engine = engine::EngineState::spawn(&handle)
                .expect("failed to spawn solaris-engine");
            app.manage(engine);

            #[cfg(debug_assertions)]
            if let Some(window) = app.get_webview_window("main") {
                window.open_devtools();
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::list_conversations,
            commands::new_conversation,
            commands::delete_conversation,
            commands::get_conversation,
            commands::chat_send,
            commands::list_models,
            commands::upload_document,
            commands::list_documents,
            commands::delete_document,
            commands::list_projects,
            commands::create_project,
            commands::rename_project,
            commands::delete_project,
        ])
        .build(tauri::generate_context!())
        .expect("error building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(engine) = app.try_state::<engine::EngineState>() {
                    engine.kill();
                }
            }
        });
}
