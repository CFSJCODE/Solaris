/// SQLite database — managed by Rust via rusqlite (bundled, zero installation).
use rusqlite::{params, Connection, Result};
use serde::{Deserialize, Serialize};
use std::sync::Mutex;

pub struct DbState(pub Mutex<Connection>);

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Conversation {
    pub id: i64,
    pub title: String,
    pub project_id: Option<i64>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Message {
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
    conn.execute_batch("
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
            message_id UNINDEXED,
            content='messages',
            content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, content, conversation_id, message_id)
            VALUES (new.id, new.content, new.conversation_id, new.id);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content, conversation_id, message_id)
            VALUES ('delete', old.id, old.content, old.conversation_id, old.id);
        END;

        CREATE TABLE IF NOT EXISTS documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER,
            filename    TEXT    NOT NULL,
            mime_type   TEXT    NOT NULL DEFAULT 'text/plain',
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    ")?;
    Ok(())
}

// ── Project helpers ────────────────────────────────────────────────────────

impl DbState {
    pub fn list_projects(&self) -> Result<Vec<Project>> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, name, description, created_at, updated_at FROM projects ORDER BY name",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(Project {
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
        // Null out project_id on conversations before deleting project
        conn.execute("UPDATE conversations SET project_id=NULL WHERE project_id=?1", params![id])?;
        conn.execute("DELETE FROM projects WHERE id=?1", params![id])?;
        Ok(())
    }

    /// Full-text search across all messages excluding the current conversation.
    /// Returns up to `limit` content snippets from past conversations.
    pub fn fts_search(&self, query: &str, exclude_conv_id: i64, limit: usize) -> Result<Vec<String>> {
        if query.trim().is_empty() {
            return Ok(vec![]);
        }
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT content FROM messages_fts
             WHERE messages_fts MATCH ?1
             AND conversation_id != ?2
             ORDER BY rank
             LIMIT ?3",
        )?;
        let rows = stmt.query_map(
            params![query, exclude_conv_id, limit as i64],
            |row| row.get::<_, String>(0),
        )?;
        rows.collect()
    }

// ── Conversation helpers ───────────────────────────────────────────────────

    pub fn list_conversations(&self) -> Result<Vec<Conversation>> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, title, project_id, created_at, updated_at
             FROM conversations ORDER BY updated_at DESC LIMIT 100",
        )?;
        let rows = stmt.query_map([], |row| {
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
        conn.execute(
            "INSERT INTO conversations (title, project_id) VALUES (?1, ?2)",
            params![title, project_id],
        )?;
        Ok(conn.last_insert_rowid())
    }

    pub fn delete_conversation(&self, id: i64) -> Result<()> {
        let conn = self.0.lock().unwrap();
        conn.execute("DELETE FROM conversations WHERE id=?1", params![id])?;
        Ok(())
    }

    pub fn get_messages(&self, conversation_id: i64) -> Result<Vec<Message>> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, conversation_id, role, content, model, provider, cost_usd, created_at
             FROM messages WHERE conversation_id=?1 ORDER BY id",
        )?;
        let rows = stmt.query_map(params![conversation_id], |row| {
            Ok(Message {
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
