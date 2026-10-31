use crate::db::DbState;
use rusqlite::{params, Connection, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextSource {
    pub kind: String,
    pub document_id: Option<i64>,
    pub filename: String,
    pub citation: String,
    pub content: String,
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    fn db() -> DbState {
        let c=Connection::open_in_memory().unwrap();
        c.execute_batch("PRAGMA foreign_keys=ON;CREATE TABLE projects(id INTEGER PRIMARY KEY,instructions TEXT DEFAULT '',pinned INTEGER DEFAULT 0,updated_at TEXT);CREATE TABLE messages(id INTEGER PRIMARY KEY);").unwrap();
        migrate(&c).unwrap(); migrate(&c).unwrap();
        DbState(Mutex::new(c))
    }
    #[test]
    fn file_context_is_scoped_and_selected_files_cannot_cross_projects() {
        let db=db();
        db.0.lock().unwrap().execute_batch("INSERT INTO projects(id) VALUES (1),(2)").unwrap();
        let a=db.store_file(Some(1),"contrato.md","text/plain",42,"","O prazo de entrega é 17 de dezembro.").unwrap();
        let b=db.store_file(Some(2),"privado.md","text/plain",42,"","O prazo confidencial é 31 de janeiro.").unwrap();
        assert_eq!(db.project_files(None).unwrap().len(),0);
        let hits=db.file_context(Some(1),"qual o prazo de entrega",&[]).unwrap();
        assert_eq!(hits.len(),1);assert!(hits[0].content.contains("17 de dezembro"));
        assert!(db.file_context(Some(1),"prazo",&[b]).is_err());
        assert!(db.read_file(b,Some(1)).is_err());
        db.change_file(a,Some(1),Some(false)).unwrap();
        assert!(db.file_context(Some(1),"prazo",&[]).unwrap().is_empty());
        assert_eq!(db.file_context(Some(1),"",&[a]).unwrap().len(),1);
        db.change_file(a,Some(1),None).unwrap();
        assert!(db.file_context(Some(1),"prazo",&[]).unwrap().is_empty());
    }
    #[test]
    fn unicode_context_is_bounded_and_fts_input_is_safe() {
        let db=db();
        let id=db.store_file(None,"memória.md","text/plain",42,"",&"ação técnica ".repeat(6000)).unwrap();
        let hits=db.file_context(None,"*\" OR NEAR()",&[id]).unwrap();
        assert!(hits.iter().map(|h|h.content.chars().count()).sum::<usize>()<=12000);
        assert!(!hits.is_empty());
        assert!(!search_query("\"a\" OR * ").contains('*'));
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ProjectFile {
    pub id: i64,
    pub filename: String,
    pub mime_type: String,
    pub byte_size: i64,
    pub chunk_count: i64,
    pub enabled: bool,
    pub created_at: String,
}

pub fn migrate(conn: &Connection) -> Result<()> {
    for (table, column, definition) in [
        ("projects", "instructions", "TEXT NOT NULL DEFAULT ''"),
        ("projects", "pinned", "INTEGER NOT NULL DEFAULT 0"),
        ("messages", "sources_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("messages", "memory_report_json", "TEXT NOT NULL DEFAULT 'null'"),
    ] {
        let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
        let columns = stmt.query_map([], |r| r.get::<_, String>(1))?.collect::<Result<Vec<_>>>()?;
        if !columns.iter().any(|c| c == column) {
            conn.execute_batch(&format!("ALTER TABLE {table} ADD COLUMN {column} {definition}"))?;
        }
    }
    conn.execute_batch("
        CREATE TABLE IF NOT EXISTS knowledge_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            filename TEXT NOT NULL, mime_type TEXT NOT NULL, byte_size INTEGER NOT NULL,
            original_b64 TEXT NOT NULL, extracted_text TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES knowledge_files(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL, filename TEXT NOT NULL, content TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS knowledge_project ON knowledge_files(project_id);
        CREATE INDEX IF NOT EXISTS knowledge_document ON knowledge_chunks(document_id);
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(filename, content, content='knowledge_chunks', content_rowid='id');
        CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge_chunks BEGIN
            INSERT INTO knowledge_fts(rowid,filename,content) VALUES(new.id,new.filename,new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge_chunks BEGIN
            INSERT INTO knowledge_fts(knowledge_fts,rowid,filename,content) VALUES('delete',old.id,old.filename,old.content);
        END;
    ")
}

pub fn search_query(text: &str) -> String {
    let stop = ["para", "como", "qual", "quais", "sobre", "arquivo", "arquivos", "projeto", "voce", "você", "isso", "esta", "esse", "essa", "pelo", "pela", "pode", "usar", "leia", "with", "this", "that", "from", "what", "have"];
    text.split(|c: char| !c.is_alphanumeric()).map(str::to_lowercase)
        .filter(|w| w.chars().count() >= 3 && !stop.contains(&w.as_str())).take(24)
        .map(|w| format!("\"{w}\" ")).collect::<Vec<_>>().join(" OR ")
}

impl DbState {
    pub fn project_scope(&self, conversation_id: i64) -> Result<Option<i64>> {
        self.0.lock().unwrap().query_row("SELECT project_id FROM conversations WHERE id=?1", [conversation_id], |r| r.get(0))
    }

    pub fn check_project(&self, id: Option<i64>) -> Result<()> {
        if let Some(id) = id {
            self.0.lock().unwrap().query_row("SELECT id FROM projects WHERE id=?1", [id], |_| Ok(()))?;
        }
        Ok(())
    }

    pub fn project_instructions(&self, id: Option<i64>) -> Result<String> {
        match id {
            Some(id) => self.0.lock().unwrap().query_row("SELECT instructions FROM projects WHERE id=?1", [id], |r| r.get(0)),
            None => Ok(String::new()),
        }
    }

    pub fn update_project_settings(&self, id: i64, instructions: &str, pinned: bool) -> Result<()> {
        self.0.lock().unwrap().execute("UPDATE projects SET instructions=?2,pinned=?3,updated_at=datetime('now') WHERE id=?1", params![id,instructions,pinned])?;
        Ok(())
    }

    pub fn store_file(&self, project_id: Option<i64>, filename: &str, mime_type: &str, byte_size: i64, original: &str, text: &str) -> Result<i64> {
        self.check_project(project_id)?;
        let conn = self.0.lock().unwrap();
        let tx = conn.unchecked_transaction()?;
        tx.execute("INSERT INTO knowledge_files(project_id,filename,mime_type,byte_size,original_b64,extracted_text) VALUES(?1,?2,?3,?4,?5,?6)", params![project_id,filename,mime_type,byte_size,original,text])?;
        let id = tx.last_insert_rowid();
        let chars: Vec<char> = text.chars().collect();
        for (index, start) in (0..chars.len()).step_by(1300).enumerate() {
            let content: String = chars[start..(start+1500).min(chars.len())].iter().collect();
            tx.execute("INSERT INTO knowledge_chunks(document_id,chunk_index,filename,content) VALUES(?1,?2,?3,?4)",params![id,index as i64,filename,content])?;
        }
        tx.execute("UPDATE projects SET updated_at=datetime('now') WHERE id=?1", [project_id])?;
        tx.commit()?;
        Ok(id)
    }

    pub fn project_files(&self, project_id: Option<i64>) -> Result<Vec<ProjectFile>> {
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare("SELECT id,filename,mime_type,byte_size,enabled,created_at,(SELECT count(*) FROM knowledge_chunks WHERE document_id=f.id) FROM knowledge_files f WHERE project_id IS ?1 ORDER BY id DESC")?;
        let rows = stmt.query_map([project_id], |r| Ok(ProjectFile { id:r.get(0)?,filename:r.get(1)?,mime_type:r.get(2)?,byte_size:r.get(3)?,enabled:r.get(4)?,created_at:r.get(5)?,chunk_count:r.get(6)? }))?;
        rows.collect()
    }

    pub fn read_file(&self, id: i64, project_id: Option<i64>) -> Result<String> {
        self.0.lock().unwrap().query_row("SELECT extracted_text FROM knowledge_files WHERE id=?1 AND project_id IS ?2", params![id,project_id], |r| r.get(0))
    }

    pub fn change_file(&self, id: i64, project_id: Option<i64>, enabled: Option<bool>) -> Result<()> {
        let conn = self.0.lock().unwrap();
        let changed = match enabled {
            Some(enabled) => conn.execute("UPDATE knowledge_files SET enabled=?3 WHERE id=?1 AND project_id IS ?2",params![id,project_id,enabled])?,
            None => conn.execute("DELETE FROM knowledge_files WHERE id=?1 AND project_id IS ?2",params![id,project_id])?,
        };
        if changed == 0 { return Err(rusqlite::Error::QueryReturnedNoRows); }
        Ok(())
    }

    pub fn file_context(&self, project_id: Option<i64>, query: &str, selected: &[i64]) -> Result<Vec<ContextSource>> {
        let conn = self.0.lock().unwrap();
        for id in selected {
            conn.query_row("SELECT id FROM knowledge_files WHERE id=?1 AND project_id IS ?2",params![id,project_id], |_| Ok(()))?;
        }
        let query = search_query(query);
        let sql = if !query.is_empty() && selected.is_empty() {
            "SELECT f.id,f.filename,c.chunk_index,c.content FROM knowledge_fts JOIN knowledge_chunks c ON c.id=knowledge_fts.rowid JOIN knowledge_files f ON f.id=c.document_id WHERE f.project_id IS ?1 AND f.enabled=1 AND knowledge_fts MATCH ?2 ORDER BY rank LIMIT 32"
        } else {
            "SELECT f.id,f.filename,c.chunk_index,c.content FROM knowledge_chunks c JOIN knowledge_files f ON f.id=c.document_id WHERE f.project_id IS ?1 AND (f.enabled=1 OR ?2!='') ORDER BY c.chunk_index,f.id DESC LIMIT 2000"
        };
        let mut stmt = conn.prepare(sql)?;
        let rows = stmt.query_map(params![project_id,if selected.is_empty() { query.as_str() } else { "selected" }], |r| Ok(ContextSource {
            kind:"file".into(),document_id:Some(r.get(0)?),filename:r.get(1)?,citation:format!("arquivo:{}:{}",r.get::<_,i64>(0)?,r.get::<_,i64>(2)?+1),content:r.get(3)?
        }))?;
        let candidates = rows.collect::<Result<Vec<_>>>()?;
        drop(stmt);drop(conn);
        if candidates.is_empty() && !query.is_empty() && selected.is_empty() { return self.file_context(project_id,"",selected); }
        let mut result = Vec::new();
        let mut remaining = 12000;
        for mut item in candidates {
            if !selected.is_empty() && !selected.contains(&item.document_id.unwrap_or(0)) { continue; }
            if remaining == 0 { break; }
            item.content = item.content.chars().take(remaining).collect();
            remaining -= item.content.chars().count();
            result.push(item);
        }
        Ok(result)
    }

    pub fn save_memory_report(&self, id:i64, report:&serde_json::Value, replacement:Option<&str>)->Result<()> {
        let conn=self.0.lock().unwrap();
        conn.execute("UPDATE messages SET memory_report_json=?2,content=COALESCE(?3,content) WHERE id=?1",params![id,report.to_string(),replacement])?;
        Ok(())
    }

    pub fn save_sources(&self, message_id: i64, sources: &[ContextSource]) -> Result<()> {
        let json = serde_json::to_string(sources).map_err(|e| rusqlite::Error::ToSqlConversionFailure(Box::new(e)))?;
        self.0.lock().unwrap().execute("UPDATE messages SET sources_json=?2 WHERE id=?1",params![message_id,json])?;
        Ok(())
    }
}
