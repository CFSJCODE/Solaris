/// Tauri commands — bridge between frontend and engine/db.
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tauri::{ipc::Channel, State};

use crate::db::{Conversation, DbState, Document, Message, Project};
use crate::engine::EngineState;

static REQ_COUNTER: AtomicU64 = AtomicU64::new(1);

fn next_id() -> String {
    REQ_COUNTER.fetch_add(1, Ordering::Relaxed).to_string()
}

// ── Chat events (streamed via Channel) ────────────────────────────────────

#[derive(Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ChatEvent {
    Delta { text: String },
    Done { usage: Value },
    Error { message: String },
}

// ── Commands ──────────────────────────────────────────────────────────────

#[tauri::command]
pub fn list_conversations(db: State<DbState>) -> Result<Vec<Conversation>, String> {
    db.list_conversations().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn new_conversation(
    db: State<DbState>,
    title: Option<String>,
    project_id: Option<i64>,
) -> Result<i64, String> {
    db.create_conversation(
        title.as_deref().unwrap_or("Nova conversa"),
        project_id,
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn delete_conversation(db: State<DbState>, id: i64) -> Result<(), String> {
    db.delete_conversation(id).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_conversation(
    db: State<DbState>,
    id: i64,
) -> Result<Vec<Message>, String> {
    db.get_messages(id).map_err(|e| e.to_string())
}

/// Send a user message and stream back the assistant response.
#[tauri::command]
pub async fn chat_send(
    db: State<'_, DbState>,
    engine: State<'_, EngineState>,
    conversation_id: i64,
    message: String,
    model: Option<String>,
    provider: Option<String>,
    on_event: Channel<ChatEvent>,
) -> Result<(), String> {
    // Persist user message
    db.add_message(conversation_id, "user", &message, None, None, None)
        .map_err(|e| e.to_string())?;

    // Build history for the engine
    let history: Vec<Value> = db
        .get_messages(conversation_id)
        .map_err(|e| e.to_string())?
        .iter()
        .map(|m| json!({"role": m.role, "content": m.content}))
        .collect();

    // Build FTS memory context from user message keywords.
    // Strip non-alphanumeric characters so punctuation doesn't produce invalid FTS5 syntax.
    let fts_keywords: Vec<String> = message
        .split_whitespace()
        .map(|w| w.chars().filter(|c| c.is_alphanumeric()).collect::<String>())
        .filter(|w| w.len() > 3)
        .take(5)
        .collect();
    let fts_query = fts_keywords.join(" OR ");
    let memory_snippets = if !fts_query.is_empty() {
        db.fts_search(&fts_query, conversation_id, 3)
            .unwrap_or_default()
    } else {
        vec![]
    };
    let system_context: Option<String> = if memory_snippets.is_empty() {
        None
    } else {
        Some(format!(
            "Contexto de conversas anteriores (memória):\n{}",
            memory_snippets.join("\n---\n")
        ))
    };

    let req_id = next_id();
    let mut req = json!({
        "id": req_id,
        "type": "chat_stream",
        "messages": history,
    });
    if let Some(m) = model {
        req["model"] = Value::String(m);
    }
    if let Some(p) = provider {
        req["provider"] = Value::String(p);
    }
    if let Some(sys) = system_context {
        req["system"] = Value::String(sys);
    }

    // Accumulate the full reply so we can persist it
    let accumulated = std::sync::Arc::new(std::sync::Mutex::new(String::new()));
    let acc_clone = accumulated.clone();
    let ch = on_event.clone();

    let (tx, rx) = std::sync::mpsc::channel::<Value>();

    engine.send(req, move |val: Value| {
        let _ = tx.send(val);
    })?;

    // Process events — we're in an async context; use blocking_recv is fine here
    // because the engine runs on its own OS thread.
    let db_ref = db.inner();

    let mut usage_val = Value::Null;
    let mut err_msg: Option<String> = None;

    loop {
        match rx.recv() {
            Err(_) => break,
            Ok(val) => {
                let ev_type = val["type"].as_str().unwrap_or("").to_string();
                match ev_type.as_str() {
                    "chat_delta" => {
                        let text = val["text"].as_str().unwrap_or("").to_string();
                        acc_clone.lock().unwrap().push_str(&text);
                        let _ = ch.send(ChatEvent::Delta { text });
                    }
                    "chat_done" => {
                        usage_val = val["usage"].clone();
                        let _ = ch.send(ChatEvent::Done {
                            usage: usage_val.clone(),
                        });
                        break;
                    }
                    "chat_error" => {
                        let msg = val["message"]
                            .as_str()
                            .unwrap_or("Erro desconhecido")
                            .to_string();
                        err_msg = Some(msg.clone());
                        let _ = ch.send(ChatEvent::Error { message: msg });
                        break;
                    }
                    _ => {}
                }
            }
        }
    }

    // Persist assistant reply
    let full_reply = accumulated.lock().unwrap().clone();
    if !full_reply.is_empty() {
        let model_str = usage_val["model"].as_str();
        let provider_str = usage_val["provider"].as_str();
        let cost = usage_val["cost_usd"].as_f64();
        db_ref
            .add_message(
                conversation_id,
                "assistant",
                &full_reply,
                model_str,
                provider_str,
                cost,
            )
            .map_err(|e| e.to_string())?;
    }

    if let Some(e) = err_msg {
        if full_reply.is_empty() {
            return Err(e);
        }
    }

    Ok(())
}

// ── Projects ──────────────────────────────────────────────────────────────

#[tauri::command]
pub fn list_projects(db: State<DbState>) -> Result<Vec<Project>, String> {
    db.list_projects().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn create_project(
    db: State<DbState>,
    name: String,
    description: Option<String>,
) -> Result<i64, String> {
    db.create_project(&name, description.as_deref())
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn rename_project(
    db: State<DbState>,
    id: i64,
    name: String,
    description: Option<String>,
) -> Result<(), String> {
    db.rename_project(id, &name, description.as_deref())
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn delete_project(db: State<DbState>, id: i64) -> Result<(), String> {
    db.delete_project(id).map_err(|e| e.to_string())
}

// ── Models ────────────────────────────────────────────────────────────────

#[tauri::command]
pub async fn list_models(engine: State<'_, EngineState>) -> Result<Vec<Value>, String> {
    let req_id = next_id();
    let req = json!({"id": req_id, "type": "models_list"});
    let (tx, rx) = std::sync::mpsc::channel::<Value>();
    engine.send(req, move |val| {
        let _ = tx.send(val);
    })?;
    let resp = rx.recv().map_err(|e| e.to_string())?;
    Ok(resp["models"]
        .as_array()
        .cloned()
        .unwrap_or_default())
}

// ── Vision ────────────────────────────────────────────────────────────────

#[derive(Clone, Serialize)]
pub struct VisionFrame {
    pub jpeg_b64: String,
    pub detections: Vec<Detection>,
}

#[derive(Clone, Serialize)]
pub struct Detection {
    pub label: String,
    pub conf: f64,
    pub box_coords: Vec<i64>,
}

#[tauri::command]
pub async fn vision_frame(
    engine: State<'_, EngineState>,
    source: Option<u32>,
    conf: Option<f64>,
) -> Result<VisionFrame, String> {
    let req_id = next_id();
    let req = json!({
        "id": req_id,
        "type": "vision_frame",
        "source": source.unwrap_or(0),
        "conf": conf.unwrap_or(0.35),
    });
    let (tx, rx) = std::sync::mpsc::channel::<Value>();
    engine.send(req, move |val| { let _ = tx.send(val); })?;
    let resp = rx.recv().map_err(|e| e.to_string())?;

    if resp["type"] == "error" {
        return Err(resp["message"].as_str().unwrap_or("Erro desconhecido").to_string());
    }

    let jpeg_b64 = resp["jpeg_b64"].as_str().unwrap_or("").to_string();
    let detections: Vec<Detection> = resp["detections"]
        .as_array()
        .unwrap_or(&vec![])
        .iter()
        .map(|d| Detection {
            label: d["label"].as_str().unwrap_or("").to_string(),
            conf: d["conf"].as_f64().unwrap_or(0.0),
            box_coords: d["box"]
                .as_array()
                .unwrap_or(&vec![])
                .iter()
                .map(|v| v.as_i64().unwrap_or(0))
                .collect(),
        })
        .collect();

    Ok(VisionFrame { jpeg_b64, detections })
}

// ── Documents / RAG ───────────────────────────────────────────────────────

#[derive(Deserialize)]
pub struct UploadDocumentArgs {
    pub project_id: Option<i64>,
    pub filename: String,
    pub mime_type: String,
    pub content_b64: String,
}

#[tauri::command]
pub async fn upload_document(
    db: State<'_, DbState>,
    engine: State<'_, EngineState>,
    args: UploadDocumentArgs,
) -> Result<Document, String> {
    // 1. Extract text
    let req_id = next_id();
    let req = json!({
        "id": req_id,
        "type": "extract_text",
        "content_b64": args.content_b64,
        "mime_type": args.mime_type,
    });
    let (tx, rx) = std::sync::mpsc::channel::<Value>();
    engine.send(req, move |val| { let _ = tx.send(val); })?;
    let resp = rx.recv().map_err(|e| e.to_string())?;
    let text = resp["text"].as_str().unwrap_or("").to_string();

    // 2. Embed chunks
    let chunk_size = 512usize;
    let overlap = 64usize;
    let mut chunks: Vec<String> = Vec::new();
    let mut start = 0;
    // Fatiar por caractere: fatiar bytes quebra acentos (UTF-8) e causa panic.
    let t: Vec<char> = text.trim().chars().collect();
    while start < t.len() {
        let end = (start + chunk_size).min(t.len());
        let chunk = t[start..end].iter().collect::<String>().trim().to_string();
        if !chunk.is_empty() {
            chunks.push(chunk);
        }
        start += chunk_size - overlap;
    }

    if chunks.is_empty() {
        return Err("Documento vazio ou sem texto extraível.".into());
    }

    let req_id2 = next_id();
    let embed_req = json!({
        "id": req_id2,
        "type": "rag_embed",
        "texts": chunks,
    });
    let (tx2, rx2) = std::sync::mpsc::channel::<Value>();
    engine.send(embed_req, move |val| { let _ = tx2.send(val); })?;
    let embed_resp = rx2.recv().map_err(|e| e.to_string())?;
    let embeddings = embed_resp["embeddings"].clone();

    // 3. Save to DB and get doc_id for chunk IDs
    let chunk_count = chunks.len() as i64;
    let doc_id = db
        .add_document(args.project_id, &args.filename, &args.mime_type, chunk_count)
        .map_err(|e| e.to_string())?;

    // 4. Add chunks to ChromaDB
    let chunk_ids: Vec<String> = (0..chunks.len())
        .map(|i| format!("doc{}_{}", doc_id, i))
        .collect();
    let metadatas: Vec<Value> = (0..chunks.len())
        .map(|i| json!({"doc_id": doc_id, "chunk_idx": i, "filename": args.filename}))
        .collect();

    let req_id3 = next_id();
    let add_req = json!({
        "id": req_id3,
        "type": "rag_add_chunks",
        "project_id": args.project_id,
        "chunk_ids": chunk_ids,
        "embeddings": embeddings,
        "texts": chunks,
        "metadatas": metadatas,
    });
    let (tx3, rx3) = std::sync::mpsc::channel::<Value>();
    engine.send(add_req, move |val| { let _ = tx3.send(val); })?;
    rx3.recv().map_err(|e| e.to_string())?;

    // Return the created document record
    let docs = db
        .list_documents(args.project_id)
        .map_err(|e| e.to_string())?;
    docs.into_iter()
        .find(|d| d.id == doc_id)
        .ok_or_else(|| "Erro ao recuperar documento criado.".into())
}

#[tauri::command]
pub fn list_documents(
    db: State<DbState>,
    project_id: Option<i64>,
) -> Result<Vec<Document>, String> {
    db.list_documents(project_id).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn delete_document(
    db: State<'_, DbState>,
    engine: State<'_, EngineState>,
    id: i64,
    project_id: Option<i64>,
) -> Result<(), String> {
    // Build chunk IDs for this document (we don't store them, so reconstruct)
    let docs = db.list_documents(project_id).map_err(|e| e.to_string())?;
    if let Some(doc) = docs.iter().find(|d| d.id == id) {
        let chunk_ids: Vec<String> = (0..doc.chunk_count)
            .map(|i| format!("doc{}_{}", id, i))
            .collect();
        if !chunk_ids.is_empty() {
            let req_id = next_id();
            let req = json!({
                "id": req_id,
                "type": "rag_delete_chunks",
                "project_id": project_id,
                "chunk_ids": chunk_ids,
            });
            let (tx, rx) = std::sync::mpsc::channel::<Value>();
            engine.send(req, move |val| { let _ = tx.send(val); })?;
            rx.recv().map_err(|e| e.to_string())?;
        }
    }
    db.delete_document(id).map_err(|e| e.to_string())
}
