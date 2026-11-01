//! Pastas locais vinculadas a projetos: indexação, contexto do chat e edições aprovadas.
//!
//! O núcleo deste módulo não depende do Tauri: varredura, validação de caminhos, extração das
//! propostas de edição e persistência SQLite são testáveis isoladamente. Os comandos IPC ficam
//! em `folder_commands.rs`.
use crate::db::DbState;
use crate::knowledge::{search_query, ContextSource};
use rusqlite::{params, Connection, OptionalExtension};
use serde::Serialize;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::time::UNIX_EPOCH;

/// Máximo de arquivos considerados por pasta; o restante é informado como truncado.
pub const MAX_FILES: usize = 4000;
/// Texto/código acima deste tamanho não é indexado nem editado.
pub const MAX_TEXT_BYTES: u64 = 2_000_000;
/// PDF/DOCX acima deste tamanho não é enviado ao extrator.
pub const MAX_DOC_BYTES: u64 = 10_000_000;
/// Conteúdo máximo de uma proposta de edição.
pub const MAX_EDIT_BYTES: usize = 1_000_000;
pub const MAX_FOLDERS_PER_PROJECT: i64 = 8;
const MAX_INDEXED_CHARS: usize = 500_000;
const MAX_DEPTH: usize = 16;
const MAX_EDITS_PER_REPLY: usize = 10;
const SEARCH_BUDGET: usize = 10_000;
const MENTION_BUDGET: usize = 24_000;
const OVERVIEW_PATHS: usize = 200;

const IGNORED_DIRS: &[&str] = &[
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "target",
    "dist",
    "build",
    "out",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".idea",
    ".vscode",
    ".vs",
    ".next",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "coverage",
    ".pio",
    ".gradle",
    ".terraform",
];

const TEXT_EXTENSIONS: &[&str] = &[
    "md",
    "markdown",
    "txt",
    "rst",
    "adoc",
    "py",
    "pyi",
    "rs",
    "ts",
    "tsx",
    "js",
    "jsx",
    "mjs",
    "cjs",
    "json",
    "jsonc",
    "toml",
    "yaml",
    "yml",
    "xml",
    "html",
    "htm",
    "css",
    "scss",
    "sass",
    "less",
    "sql",
    "sh",
    "bash",
    "zsh",
    "ps1",
    "psm1",
    "bat",
    "cmd",
    "c",
    "h",
    "cpp",
    "hpp",
    "cc",
    "hh",
    "cxx",
    "ino",
    "pde",
    "java",
    "kt",
    "kts",
    "go",
    "rb",
    "php",
    "cs",
    "swift",
    "lua",
    "r",
    "m",
    "csv",
    "tsv",
    "log",
    "ini",
    "cfg",
    "conf",
    "properties",
    "cmake",
    "mk",
    "v",
    "sv",
    "vhd",
    "vhdl",
    "s",
    "asm",
    "ld",
    "dts",
    "dtsi",
    "proto",
    "graphql",
    "gql",
    "vue",
    "svelte",
    "dart",
    "scala",
    "ex",
    "exs",
    "erl",
    "hs",
    "ml",
    "jl",
    "tex",
    "bib",
    "gitignore",
    "dockerignore",
    "editorconfig",
    "svg",
];

const TEXT_NAMES: &[&str] = &[
    "makefile",
    "dockerfile",
    "cmakelists.txt",
    "license",
    "readme",
    "changelog",
    "kconfig",
    "sdkconfig",
    "platformio.ini",
    "cargo.lock",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Text,
    Pdf,
    Docx,
}

impl Kind {
    pub fn as_str(self) -> &'static str {
        match self {
            Kind::Text => "text",
            Kind::Pdf => "pdf",
            Kind::Docx => "docx",
        }
    }
    pub fn mime(self) -> &'static str {
        match self {
            Kind::Text => "text/plain",
            Kind::Pdf => "application/pdf",
            Kind::Docx => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    }
}

/// Arquivos com segredos prováveis nunca são indexados, lidos nem editados.
pub fn is_secret(name: &str) -> bool {
    let lower = name.to_lowercase();
    if lower.starts_with(".env") {
        return ![".example", ".sample", ".template"]
            .iter()
            .any(|s| lower.ends_with(s));
    }
    [".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx"]
        .iter()
        .any(|s| lower.ends_with(s))
        || ["id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"]
            .iter()
            .any(|p| lower.starts_with(p))
        || lower.contains("secret")
        || lower.contains("credential")
        || lower == ".npmrc"
        || lower == ".pypirc"
        || lower == ".netrc"
}

pub fn is_ignored_dir(name: &str) -> bool {
    IGNORED_DIRS.contains(&name.to_lowercase().as_str())
}

pub fn classify(path: &Path) -> Option<Kind> {
    let name = path.file_name()?.to_str()?;
    if is_secret(name) {
        return None;
    }
    let lower = name.to_lowercase();
    if TEXT_NAMES.contains(&lower.as_str()) {
        return Some(Kind::Text);
    }
    let ext = lower.rsplit_once('.').map(|(_, e)| e).unwrap_or("");
    match ext {
        "pdf" => Some(Kind::Pdf),
        "docx" => Some(Kind::Docx),
        e if TEXT_EXTENSIONS.contains(&e) => Some(Kind::Text),
        _ => None,
    }
}

#[derive(Debug, Clone)]
pub struct ScannedFile {
    pub rel_path: String,
    pub abs: PathBuf,
    pub size: u64,
    pub mtime: i64,
    pub kind: Kind,
}

#[derive(Debug, Default)]
pub struct Scan {
    pub files: Vec<ScannedFile>,
    pub skipped: usize,
    pub truncated: bool,
}

fn rel_string(root: &Path, path: &Path) -> Option<String> {
    let rel = path.strip_prefix(root).ok()?;
    let parts = rel
        .components()
        .map(|c| c.as_os_str().to_str().map(str::to_string))
        .collect::<Option<Vec<_>>>()?;
    Some(parts.join("/"))
}

/// Percorre a pasta sem seguir links simbólicos, ignorando diretórios de build/dependências.
pub fn scan(root: &Path) -> std::io::Result<Scan> {
    let mut result = Scan::default();
    let mut stack = vec![(root.to_path_buf(), 0usize)];
    while let Some((dir, depth)) = stack.pop() {
        let mut entries = match fs::read_dir(&dir) {
            Ok(e) => e.filter_map(|e| e.ok()).collect::<Vec<_>>(),
            Err(e) if dir == root => return Err(e),
            Err(_) => {
                result.skipped += 1;
                continue;
            }
        };
        entries.sort_by_key(|e| e.file_name());
        for entry in entries {
            let path = entry.path();
            let Ok(meta) = fs::symlink_metadata(&path) else {
                result.skipped += 1;
                continue;
            };
            let name = entry.file_name().to_string_lossy().to_string();
            if meta.file_type().is_symlink() {
                result.skipped += 1;
            } else if meta.is_dir() {
                if is_ignored_dir(&name) || depth + 1 > MAX_DEPTH {
                    continue;
                }
                stack.push((path, depth + 1));
            } else if meta.is_file() {
                let Some(kind) = classify(&path) else {
                    result.skipped += 1;
                    continue;
                };
                if result.files.len() >= MAX_FILES {
                    result.truncated = true;
                    continue;
                }
                let Some(rel_path) = rel_string(root, &path) else {
                    result.skipped += 1;
                    continue;
                };
                let mtime = meta
                    .modified()
                    .ok()
                    .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                    .map(|d| d.as_secs() as i64)
                    .unwrap_or(0);
                result.files.push(ScannedFile {
                    rel_path,
                    abs: path,
                    size: meta.len(),
                    mtime,
                    kind,
                });
            }
        }
    }
    result.files.sort_by(|a, b| a.rel_path.cmp(&b.rel_path));
    Ok(result)
}

/// Resolve um caminho relativo dentro da raiz, recusando `..`, caminhos absolutos, links
/// simbólicos e qualquer resolução que escape da pasta vinculada.
pub fn safe_join(root: &Path, rel: &str) -> Result<PathBuf, String> {
    let rel = rel.trim().replace('\\', "/");
    if rel.is_empty() || rel.len() > 400 || rel.contains('\0') {
        return Err("Caminho inválido.".into());
    }
    let mut joined = root.to_path_buf();
    for component in Path::new(&rel).components() {
        match component {
            Component::Normal(part) => joined.push(part),
            Component::CurDir => {}
            _ => return Err("O caminho precisa ficar dentro da pasta vinculada.".into()),
        }
    }
    if joined == root {
        return Err("Caminho inválido.".into());
    }
    let canonical_root = root
        .canonicalize()
        .map_err(|_| "A pasta vinculada não está acessível.".to_string())?;
    let mut probe = joined.as_path();
    loop {
        if let Ok(meta) = fs::symlink_metadata(probe) {
            if meta.file_type().is_symlink() {
                return Err("Links simbólicos não são seguidos.".into());
            }
            let canonical = probe
                .canonicalize()
                .map_err(|_| "Caminho inacessível.".to_string())?;
            if !canonical.starts_with(&canonical_root) {
                return Err("O caminho precisa ficar dentro da pasta vinculada.".into());
            }
            break;
        }
        probe = probe
            .parent()
            .ok_or_else(|| "Caminho inválido.".to_string())?;
    }
    Ok(joined)
}

/// Caminhos em que o modelo nunca pode gravar, mesmo com aprovação.
pub fn write_blocked(rel: &str) -> Option<&'static str> {
    let normalized = rel.replace('\\', "/");
    let parts: Vec<&str> = normalized.split('/').filter(|p| !p.is_empty()).collect();
    if parts.iter().any(|p| is_ignored_dir(p)) {
        return Some("Diretórios de controle de versão, dependências e build não são editáveis.");
    }
    if parts.last().is_some_and(|n| is_secret(n)) {
        return Some("Arquivos de credenciais não são editáveis pelo SOLARIS.");
    }
    if parts.last().is_some_and(|n| {
        let lower = n.to_lowercase();
        [
            ".exe", ".dll", ".msi", ".bat", ".cmd", ".ps1", ".sys", ".lnk",
        ]
        .iter()
        .any(|s| lower.ends_with(s))
    }) {
        return Some("Executáveis e scripts do Windows não são gravados por propostas do chat.");
    }
    None
}

pub fn read_text_file(path: &Path, max: u64) -> Result<String, String> {
    let meta = fs::metadata(path).map_err(|_| "Arquivo não encontrado.".to_string())?;
    if meta.len() > max {
        return Err(format!(
            "Arquivo com {:.1} MB excede o limite de {:.1} MB.",
            meta.len() as f64 / 1e6,
            max as f64 / 1e6
        ));
    }
    let bytes = fs::read(path).map_err(|e| format!("Falha ao ler arquivo: {e}"))?;
    if bytes.iter().take(8192).any(|b| *b == 0) {
        return Err("Arquivo binário.".into());
    }
    let text = String::from_utf8(bytes).map_err(|_| "Arquivo não está em UTF-8.".to_string())?;
    Ok(text.strip_prefix('\u{feff}').unwrap_or(&text).to_string())
}

pub fn base64_encode(bytes: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let n = (chunk[0] as u32) << 16
            | (*chunk.get(1).unwrap_or(&0) as u32) << 8
            | *chunk.get(2).unwrap_or(&0) as u32;
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 {
            T[(n >> 6) as usize & 63] as char
        } else {
            '='
        });
        out.push(if chunk.len() > 2 {
            T[n as usize & 63] as char
        } else {
            '='
        });
    }
    out
}

// ── Propostas de edição no texto do modelo ──────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EditBlock {
    pub folder_id: Option<i64>,
    pub path: String,
    pub content: String,
}

fn attribute(tag: &str, names: &[&str]) -> Option<String> {
    for name in names {
        for quote in ['"', '\''] {
            let key = format!("{name}={quote}");
            if let Some(start) = tag.find(&key) {
                let rest = &tag[start + key.len()..];
                if let Some(end) = rest.find(quote) {
                    return Some(rest[..end].to_string());
                }
            }
        }
    }
    None
}

/// Remove blocos `<solaris_edit pasta="1" caminho="src/main.c">…</solaris_edit>` da resposta,
/// devolvendo o texto visível com um aviso no lugar de cada bloco.
pub fn extract_edits(reply: &str) -> (String, Vec<EditBlock>) {
    const OPEN: &str = "<solaris_edit";
    const CLOSE: &str = "</solaris_edit>";
    let mut visible = String::new();
    let mut blocks = Vec::new();
    let mut rest = reply;
    while let Some(start) = rest.find(OPEN) {
        let after = &rest[start..];
        let (Some(tag_end), Some(close)) = (after.find('>'), after.find(CLOSE)) else {
            break;
        };
        if tag_end > close {
            break;
        }
        let tag = &after[..tag_end];
        let mut content = &after[tag_end + 1..close];
        content = content
            .strip_prefix("\r\n")
            .or_else(|| content.strip_prefix('\n'))
            .unwrap_or(content);
        visible.push_str(&rest[..start]);
        let path = attribute(tag, &["caminho", "path"]).unwrap_or_default();
        if blocks.len() < MAX_EDITS_PER_REPLY && !path.trim().is_empty() {
            visible.push_str(&format!(
                "\n\n> Edição proposta para `{}` — revise e aprove antes da gravação.\n\n",
                path.trim()
            ));
            blocks.push(EditBlock {
                folder_id: attribute(tag, &["pasta", "folder"]).and_then(|v| v.trim().parse().ok()),
                path: path.trim().to_string(),
                content: content.to_string(),
            });
        } else {
            visible.push_str("\n\n> Proposta de edição descartada (sem caminho ou acima do limite de 10 por resposta).\n\n");
        }
        rest = &after[close + CLOSE.len()..];
    }
    visible.push_str(rest);
    (visible.trim().to_string(), blocks)
}

/// Extrai menções `@caminho/arquivo.ext` da mensagem do usuário.
pub fn mentions(message: &str) -> Vec<String> {
    let mut found: Vec<String> = Vec::new();
    // Caminhos com espaços: @"pasta/meu arquivo.md"
    let mut rest = message;
    while let Some(start) = rest.find("@\"") {
        let after = &rest[start + 2..];
        let Some(end) = after.find('"') else { break };
        let path = after[..end].trim().replace('\\', "/");
        if path.len() > 1 && !found.contains(&path) {
            found.push(path);
        }
        rest = &after[end + 1..];
    }
    for word in message.split_whitespace() {
        if let Some(raw) = word.strip_prefix('@').filter(|r| !r.starts_with('"')) {
            let path = raw
                .trim_matches(|c: char| {
                    matches!(
                        c,
                        ',' | ';' | ':' | '?' | '!' | ')' | '(' | '"' | '\'' | '`'
                    )
                })
                .trim_end_matches('.');
            if path.len() > 1 && !found.iter().any(|f| f == path) && !path.contains('"') {
                found.push(path.replace('\\', "/"));
            }
        }
        if found.len() >= 8 {
            break;
        }
    }
    found
}

/// Mantém o estilo de quebra de linha do arquivo original.
pub fn match_line_endings(original: Option<&str>, proposed: &str) -> String {
    let normalized = proposed.replace("\r\n", "\n");
    if original.is_some_and(|o| o.contains("\r\n")) {
        normalized.replace('\n', "\r\n")
    } else {
        normalized
    }
}

/// Grava a proposta aprovada: confere conflito, guarda cópia de segurança e grava de forma
/// atômica (arquivo temporário + rename) dentro da pasta vinculada.
pub fn write_checked(
    root: &Path,
    rel: &str,
    original: Option<&str>,
    proposed: &str,
    backup_dir: &Path,
) -> Result<PathBuf, String> {
    if let Some(reason) = write_blocked(rel) {
        return Err(reason.into());
    }
    let target = safe_join(root, rel)?;
    let current = if target.exists() {
        if !target.is_file() {
            return Err("O destino não é um arquivo.".into());
        }
        Some(read_text_file(&target, MAX_TEXT_BYTES)?)
    } else {
        None
    };
    match (original, current.as_deref()) {
        (None, Some(_)) => {
            return Err("O arquivo foi criado depois da proposta. Peça uma nova versão.".into())
        }
        (Some(_), None) => {
            return Err("O arquivo foi removido ou movido depois da proposta.".into())
        }
        (Some(a), Some(b)) if a != b => return Err(
            "O arquivo mudou no disco depois da proposta. Nada foi gravado; peça uma nova versão."
                .into(),
        ),
        _ => {}
    }
    if let Some(current) = &current {
        fs::create_dir_all(backup_dir).map_err(|e| format!("Falha ao criar backup: {e}"))?;
        let name = target
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "arquivo".into());
        fs::write(backup_dir.join(format!("{name}.bak")), current)
            .map_err(|e| format!("Falha ao gravar backup: {e}"))?;
    }
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Falha ao criar diretório: {e}"))?;
    }
    let tmp = target.with_file_name(format!(
        ".{}.solaris-tmp",
        target
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default()
    ));
    fs::write(&tmp, proposed).map_err(|e| format!("Falha ao gravar: {e}"))?;
    if let Err(e) = fs::rename(&tmp, &target) {
        let _ = fs::remove_file(&tmp);
        return Err(format!("Falha ao substituir o arquivo: {e}"));
    }
    Ok(target)
}

// ── Persistência ────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct ProjectFolder {
    pub id: i64,
    pub project_id: i64,
    pub path: String,
    pub label: String,
    pub enabled: bool,
    pub file_count: i64,
    pub indexed_count: i64,
    pub skipped_count: i64,
    pub truncated: bool,
    pub last_indexed_at: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct FolderFile {
    pub folder_id: i64,
    pub rel_path: String,
    pub kind: String,
    pub byte_size: i64,
    pub indexed: bool,
    pub note: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct FolderEdit {
    pub id: i64,
    pub project_id: i64,
    pub folder_id: i64,
    pub folder_label: String,
    pub rel_path: String,
    pub original: Option<String>,
    pub proposed: String,
    pub status: String,
    pub detail: String,
    pub conversation_id: Option<i64>,
    pub message_id: Option<i64>,
    pub created_at: String,
    pub decided_at: Option<String>,
}

#[derive(Debug, Clone, Copy)]
pub struct KnownFile {
    pub size: i64,
    pub mtime: i64,
}

pub fn migrate(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS project_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            path TEXT NOT NULL, label TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            file_count INTEGER NOT NULL DEFAULT 0, indexed_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0, truncated INTEGER NOT NULL DEFAULT 0,
            last_indexed_at TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, path)
        );
        CREATE TABLE IF NOT EXISTS folder_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER NOT NULL REFERENCES project_folders(id) ON DELETE CASCADE,
            rel_path TEXT NOT NULL, kind TEXT NOT NULL, byte_size INTEGER NOT NULL,
            mtime INTEGER NOT NULL, indexed INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '',
            UNIQUE(folder_id, rel_path)
        );
        CREATE TABLE IF NOT EXISTS folder_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL REFERENCES folder_files(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL, rel_path TEXT NOT NULL, content TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS folder_chunks_file ON folder_chunks(file_id);
        CREATE VIRTUAL TABLE IF NOT EXISTS folder_fts USING fts5(rel_path, content, content='folder_chunks', content_rowid='id');
        CREATE TRIGGER IF NOT EXISTS folder_chunks_ai AFTER INSERT ON folder_chunks BEGIN
            INSERT INTO folder_fts(rowid,rel_path,content) VALUES(new.id,new.rel_path,new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS folder_chunks_ad AFTER DELETE ON folder_chunks BEGIN
            INSERT INTO folder_fts(folder_fts,rowid,rel_path,content) VALUES('delete',old.id,old.rel_path,old.content);
        END;
        CREATE TABLE IF NOT EXISTS folder_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            folder_id INTEGER NOT NULL REFERENCES project_folders(id) ON DELETE CASCADE,
            rel_path TEXT NOT NULL, original TEXT, proposed TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', detail TEXT NOT NULL DEFAULT '',
            conversation_id INTEGER, message_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), decided_at TEXT
        );
        CREATE INDEX IF NOT EXISTS folder_edits_project ON folder_edits(project_id, status);
    ",
    )
}

const FOLDER_COLUMNS: &str = "id,project_id,path,label,enabled,file_count,indexed_count,skipped_count,truncated,last_indexed_at,created_at";

fn folder_row(r: &rusqlite::Row) -> rusqlite::Result<ProjectFolder> {
    Ok(ProjectFolder {
        id: r.get(0)?,
        project_id: r.get(1)?,
        path: r.get(2)?,
        label: r.get(3)?,
        enabled: r.get(4)?,
        file_count: r.get(5)?,
        indexed_count: r.get(6)?,
        skipped_count: r.get(7)?,
        truncated: r.get(8)?,
        last_indexed_at: r.get(9)?,
        created_at: r.get(10)?,
    })
}

const EDIT_SELECT: &str = "SELECT e.id,e.project_id,e.folder_id,f.label,e.rel_path,e.original,e.proposed,e.status,e.detail,e.conversation_id,e.message_id,e.created_at,e.decided_at FROM folder_edits e JOIN project_folders f ON f.id=e.folder_id";

fn edit_row(r: &rusqlite::Row) -> rusqlite::Result<FolderEdit> {
    Ok(FolderEdit {
        id: r.get(0)?,
        project_id: r.get(1)?,
        folder_id: r.get(2)?,
        folder_label: r.get(3)?,
        rel_path: r.get(4)?,
        original: r.get(5)?,
        proposed: r.get(6)?,
        status: r.get(7)?,
        detail: r.get(8)?,
        conversation_id: r.get(9)?,
        message_id: r.get(10)?,
        created_at: r.get(11)?,
        decided_at: r.get(12)?,
    })
}

fn sql(e: rusqlite::Error) -> String {
    match e {
        rusqlite::Error::QueryReturnedNoRows => "Registro não encontrado neste projeto.".into(),
        other => other.to_string(),
    }
}

/// Recompõe o texto de um documento a partir dos trechos sobrepostos (1500 com passo 1300).
fn join_chunks(chunks: Vec<String>) -> String {
    let mut text = String::new();
    for (i, chunk) in chunks.into_iter().enumerate() {
        if i == 0 {
            text.push_str(&chunk);
        } else {
            text.extend(chunk.chars().skip(200));
        }
    }
    text
}

impl DbState {
    pub fn attach_folder(&self, project_id: i64, path: &Path) -> Result<ProjectFolder, String> {
        let canonical = path
            .canonicalize()
            .map_err(|_| "Pasta não encontrada ou sem permissão de leitura.".to_string())?;
        if !canonical.is_dir() {
            return Err("Selecione uma pasta, não um arquivo.".into());
        }
        if canonical.parent().is_none() {
            return Err("Vincule uma pasta de trabalho, não a raiz de uma unidade.".into());
        }
        let display = canonical.to_string_lossy().to_string();
        let display = display
            .strip_prefix(r"\\?\")
            .unwrap_or(&display)
            .to_string();
        let label = canonical
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| display.clone());
        let conn = self.0.lock().unwrap();
        conn.query_row("SELECT id FROM projects WHERE id=?1", [project_id], |_| {
            Ok(())
        })
        .map_err(|_| "Projeto não encontrado.".to_string())?;
        if let Some(existing) = conn
            .query_row(
                &format!(
                    "SELECT {FOLDER_COLUMNS} FROM project_folders WHERE project_id=?1 AND path=?2"
                ),
                params![project_id, display],
                folder_row,
            )
            .optional()
            .map_err(sql)?
        {
            return Ok(existing);
        }
        let count: i64 = conn
            .query_row(
                "SELECT count(*) FROM project_folders WHERE project_id=?1",
                [project_id],
                |r| r.get(0),
            )
            .map_err(sql)?;
        if count >= MAX_FOLDERS_PER_PROJECT {
            return Err(format!(
                "Cada projeto aceita até {MAX_FOLDERS_PER_PROJECT} pastas vinculadas."
            ));
        }
        conn.execute(
            "INSERT INTO project_folders(project_id,path,label) VALUES(?1,?2,?3)",
            params![project_id, display, label],
        )
        .map_err(sql)?;
        let id = conn.last_insert_rowid();
        conn.query_row(
            &format!("SELECT {FOLDER_COLUMNS} FROM project_folders WHERE id=?1"),
            [id],
            folder_row,
        )
        .map_err(sql)
    }

    pub fn list_folders(&self, project_id: i64) -> Result<Vec<ProjectFolder>, String> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn
            .prepare(&format!(
                "SELECT {FOLDER_COLUMNS} FROM project_folders WHERE project_id=?1 ORDER BY id"
            ))
            .map_err(sql)?;
        let rows = stmt.query_map([project_id], folder_row).map_err(sql)?;
        rows.collect::<rusqlite::Result<Vec<_>>>().map_err(sql)
    }

    pub fn folder(&self, project_id: i64, folder_id: i64) -> Result<ProjectFolder, String> {
        self.0
            .lock()
            .unwrap()
            .query_row(
                &format!(
                    "SELECT {FOLDER_COLUMNS} FROM project_folders WHERE id=?1 AND project_id=?2"
                ),
                params![folder_id, project_id],
                folder_row,
            )
            .map_err(sql)
    }

    pub fn detach_folder(&self, project_id: i64, folder_id: i64) -> Result<(), String> {
        let changed = self
            .0
            .lock()
            .unwrap()
            .execute(
                "DELETE FROM project_folders WHERE id=?1 AND project_id=?2",
                params![folder_id, project_id],
            )
            .map_err(sql)?;
        if changed == 0 {
            return Err("Pasta não encontrada neste projeto.".into());
        }
        Ok(())
    }

    pub fn set_folder_enabled(
        &self,
        project_id: i64,
        folder_id: i64,
        enabled: bool,
    ) -> Result<(), String> {
        let changed = self
            .0
            .lock()
            .unwrap()
            .execute(
                "UPDATE project_folders SET enabled=?3 WHERE id=?1 AND project_id=?2",
                params![folder_id, project_id, enabled],
            )
            .map_err(sql)?;
        if changed == 0 {
            return Err("Pasta não encontrada neste projeto.".into());
        }
        Ok(())
    }

    pub fn folder_known_files(&self, folder_id: i64) -> Result<HashMap<String, KnownFile>, String> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn
            .prepare("SELECT rel_path,byte_size,mtime FROM folder_files WHERE folder_id=?1")
            .map_err(sql)?;
        let rows = stmt
            .query_map([folder_id], |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    KnownFile {
                        size: r.get(1)?,
                        mtime: r.get(2)?,
                    },
                ))
            })
            .map_err(sql)?;
        rows.collect::<rusqlite::Result<HashMap<_, _>>>()
            .map_err(sql)
    }

    /// Substitui o registro de um arquivo e seus trechos. `text = None` registra o arquivo
    /// como visível na listagem, porém sem conteúdo indexado (com o motivo em `note`).
    pub fn store_folder_file(
        &self,
        folder_id: i64,
        file: &ScannedFile,
        text: Option<&str>,
        note: &str,
    ) -> Result<(), String> {
        let conn = self.0.lock().unwrap();
        let tx = conn.unchecked_transaction().map_err(sql)?;
        tx.execute(
            "DELETE FROM folder_files WHERE folder_id=?1 AND rel_path=?2",
            params![folder_id, file.rel_path],
        )
        .map_err(sql)?;
        let text = text.map(|t| t.chars().take(MAX_INDEXED_CHARS).collect::<String>());
        let note = if text
            .as_ref()
            .is_some_and(|t| t.chars().count() >= MAX_INDEXED_CHARS)
        {
            "Indexado parcialmente (limite de 500 mil caracteres)."
        } else {
            note
        };
        tx.execute(
            "INSERT INTO folder_files(folder_id,rel_path,kind,byte_size,mtime,indexed,note) VALUES(?1,?2,?3,?4,?5,?6,?7)",
            params![folder_id, file.rel_path, file.kind.as_str(), file.size as i64, file.mtime, text.is_some(), note],
        )
        .map_err(sql)?;
        let file_id = tx.last_insert_rowid();
        if let Some(text) = text {
            let chars: Vec<char> = text.chars().collect();
            for (index, start) in (0..chars.len()).step_by(1300).enumerate() {
                let content: String = chars[start..(start + 1500).min(chars.len())]
                    .iter()
                    .collect();
                tx.execute(
                    "INSERT INTO folder_chunks(file_id,chunk_index,rel_path,content) VALUES(?1,?2,?3,?4)",
                    params![file_id, index as i64, file.rel_path, content],
                )
                .map_err(sql)?;
            }
        }
        tx.commit().map_err(sql)
    }

    pub fn remove_folder_files(&self, folder_id: i64, rel_paths: &[String]) -> Result<(), String> {
        let conn = self.0.lock().unwrap();
        let tx = conn.unchecked_transaction().map_err(sql)?;
        for rel in rel_paths {
            tx.execute(
                "DELETE FROM folder_files WHERE folder_id=?1 AND rel_path=?2",
                params![folder_id, rel],
            )
            .map_err(sql)?;
        }
        tx.commit().map_err(sql)
    }

    pub fn finish_folder_index(
        &self,
        folder_id: i64,
        skipped: usize,
        truncated: bool,
    ) -> Result<(), String> {
        self.0
            .lock()
            .unwrap()
            .execute(
                "UPDATE project_folders SET file_count=(SELECT count(*) FROM folder_files WHERE folder_id=?1),
                 indexed_count=(SELECT count(*) FROM folder_files WHERE folder_id=?1 AND indexed=1),
                 skipped_count=?2, truncated=?3, last_indexed_at=datetime('now') WHERE id=?1",
                params![folder_id, skipped as i64, truncated],
            )
            .map_err(sql)?;
        Ok(())
    }

    pub fn folder_files(
        &self,
        project_id: i64,
        folder_id: i64,
        filter: &str,
        limit: usize,
    ) -> Result<Vec<FolderFile>, String> {
        self.folder(project_id, folder_id)?;
        let conn = self.0.lock().unwrap();
        let pattern = format!(
            "%{}%",
            filter.trim().replace('\\', "/").replace(['%', '_'], "")
        );
        let mut stmt = conn
            .prepare("SELECT folder_id,rel_path,kind,byte_size,indexed,note FROM folder_files WHERE folder_id=?1 AND rel_path LIKE ?2 ORDER BY rel_path LIMIT ?3")
            .map_err(sql)?;
        let rows = stmt
            .query_map(params![folder_id, pattern, limit.min(2000) as i64], |r| {
                Ok(FolderFile {
                    folder_id: r.get(0)?,
                    rel_path: r.get(1)?,
                    kind: r.get(2)?,
                    byte_size: r.get(3)?,
                    indexed: r.get(4)?,
                    note: r.get(5)?,
                })
            })
            .map_err(sql)?;
        rows.collect::<rusqlite::Result<Vec<_>>>().map_err(sql)
    }

    fn indexed_text(&self, folder_id: i64, rel: &str) -> Result<Option<(String, String)>, String> {
        let conn = self.0.lock().unwrap();
        let Some((file_id, kind)) = conn
            .query_row(
                "SELECT id,kind FROM folder_files WHERE folder_id=?1 AND rel_path=?2",
                params![folder_id, rel],
                |r| Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?)),
            )
            .optional()
            .map_err(sql)?
        else {
            return Ok(None);
        };
        let mut stmt = conn
            .prepare("SELECT content FROM folder_chunks WHERE file_id=?1 ORDER BY chunk_index")
            .map_err(sql)?;
        let chunks = stmt
            .query_map([file_id], |r| r.get::<_, String>(0))
            .map_err(sql)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(sql)?;
        Ok(Some((kind, join_chunks(chunks))))
    }

    /// Lê o conteúdo atual de um arquivo da pasta: texto direto do disco; PDF/DOCX a partir
    /// do texto extraído na indexação.
    pub fn folder_read(
        &self,
        project_id: i64,
        folder_id: i64,
        rel: &str,
    ) -> Result<String, String> {
        let folder = self.folder(project_id, folder_id)?;
        let name = rel.rsplit('/').next().unwrap_or(rel);
        if is_secret(name) {
            return Err("Arquivos de credenciais não são lidos pelo SOLARIS.".into());
        }
        let path = safe_join(Path::new(&folder.path), rel)?;
        match classify(&path) {
            Some(Kind::Text) => read_text_file(&path, MAX_TEXT_BYTES),
            Some(_) => self
                .indexed_text(folder_id, rel)?
                .map(|(_, text)| text)
                .filter(|t| !t.is_empty())
                .ok_or_else(|| "Documento ainda não indexado. Reindexe a pasta.".into()),
            None => Err("Formato não suportado para leitura.".into()),
        }
    }

    /// Resumo das pastas para o prompt de sistema: identificador, nome e parte da árvore.
    pub fn folder_overview(&self, project_id: Option<i64>) -> Result<String, String> {
        let Some(project_id) = project_id else {
            return Ok(String::new());
        };
        let folders: Vec<ProjectFolder> = self
            .list_folders(project_id)?
            .into_iter()
            .filter(|f| f.enabled)
            .collect();
        if folders.is_empty() {
            return Ok(String::new());
        }
        let mut text = String::from(
            "Pastas locais vinculadas a este projeto (somente as listadas são acessíveis):\n",
        );
        let per_folder = (OVERVIEW_PATHS / folders.len()).max(20);
        for folder in &folders {
            let files = self.folder_files(project_id, folder.id, "", per_folder + 1)?;
            text.push_str(&format!(
                "- pasta={} «{}»: {} arquivos listados, {} com conteúdo indexado{}.\n",
                folder.id,
                folder.label,
                folder.file_count,
                folder.indexed_count,
                if folder.truncated {
                    ", lista truncada"
                } else {
                    ""
                }
            ));
            for file in files.iter().take(per_folder) {
                text.push_str(&format!("  {}\n", file.rel_path));
            }
            if files.len() > per_folder {
                text.push_str("  …\n");
            }
        }
        Ok(text)
    }

    /// Contexto das pastas: arquivos mencionados com `@caminho` entram inteiros (com limite)
    /// e, se `search` estiver ativo, trechos relevantes por FTS5 completam o orçamento.
    pub fn folder_context(
        &self,
        project_id: Option<i64>,
        query: &str,
        mentioned: &[String],
        search: bool,
    ) -> Result<Vec<ContextSource>, String> {
        let Some(project_id) = project_id else {
            return Ok(Vec::new());
        };
        let folders: Vec<ProjectFolder> = self
            .list_folders(project_id)?
            .into_iter()
            .filter(|f| f.enabled)
            .collect();
        if folders.is_empty() {
            return Ok(Vec::new());
        }
        let mut result = Vec::new();
        let mut included: HashSet<(i64, String)> = HashSet::new();
        let mut budget = MENTION_BUDGET;
        for mention in mentioned {
            let mention = mention.trim_start_matches("./");
            let hit = {
                let conn = self.0.lock().unwrap();
                let mut found = None;
                for folder in &folders {
                    found = conn
                        .query_row(
                            "SELECT rel_path FROM folder_files WHERE folder_id=?1 AND (rel_path=?2 OR rel_path LIKE ?3) ORDER BY length(rel_path) LIMIT 1",
                            params![folder.id, mention, format!("%/{}", mention.replace(['%', '_'], ""))],
                            |r| r.get::<_, String>(0),
                        )
                        .optional()
                        .map_err(sql)?
                        .map(|rel| (folder.clone(), rel));
                    if found.is_some() {
                        break;
                    }
                }
                found
            };
            let Some((folder, rel)) = hit else { continue };
            if budget == 0 || !included.insert((folder.id, rel.clone())) {
                continue;
            }
            let content = match self.folder_read(project_id, folder.id, &rel) {
                Ok(text) => text,
                Err(e) => format!("[Não foi possível ler: {e}]"),
            };
            let total = content.chars().count();
            let content: String = content.chars().take(budget).collect();
            budget -= content.chars().count();
            result.push(ContextSource {
                kind: "folder".into(),
                document_id: Some(folder.id),
                filename: format!("{}/{}", folder.label, rel),
                citation: format!(
                    "pasta:{}:{}{}",
                    folder.id,
                    rel,
                    if total > content.chars().count() {
                        " (truncado)"
                    } else {
                        " (arquivo completo)"
                    }
                ),
                content,
            });
        }
        let query = search_query(query);
        if !search || query.is_empty() {
            return Ok(result);
        }
        let conn = self.0.lock().unwrap();
        let mut stmt = conn
            .prepare(
                "SELECT p.id,p.label,c.rel_path,c.chunk_index,c.content FROM folder_fts
                 JOIN folder_chunks c ON c.id=folder_fts.rowid
                 JOIN folder_files f ON f.id=c.file_id
                 JOIN project_folders p ON p.id=f.folder_id
                 WHERE p.project_id=?1 AND p.enabled=1 AND folder_fts MATCH ?2
                 ORDER BY rank LIMIT 24",
            )
            .map_err(sql)?;
        let rows = stmt
            .query_map(params![project_id, query], |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, i64>(3)?,
                    r.get::<_, String>(4)?,
                ))
            })
            .map_err(sql)?;
        let mut remaining = SEARCH_BUDGET;
        for row in rows {
            let (folder_id, label, rel, chunk, content) = row.map_err(sql)?;
            if remaining == 0 {
                break;
            }
            if included.contains(&(folder_id, rel.clone())) {
                continue;
            }
            let content: String = content.chars().take(remaining).collect();
            remaining -= content.chars().count();
            result.push(ContextSource {
                kind: "folder".into(),
                document_id: Some(folder_id),
                filename: format!("{label}/{rel}"),
                citation: format!("pasta:{folder_id}:{rel}:{}", chunk + 1),
                content,
            });
        }
        Ok(result)
    }

    /// Registra propostas do modelo como pendentes. Nada é gravado em disco aqui.
    pub fn propose_edits(
        &self,
        project_id: Option<i64>,
        conversation_id: i64,
        message_id: i64,
        blocks: &[EditBlock],
    ) -> (Vec<FolderEdit>, Vec<String>) {
        let mut edits = Vec::new();
        let mut errors = Vec::new();
        let Some(project_id) = project_id else {
            if !blocks.is_empty() {
                errors.push("Conversas sem projeto não têm pastas vinculadas.".into());
            }
            return (edits, errors);
        };
        let folders = match self.list_folders(project_id) {
            Ok(f) => f.into_iter().filter(|f| f.enabled).collect::<Vec<_>>(),
            Err(e) => return (edits, vec![e]),
        };
        for block in blocks {
            let folder = match block.folder_id {
                Some(id) => folders.iter().find(|f| f.id == id),
                None if folders.len() == 1 => folders.first(),
                None => None,
            };
            let Some(folder) = folder else {
                errors.push(format!(
                    "{}: pasta não identificada ou não vinculada.",
                    block.path
                ));
                continue;
            };
            let outcome = (|| -> Result<FolderEdit, String> {
                if block.content.len() > MAX_EDIT_BYTES {
                    return Err("conteúdo acima de 1 MB.".into());
                }
                if let Some(reason) = write_blocked(&block.path) {
                    return Err(reason.into());
                }
                let root = Path::new(&folder.path);
                let target = safe_join(root, &block.path)?;
                let rel = rel_string(root, &target).unwrap_or_else(|| block.path.clone());
                let original = if target.exists() {
                    Some(read_text_file(&target, MAX_TEXT_BYTES)?)
                } else {
                    None
                };
                if original.as_deref() == Some(block.content.as_str()) {
                    return Err("proposta idêntica ao arquivo atual.".into());
                }
                let proposed = match_line_endings(original.as_deref(), &block.content);
                let conn = self.0.lock().unwrap();
                conn.execute(
                    "UPDATE folder_edits SET status='superseded',decided_at=datetime('now'),detail='Substituída por proposta mais recente.' WHERE folder_id=?1 AND rel_path=?2 AND status='pending'",
                    params![folder.id, rel],
                )
                .map_err(sql)?;
                conn.execute(
                    "INSERT INTO folder_edits(project_id,folder_id,rel_path,original,proposed,conversation_id,message_id) VALUES(?1,?2,?3,?4,?5,?6,?7)",
                    params![project_id, folder.id, rel, original, proposed, conversation_id, message_id],
                )
                .map_err(sql)?;
                let id = conn.last_insert_rowid();
                conn.query_row(&format!("{EDIT_SELECT} WHERE e.id=?1"), [id], edit_row)
                    .map_err(sql)
            })();
            match outcome {
                Ok(edit) => edits.push(edit),
                Err(e) => errors.push(format!("{}: {e}", block.path)),
            }
        }
        (edits, errors)
    }

    pub fn list_edits(
        &self,
        project_id: i64,
        status: Option<&str>,
    ) -> Result<Vec<FolderEdit>, String> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn
            .prepare(&format!(
                "{EDIT_SELECT} WHERE e.project_id=?1 AND (?2 IS NULL OR e.status=?2) ORDER BY e.id DESC LIMIT 50"
            ))
            .map_err(sql)?;
        let rows = stmt
            .query_map(params![project_id, status], edit_row)
            .map_err(sql)?;
        rows.collect::<rusqlite::Result<Vec<_>>>().map_err(sql)
    }

    pub fn get_edit(&self, project_id: i64, id: i64) -> Result<FolderEdit, String> {
        self.0
            .lock()
            .unwrap()
            .query_row(
                &format!("{EDIT_SELECT} WHERE e.id=?1 AND e.project_id=?2"),
                params![id, project_id],
                edit_row,
            )
            .map_err(sql)
    }

    pub fn mark_edit(&self, id: i64, status: &str, detail: &str) -> Result<(), String> {
        self.0
            .lock()
            .unwrap()
            .execute(
                "UPDATE folder_edits SET status=?2,detail=?3,decided_at=datetime('now') WHERE id=?1",
                params![id, status, detail],
            )
            .map_err(sql)?;
        Ok(())
    }

    pub fn replace_message_content(&self, message_id: i64, content: &str) -> Result<(), String> {
        self.0
            .lock()
            .unwrap()
            .execute(
                "UPDATE messages SET content=?2 WHERE id=?1",
                params![message_id, content],
            )
            .map_err(sql)?;
        Ok(())
    }
}

/// Aplica (ou recusa) uma proposta pendente. A aprovação é sempre uma ação explícita do
/// usuário na interface; a resposta do modelo nunca grava diretamente.
pub fn decide_edit(
    db: &DbState,
    project_id: i64,
    edit_id: i64,
    approve: bool,
    backup_root: &Path,
) -> Result<FolderEdit, String> {
    let edit = db.get_edit(project_id, edit_id)?;
    if edit.status != "pending" {
        return Err("Esta proposta já foi decidida.".into());
    }
    if !approve {
        db.mark_edit(edit_id, "rejected", "Recusada pelo usuário.")?;
        return db.get_edit(project_id, edit_id);
    }
    let folder = db.folder(project_id, edit.folder_id)?;
    let root = Path::new(&folder.path);
    match write_checked(
        root,
        &edit.rel_path,
        edit.original.as_deref(),
        &edit.proposed,
        &backup_root.join(format!("edit-{edit_id}")),
    ) {
        Ok(target) => {
            db.mark_edit(
                edit_id,
                "applied",
                if edit.original.is_some() {
                    "Gravado; a versão anterior foi copiada para o backup local."
                } else {
                    "Arquivo criado na pasta vinculada."
                },
            )?;
            if let (Ok(meta), Some(kind)) = (fs::metadata(&target), classify(&target)) {
                let file = ScannedFile {
                    rel_path: edit.rel_path.clone(),
                    abs: target.clone(),
                    size: meta.len(),
                    mtime: meta
                        .modified()
                        .ok()
                        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                        .map(|d| d.as_secs() as i64)
                        .unwrap_or(0),
                    kind,
                };
                if kind == Kind::Text {
                    let _ = db.store_folder_file(folder.id, &file, Some(&edit.proposed), "");
                    let _ = db.finish_folder_index(
                        folder.id,
                        folder.skipped_count as usize,
                        folder.truncated,
                    );
                }
            }
        }
        Err(reason) => {
            let status = if reason.contains("mudou")
                || reason.contains("criado depois")
                || reason.contains("removido")
            {
                "conflict"
            } else {
                "failed"
            };
            db.mark_edit(edit_id, status, &reason)?;
        }
    }
    db.get_edit(project_id, edit_id)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    fn tmp(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "solaris-ws-{name}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn db() -> DbState {
        let c = Connection::open_in_memory().unwrap();
        c.execute_batch("PRAGMA foreign_keys=ON;CREATE TABLE projects(id INTEGER PRIMARY KEY,instructions TEXT DEFAULT '',pinned INTEGER DEFAULT 0,updated_at TEXT);CREATE TABLE messages(id INTEGER PRIMARY KEY, content TEXT);INSERT INTO projects(id) VALUES (1),(2);").unwrap();
        crate::knowledge::migrate(&c).unwrap();
        migrate(&c).unwrap();
        migrate(&c).unwrap();
        DbState(Mutex::new(c))
    }

    fn sample_tree() -> PathBuf {
        let root = tmp("tree");
        fs::create_dir_all(root.join("src")).unwrap();
        fs::create_dir_all(root.join("node_modules/pkg")).unwrap();
        fs::create_dir_all(root.join(".git")).unwrap();
        fs::write(
            root.join("src/main.c"),
            "int main(){ /* motor PWM ESP32 */ return 0; }\n",
        )
        .unwrap();
        fs::write(
            root.join("README.md"),
            "# Robô\nControle PID do robô seguidor de linha.\n",
        )
        .unwrap();
        fs::write(root.join(".env"), "API_KEY=sk-segredo").unwrap();
        fs::write(root.join("node_modules/pkg/index.js"), "x").unwrap();
        fs::write(root.join(".git/config"), "x").unwrap();
        fs::write(root.join("foto.png"), [0u8, 1, 2]).unwrap();
        root
    }

    #[test]
    fn scan_skips_secrets_dependencies_and_binaries() {
        let root = sample_tree();
        let scan = scan(&root).unwrap();
        let paths: Vec<_> = scan.files.iter().map(|f| f.rel_path.as_str()).collect();
        assert_eq!(paths, vec!["README.md", "src/main.c"]);
        assert!(scan.skipped >= 2);
    }

    #[test]
    fn safe_join_rejects_escapes() {
        let root = sample_tree();
        assert!(safe_join(&root, "../fora.txt").is_err());
        assert!(safe_join(&root, "src/../../fora.txt").is_err());
        assert!(safe_join(&root, "/etc/passwd").is_err());
        assert!(safe_join(&root, "").is_err());
        assert!(safe_join(&root, "src/novo/arquivo.rs").is_ok());
        assert!(safe_join(&root, "src\\main.c").is_ok());
        #[cfg(unix)]
        {
            let outside = tmp("outside");
            std::os::unix::fs::symlink(&outside, root.join("link")).unwrap();
            assert!(safe_join(&root, "link/x.txt").is_err());
        }
        assert!(write_blocked(".git/config").is_some());
        assert!(write_blocked("config/.env.local").is_some());
        assert!(write_blocked("tools/run.ps1").is_some());
        assert!(write_blocked("src/main.c").is_none());
    }

    #[test]
    fn edits_are_extracted_and_hidden_from_visible_text() {
        let reply = "Segue a correção.\n<solaris_edit pasta=\"3\" caminho=\"src/main.c\">\nint main(){return 1;}\n</solaris_edit>\nFim.";
        let (visible, blocks) = extract_edits(reply);
        assert_eq!(
            blocks,
            vec![EditBlock {
                folder_id: Some(3),
                path: "src/main.c".into(),
                content: "int main(){return 1;}\n".into()
            }]
        );
        assert!(!visible.contains("solaris_edit"));
        assert!(visible.contains("src/main.c") && visible.ends_with("Fim."));
        let (same, none) = extract_edits("<solaris_edit caminho=\"a\">sem fechamento");
        assert!(none.is_empty() && same.contains("sem fechamento"));
        assert_eq!(
            mentions("analise @src/main.c, e @README.md?"),
            vec!["src/main.c", "README.md"]
        );
        assert_eq!(
            mentions("veja @\"docs/meu arquivo.md\" e @a.c"),
            vec!["docs/meu arquivo.md", "a.c"]
        );
    }

    #[test]
    fn index_context_and_approved_edit_roundtrip() {
        let db = db();
        let root = sample_tree();
        let folder = db.attach_folder(1, &root).unwrap();
        assert_eq!(db.attach_folder(1, &root).unwrap().id, folder.id);
        let scan = scan(&root).unwrap();
        for file in &scan.files {
            let text = read_text_file(&file.abs, MAX_TEXT_BYTES).unwrap();
            db.store_folder_file(folder.id, file, Some(&text), "")
                .unwrap();
        }
        db.finish_folder_index(folder.id, scan.skipped, scan.truncated)
            .unwrap();
        assert_eq!(db.folder(1, folder.id).unwrap().indexed_count, 2);
        assert!(db.folder(2, folder.id).is_err());

        let hits = db
            .folder_context(Some(1), "controle PID seguidor", &[], true)
            .unwrap();
        assert!(hits.iter().any(|h| h.filename.ends_with("README.md")));
        assert!(db
            .folder_context(Some(2), "controle PID", &[], true)
            .unwrap()
            .is_empty());
        let mentioned = db
            .folder_context(Some(1), "", &["main.c".into()], false)
            .unwrap();
        assert_eq!(mentioned.len(), 1);
        assert!(mentioned[0].content.contains("motor PWM"));
        assert!(db.folder_overview(Some(1)).unwrap().contains("src/main.c"));

        let (_, blocks) = extract_edits(&format!(
            "<solaris_edit caminho=\"src/main.c\">int main(){{ return 1; }}\n</solaris_edit><solaris_edit caminho=\"../x\">y</solaris_edit><solaris_edit pasta=\"{}\" caminho=\".env\">z</solaris_edit>",
            folder.id
        ));
        let (edits, errors) = db.propose_edits(Some(1), 1, 1, &blocks);
        assert_eq!(edits.len(), 1);
        assert_eq!(errors.len(), 2);
        assert!(fs::read_to_string(root.join("src/main.c"))
            .unwrap()
            .contains("return 0"));

        let backups = tmp("backup");
        assert!(decide_edit(&db, 2, edits[0].id, true, &backups).is_err());
        let applied = decide_edit(&db, 1, edits[0].id, true, &backups).unwrap();
        assert_eq!(applied.status, "applied");
        assert!(fs::read_to_string(root.join("src/main.c"))
            .unwrap()
            .contains("return 1"));
        assert!(
            fs::read_to_string(backups.join(format!("edit-{}/main.c.bak", edits[0].id)))
                .unwrap()
                .contains("return 0")
        );
        assert!(decide_edit(&db, 1, edits[0].id, true, &backups).is_err());

        // Conflito: o arquivo muda no disco depois da proposta.
        let (_, blocks) =
            extract_edits("<solaris_edit caminho=\"README.md\"># Novo\n</solaris_edit>");
        let (edits, _) = db.propose_edits(Some(1), 1, 2, &blocks);
        fs::write(root.join("README.md"), "editado à mão").unwrap();
        let conflict = decide_edit(&db, 1, edits[0].id, true, &backups).unwrap();
        assert_eq!(conflict.status, "conflict");
        assert_eq!(
            fs::read_to_string(root.join("README.md")).unwrap(),
            "editado à mão"
        );

        // Arquivo novo e recusa.
        let (_, blocks) =
            extract_edits("<solaris_edit caminho=\"docs/notas.md\">ok\n</solaris_edit>");
        let (edits, _) = db.propose_edits(Some(1), 1, 3, &blocks);
        assert!(edits[0].original.is_none());
        let rejected = decide_edit(&db, 1, edits[0].id, false, &backups).unwrap();
        assert_eq!(rejected.status, "rejected");
        assert!(!root.join("docs/notas.md").exists());

        db.detach_folder(1, folder.id).unwrap();
        assert!(db.list_folders(1).unwrap().is_empty());
        assert!(root.join("src/main.c").exists());
    }

    #[test]
    fn crlf_and_base64_helpers() {
        assert_eq!(match_line_endings(Some("a\r\nb"), "x\ny\n"), "x\r\ny\r\n");
        assert_eq!(match_line_endings(None, "x\r\ny"), "x\ny");
        assert_eq!(base64_encode(b"Man"), "TWFu");
        assert_eq!(base64_encode(b"Ma"), "TWE=");
        assert_eq!(base64_encode(b"M"), "TQ==");
    }
}
