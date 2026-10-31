/// SQLite database — managed by Rust via rusqlite (bundled, zero installation).
use rusqlite::{params, Connection, Result};
use serde::{Deserialize, Serialize};
use std::sync::Mutex;

pub struct DbState(pub Mutex<Connection>);

fn validate_project(conn: &Connection, project_id: Option<i64>) -> Result<()> {
    if let Some(id) = project_id {
        conn.query_row("SELECT id FROM projects WHERE id=?1", [id], |_| Ok(()))?;
    }
    Ok(())
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Conversation {
    pub id: i64,
    pub title: String,
    pub project_id: Option<i64>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct MemorySnippet {
    pub conversation_id: i64,
    pub title: String,
    pub content: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn database() -> DbState {
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch("PRAGMA foreign_keys=ON").unwrap();
        migrate(&conn).unwrap();
        DbState(Mutex::new(conn))
    }

    #[test]
    fn memory_isolated_by_project_and_follows_moved_conversation() {
        let db = database();
        let a = db.create_project("A", None).unwrap();
        let b = db.create_project("B", None).unwrap();
        let old = db.create_conversation("Antiga", Some(a)).unwrap();
        let current = db.create_conversation("Atual", Some(a)).unwrap();
        let other = db.create_conversation("Outro", Some(b)).unwrap();
        let loose = db.create_conversation("Solta", None).unwrap();
        for id in [old, current, other, loose] {
            db.add_message(id, "user", "calibração importante", None, None, None)
                .unwrap();
        }
        assert_eq!(db.fts_search("calibracao", current, 3).unwrap().len(), 1);
        db.move_conversation(old, Some(b)).unwrap();
        assert!(db.fts_search("calibracao", current, 3).unwrap().is_empty());
        assert_eq!(db.list_conversations(Some(b)).unwrap().len(), 2);
        assert_eq!(db.list_conversations(None).unwrap().len(), 1);
        assert!(db.move_conversation(old, Some(999)).is_err());
    }

    #[test]
    fn legacy_history_backfill_is_idempotent_and_deletes_are_searchable() {
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch("PRAGMA foreign_keys=ON;
            CREATE TABLE conversations(id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT 'Nova conversa', project_id INTEGER, created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '');
            CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE, role TEXT, content TEXT, model TEXT, provider TEXT, cost_usd REAL, created_at TEXT DEFAULT '');
            INSERT INTO conversations(id) VALUES (1),(2);
            INSERT INTO messages(id,conversation_id,role,content) VALUES (1,1,'user','histórico antigo');").unwrap();
        migrate(&conn).unwrap();
        migrate(&conn).unwrap();
        let db = DbState(Mutex::new(conn));
        assert_eq!(db.fts_search("historico", 2, 3).unwrap().len(), 1);
        db.0.lock()
            .unwrap()
            .execute("UPDATE messages SET content='substituído' WHERE id=1", [])
            .unwrap();
        assert!(db.fts_search("historico", 2, 3).unwrap().is_empty());
        assert_eq!(db.fts_search("substituido", 2, 3).unwrap().len(), 1);
        db.delete_conversation(1).unwrap();
        assert!(db.fts_search("substituido", 2, 3).unwrap().is_empty());
    }

    #[test]
    fn deleting_project_preserves_conversations_and_samples() {
        let db = database();
        let project = db.create_project("Projeto", None).unwrap();
        db.create_conversation("Conversa", Some(project)).unwrap();
        db.save_vision_sample(Some(project), "{}").unwrap();
        db.delete_project(project).unwrap();
        assert_eq!(db.list_conversations(None).unwrap().len(), 1);
        assert_eq!(
            db.0.lock()
                .unwrap()
                .query_row(
                    "SELECT count(*) FROM vision_samples WHERE project_id IS NULL",
                    [],
                    |r| r.get::<_, i64>(0)
                )
                .unwrap(),
            1
        );
    }

    #[test]
    fn training_revision_cannot_cross_projects_or_general_scope() {
        let db = database();
        let a = db.create_project("A", None).unwrap();
        let b = db.create_project("B", None).unwrap();
        let revision = db
            .save_vision_sample(Some(a), "{\"schema_version\":2}")
            .unwrap();
        assert!(db
            .vision_sample_payload(Some(a), revision)
            .unwrap()
            .contains("schema_version"));
        assert!(db.vision_sample_payload(Some(b), revision).is_err());
        assert!(db.vision_sample_payload(None, revision).is_err());
        assert!(db.vision_sample_payload(Some(9999), revision).is_err());
    }

    #[test]
    fn memory_receipts_survive_loading_the_conversation() {
        let db = database();
        let conversation = db.create_conversation("Teste", None).unwrap();
        let message = db
            .add_message(conversation, "assistant", "Preparando", None, None, None)
            .unwrap();
        let report = serde_json::json!({"state":"failed","files":[],"detail":"Nenhum registro válido recebido."});
        db.save_memory_report(message, &report, Some("Memória não gravada."))
            .unwrap();
        let loaded = db.get_messages(conversation).unwrap();
        assert_eq!(loaded[0].content, "Memória não gravada.");
        assert_eq!(loaded[0].memory_report["state"], "failed");
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Message {
    pub memory_report: serde_json::Value,
    pub sources: Vec<crate::knowledge::ContextSource>,
    pub id: i64,
    pub conversation_id: i64,
    pub role: String,
    pub content: String,
    pub model: Option<String>,
    pub provider: Option<String>,
    pub cost_usd: Option<f64>,
    pub created_at: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Project {
    pub instructions: String,
    pub pinned: bool,
    pub conversation_count: i64,
    pub file_count: i64,
    pub id: i64,
    pub name: String,
    pub description: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Document {
    pub id: i64,
    pub project_id: Option<i64>,
    pub filename: String,
    pub mime_type: String,
    pub chunk_count: i64,
    pub created_at: String,
}

pub fn open(storage_dir: &std::path::Path) -> Result<Connection> {
    std::fs::create_dir_all(storage_dir).ok();
    let path = storage_dir.join("solaris.db");
    let conn = Connection::open(path)?;
    conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")?;
    migrate(&conn)?;
    Ok(conn)
}

fn migrate(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT    NOT NULL DEFAULT 'Nova conversa',
            project_id INTEGER,
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            TEXT    NOT NULL,
            content         TEXT    NOT NULL,
            model           TEXT,
            provider        TEXT,
            cost_usd        REAL,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,
            conversation_id UNINDEXED,
            content='messages',
            content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, content, conversation_id)
            VALUES (new.id, new.content, new.conversation_id);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content, conversation_id)
            VALUES ('delete', old.id, old.content, old.conversation_id);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content, conversation_id)
            VALUES ('delete', old.id, old.content, old.conversation_id);
            INSERT INTO messages_fts(rowid, content, conversation_id)
            VALUES (new.id, new.content, new.conversation_id);
        END;

        CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY);

        CREATE TABLE IF NOT EXISTS vision_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER,
            filename    TEXT    NOT NULL,
            mime_type   TEXT    NOT NULL DEFAULT 'text/plain',
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    ",
    )?;
    if conn.query_row(
        "SELECT count(*) FROM schema_migrations WHERE version=1",
        [],
        |r| r.get::<_, i64>(0),
    )? == 0
    {
        conn.execute_batch("BEGIN; INSERT INTO messages_fts(messages_fts) VALUES ('rebuild'); INSERT INTO schema_migrations VALUES (1); COMMIT;")?;
    }
    crate::knowledge::migrate(conn)?;
    Ok(())
}

// ── Project helpers ────────────────────────────────────────────────────────

impl DbState {
    pub fn vision_sample_payload(&self, project_id: Option<i64>, id: i64) -> Result<String> {
        let conn = self.0.lock().unwrap();
        validate_project(&conn, project_id)?;
        conn.query_row(
            "SELECT payload FROM vision_samples WHERE id=?1 AND project_id IS ?2",
            params![id, project_id],
            |row| row.get(0),
        )
    }

    pub fn save_vision_sample(&self, project_id: Option<i64>, payload: &str) -> Result<i64> {
        let conn = self.0.lock().unwrap();
        validate_project(&conn, project_id)?;
        conn.execute(
            "INSERT INTO vision_samples(project_id,payload) VALUES (?1,?2)",
            params![project_id, payload],
        )?;
        Ok(conn.last_insert_rowid())
    }

    pub fn list_projects(&self) -> Result<Vec<Project>> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, name, description, created_at, updated_at, instructions, pinned, (SELECT count(*) FROM conversations WHERE project_id=projects.id), (SELECT count(*) FROM knowledge_files WHERE project_id=projects.id) FROM projects ORDER BY pinned DESC, updated_at DESC, id DESC",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(Project {
                instructions: row.get(5)?,
                pinned: row.get(6)?,
                conversation_count: row.get(7)?,
                file_count: row.get(8)?,
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                created_at: row.get(3)?,
                updated_at: row.get(4)?,
            })
        })?;
        rows.collect()
    }

    pub fn create_project(&self, name: &str, description: Option<&str>) -> Result<i64> {
        let conn = self.0.lock().unwrap();
        conn.execute(
            "INSERT INTO projects (name, description) VALUES (?1, ?2)",
            params![name, description],
        )?;
        Ok(conn.last_insert_rowid())
    }

    pub fn rename_project(&self, id: i64, name: &str, description: Option<&str>) -> Result<()> {
        let conn = self.0.lock().unwrap();
        conn.execute(
            "UPDATE projects SET name=?1, description=?2, updated_at=datetime('now') WHERE id=?3",
            params![name, description, id],
        )?;
        Ok(())
    }

    pub fn delete_project(&self, id: i64) -> Result<()> {
        let conn = self.0.lock().unwrap();
        let tx = conn.unchecked_transaction()?;
        tx.execute(
            "UPDATE conversations SET project_id=NULL WHERE project_id=?1",
            params![id],
        )?;
        tx.execute(
            "UPDATE documents SET project_id=NULL WHERE project_id=?1",
            params![id],
        )?;
        tx.execute(
            "UPDATE knowledge_files SET project_id=NULL WHERE project_id=?1",
            params![id],
        )?;
        tx.execute("DELETE FROM projects WHERE id=?1", params![id])?;
        tx.commit()?;
        Ok(())
    }

    /// Full-text search across all messages excluding the current conversation.
    /// Returns up to `limit` content snippets from past conversations.
    pub fn fts_search(
        &self,
        query: &str,
        exclude_conv_id: i64,
        limit: usize,
    ) -> Result<Vec<MemorySnippet>> {
        if query.trim().is_empty() {
            return Ok(vec![]);
        }
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT c.id, c.title, substr(messages_fts.content, 1, 1200) FROM messages_fts
             JOIN conversations c ON c.id=messages_fts.conversation_id
             WHERE messages_fts MATCH ?1
             AND c.id != ?2
             AND c.project_id IS (SELECT project_id FROM conversations WHERE id=?2)
             ORDER BY rank
             LIMIT ?3",
        )?;
        let rows = stmt.query_map(params![query, exclude_conv_id, limit as i64], |row| {
            Ok(MemorySnippet {
                conversation_id: row.get(0)?,
                title: row.get(1)?,
                content: row.get(2)?,
            })
        })?;
        rows.collect()
    }

    // ── Conversation helpers ───────────────────────────────────────────────────

    pub fn list_conversations(&self, project_id: Option<i64>) -> Result<Vec<Conversation>> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, title, project_id, created_at, updated_at
             FROM conversations WHERE project_id IS ?1 ORDER BY updated_at DESC, id DESC LIMIT 100",
        )?;
        let rows = stmt.query_map(params![project_id], |row| {
            Ok(Conversation {
                id: row.get(0)?,
                title: row.get(1)?,
                project_id: row.get(2)?,
                created_at: row.get(3)?,
                updated_at: row.get(4)?,
            })
        })?;
        rows.collect()
    }

    pub fn create_conversation(&self, title: &str, project_id: Option<i64>) -> Result<i64> {
        let conn = self.0.lock().unwrap();
        validate_project(&conn, project_id)?;
        conn.execute(
            "INSERT INTO conversations (title, project_id) VALUES (?1, ?2)",
            params![title, project_id],
        )?;
        Ok(conn.last_insert_rowid())
    }

    pub fn move_conversation(&self, id: i64, project_id: Option<i64>) -> Result<()> {
        let conn = self.0.lock().unwrap();
        validate_project(&conn, project_id)?;
        if conn.execute(
            "UPDATE conversations SET project_id=?2 WHERE id=?1",
            params![id, project_id],
        )? == 0
        {
            return Err(rusqlite::Error::QueryReturnedNoRows);
        }
        Ok(())
    }

    pub fn delete_conversation(&self, id: i64) -> Result<()> {
        let conn = self.0.lock().unwrap();
        conn.execute("DELETE FROM conversations WHERE id=?1", params![id])?;
        Ok(())
    }

    pub fn get_messages(&self, conversation_id: i64) -> Result<Vec<Message>> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, conversation_id, role, content, model, provider, cost_usd, created_at, sources_json, memory_report_json
             FROM messages WHERE conversation_id=?1 ORDER BY id",
        )?;
        let rows = stmt.query_map(params![conversation_id], |row| {
            Ok(Message {
                memory_report: serde_json::from_str(&row.get::<_, String>(9)?).unwrap_or_default(),
                sources: serde_json::from_str(&row.get::<_, String>(8)?).unwrap_or_default(),
                id: row.get(0)?,
                conversation_id: row.get(1)?,
                role: row.get(2)?,
                content: row.get(3)?,
                model: row.get(4)?,
                provider: row.get(5)?,
                cost_usd: row.get(6)?,
                created_at: row.get(7)?,
            })
        })?;
        rows.collect()
    }

    pub fn add_message(
        &self,
        conversation_id: i64,
        role: &str,
        content: &str,
        model: Option<&str>,
        provider: Option<&str>,
        cost_usd: Option<f64>,
    ) -> Result<i64> {
        let conn = self.0.lock().unwrap();
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, model, provider, cost_usd)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![conversation_id, role, content, model, provider, cost_usd],
        )?;
        let msg_id = conn.last_insert_rowid();
        conn.execute(
            "UPDATE conversations SET updated_at=datetime('now'), title=
             CASE WHEN title='Nova conversa' AND ?2='user'
             THEN substr(?3, 1, 60) ELSE title END
             WHERE id=?1",
            params![conversation_id, role, content],
        )?;
        Ok(msg_id)
    }

    pub fn list_documents(&self, project_id: Option<i64>) -> Result<Vec<Document>> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, project_id, filename, mime_type, chunk_count, created_at
             FROM documents WHERE (?1 IS NULL OR project_id=?1) ORDER BY created_at DESC",
        )?;
        let rows = stmt.query_map(params![project_id], |row| {
            Ok(Document {
                id: row.get(0)?,
                project_id: row.get(1)?,
                filename: row.get(2)?,
                mime_type: row.get(3)?,
                chunk_count: row.get(4)?,
                created_at: row.get(5)?,
            })
        })?;
        rows.collect()
    }

    pub fn add_document(
        &self,
        project_id: Option<i64>,
        filename: &str,
        mime_type: &str,
        chunk_count: i64,
    ) -> Result<i64> {
        let conn = self.0.lock().unwrap();
        conn.execute(
            "INSERT INTO documents (project_id, filename, mime_type, chunk_count) VALUES (?1,?2,?3,?4)",
            params![project_id, filename, mime_type, chunk_count],
        )?;
        Ok(conn.last_insert_rowid())
    }

    pub fn delete_document(&self, id: i64) -> Result<()> {
        let conn = self.0.lock().unwrap();
        conn.execute("DELETE FROM documents WHERE id=?1", params![id])?;
        Ok(())
    }
}
