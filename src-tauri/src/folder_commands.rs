//! Comandos IPC das pastas locais vinculadas aos projetos.
use std::path::{Path, PathBuf};

use serde::Serialize;
use serde_json::json;
use tauri::{AppHandle, State};
use tauri_plugin_dialog::DialogExt;

use crate::commands::engine_request;
use crate::db::DbState;
use crate::engine::EngineState;
use crate::workspace::{
    self, base64_encode, read_text_file, FolderEdit, FolderFile, Kind, ProjectFolder,
    MAX_DOC_BYTES, MAX_TEXT_BYTES,
};

/// Diretório onde as versões anteriores de arquivos editados são preservadas.
pub struct FolderBackups(pub PathBuf);

#[derive(Serialize)]
pub struct IndexReport {
    pub folder: ProjectFolder,
    pub added: usize,
    pub updated: usize,
    pub removed: usize,
    pub unchanged: usize,
    pub unreadable: usize,
    pub skipped: usize,
    pub truncated: bool,
}

/// Abre o seletor nativo de pastas; devolve `None` quando o usuário cancela.
#[tauri::command]
pub async fn folder_pick(app: AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .set_title("Escolha a pasta de trabalho do projeto")
            .blocking_pick_folder()
            .map(|p| p.into_path().map(|p| p.to_string_lossy().to_string()))
            .transpose()
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn folder_attach(
    db: State<'_, DbState>,
    engine: State<'_, EngineState>,
    project_id: i64,
    path: String,
) -> Result<IndexReport, String> {
    let folder = db.attach_folder(project_id, Path::new(&path))?;
    index(&db, &engine, project_id, folder.id).await
}

#[tauri::command]
pub async fn folder_reindex(
    db: State<'_, DbState>,
    engine: State<'_, EngineState>,
    project_id: i64,
    folder_id: i64,
) -> Result<IndexReport, String> {
    index(&db, &engine, project_id, folder_id).await
}

#[tauri::command]
pub fn folder_list(db: State<DbState>, project_id: i64) -> Result<Vec<ProjectFolder>, String> {
    db.list_folders(project_id)
}

#[tauri::command]
pub fn folder_detach(db: State<DbState>, project_id: i64, folder_id: i64) -> Result<(), String> {
    db.detach_folder(project_id, folder_id)
}

#[tauri::command]
pub fn folder_set_enabled(
    db: State<DbState>,
    project_id: i64,
    folder_id: i64,
    enabled: bool,
) -> Result<(), String> {
    db.set_folder_enabled(project_id, folder_id, enabled)
}

#[tauri::command]
pub fn folder_files(
    db: State<DbState>,
    project_id: i64,
    folder_id: i64,
    filter: Option<String>,
    limit: Option<usize>,
) -> Result<Vec<FolderFile>, String> {
    db.folder_files(
        project_id,
        folder_id,
        filter.as_deref().unwrap_or(""),
        limit.unwrap_or(500),
    )
}

#[tauri::command]
pub fn folder_read(
    db: State<DbState>,
    project_id: i64,
    folder_id: i64,
    rel_path: String,
) -> Result<String, String> {
    db.folder_read(project_id, folder_id, &rel_path)
}

#[tauri::command]
pub fn folder_edits(
    db: State<DbState>,
    project_id: i64,
    status: Option<String>,
) -> Result<Vec<FolderEdit>, String> {
    db.list_edits(project_id, status.as_deref())
}

/// Aprova (grava) ou recusa uma proposta de edição.
#[tauri::command]
pub fn folder_edit_decide(
    db: State<DbState>,
    backups: State<FolderBackups>,
    project_id: i64,
    edit_id: i64,
    approve: bool,
) -> Result<FolderEdit, String> {
    workspace::decide_edit(&db, project_id, edit_id, approve, &backups.0)
}

/// Indexação incremental: só relê arquivos cujo tamanho ou data mudaram.
async fn index(
    db: &DbState,
    engine: &EngineState,
    project_id: i64,
    folder_id: i64,
) -> Result<IndexReport, String> {
    let folder = db.folder(project_id, folder_id)?;
    let known = db.folder_known_files(folder_id)?;
    let root = PathBuf::from(&folder.path);
    let known_for_scan = known.clone();
    // Varredura e leitura de texto fora da thread assíncrona.
    let (scan, texts) = tauri::async_runtime::spawn_blocking(move || {
        let scan = workspace::scan(&root)
            .map_err(|e| format!("Não foi possível ler a pasta {}: {e}", root.display()))?;
        let mut texts = Vec::new();
        for file in &scan.files {
            let unchanged = known_for_scan
                .get(&file.rel_path)
                .is_some_and(|k| k.size == file.size as i64 && k.mtime == file.mtime);
            if unchanged {
                continue;
            }
            let content = match file.kind {
                Kind::Text => read_text_file(&file.abs, MAX_TEXT_BYTES).map(Some),
                _ if file.size > MAX_DOC_BYTES => Err("Documento acima de 10 MB.".into()),
                _ => std::fs::read(&file.abs)
                    .map(|bytes| Some(base64_encode(&bytes)))
                    .map_err(|e| format!("Falha ao ler: {e}")),
            };
            texts.push((file.clone(), content));
        }
        Ok::<_, String>((scan, texts))
    })
    .await
    .map_err(|e| e.to_string())??;

    let (mut added, mut updated, mut unreadable) = (0, 0, 0);
    for (file, content) in texts {
        let text = match (file.kind, content) {
            (Kind::Text, Ok(Some(text))) => Ok(text),
            (_, Ok(Some(b64))) => engine_request(
                engine.clone(),
                json!({"type":"extract_text","content_b64":b64,"mime_type":file.kind.mime(),"filename":file.rel_path}),
            )
            .await
            .and_then(|r| {
                r["text"]
                    .as_str()
                    .filter(|t| !t.trim().is_empty())
                    .map(str::to_string)
                    .ok_or_else(|| "Sem texto extraível (PDF digitalizado precisa de OCR).".into())
            }),
            (_, Ok(None)) => Err("Sem conteúdo.".into()),
            (_, Err(e)) => Err(e),
        };
        match &text {
            Ok(t) => db.store_folder_file(folder_id, &file, Some(t), "")?,
            Err(note) => {
                unreadable += 1;
                db.store_folder_file(folder_id, &file, None, note)?
            }
        }
        if known.contains_key(&file.rel_path) {
            updated += 1;
        } else {
            added += 1;
        }
    }
    let present: std::collections::HashSet<&str> =
        scan.files.iter().map(|f| f.rel_path.as_str()).collect();
    let removed: Vec<String> = known
        .keys()
        .filter(|k| !present.contains(k.as_str()))
        .cloned()
        .collect();
    db.remove_folder_files(folder_id, &removed)?;
    db.finish_folder_index(folder_id, scan.skipped, scan.truncated)?;
    Ok(IndexReport {
        folder: db.folder(project_id, folder_id)?,
        unchanged: scan.files.len() - added - updated,
        added,
        updated,
        removed: removed.len(),
        unreadable,
        skipped: scan.skipped,
        truncated: scan.truncated,
    })
}
