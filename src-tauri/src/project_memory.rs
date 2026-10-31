use crate::knowledge::ContextSource;
use serde::{Deserialize, Serialize};
use std::{fs, path::PathBuf, sync::Mutex};

pub struct MemoryStore {
    pub root: PathBuf,
    pub lock: Mutex<()>,
}

#[derive(Clone, Serialize)]
pub struct MemoryFile {
    pub name: String,
    pub content: String,
    pub revision: String,
}

#[derive(Serialize)]
pub struct MemoryVersion {
    pub id: String,
    pub content: String,
    pub saved_at: u64,
}

#[derive(Clone, Default, Serialize, Deserialize)]
pub struct MemoryUpdate {
    pub file: String,
    pub content: String,
}

pub fn save_requested(text: &str) -> bool {
    let text = text.to_lowercase();
    if text.starts_with("como ")
        || [
            "não salve",
            "nao salve",
            "não salvar",
            "nao salvar",
            "não registre",
            "nao registre",
        ]
        .iter()
        .any(|w| text.contains(w))
    {
        return false;
    }
    text.split(|c: char| !c.is_alphabetic()).any(|word| {
        [
            "salvar",
            "salve",
            "salva",
            "guardar",
            "guarde",
            "guarda",
            "registrar",
            "registre",
            "registra",
            "memorize",
            "memorizar",
            "lembre",
        ]
        .contains(&word)
    }) && [
        "memória",
        "memoria",
        "decis",
        "essas informações",
        "essas informacoes",
    ]
    .iter()
    .any(|w| text.contains(w))
}

fn revision(text: &str) -> String {
    use std::hash::{Hash, Hasher};
    let mut hash = std::collections::hash_map::DefaultHasher::new();
    text.hash(&mut hash);
    format!("{:x}", hash.finish())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn explicit_save_requests_are_recognized_but_informational_questions_are_not() {
        assert!(save_requested(
            "salvar essas informações na memoria do projeto dronecamp"
        ));
        assert!(save_requested("Guarde esta decisão na memória"));
        assert!(!save_requested("Como salvar informações na memória?"));
        assert!(!save_requested("Não salve isso na memória"));
        assert!(!save_requested("O registro de memória está vazio"));
    }
    fn store() -> MemoryStore {
        MemoryStore {
            root: std::env::temp_dir()
                .join(format!("solaris-memory-test-{}", uuid::Uuid::new_v4())),
            lock: Mutex::new(()),
        }
    }
    fn cleanup(store: &MemoryStore) {
        let root = store.root.canonicalize().unwrap();
        assert!(root.starts_with(std::env::temp_dir().canonicalize().unwrap()));
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn updates_preserve_text_history_and_scope_and_are_idempotent() {
        let s = store();
        let files = s.list(Some(1)).unwrap();
        assert_eq!(files.len(), 5);
        let readme = files.iter().find(|f| f.name == "README.md").unwrap();
        s.save(
            Some(1),
            "README.md",
            "# Texto humano\n\nNão apagar.",
            Some(&readme.revision),
        )
        .unwrap();
        let updates = [
            MemoryUpdate {
                file: "README.md".into(),
                content: "Decisão confirmada: CPU apenas.".into(),
            },
            MemoryUpdate {
                file: "DECISOES.md".into(),
                content: "Usar CPU.".into(),
            },
            MemoryUpdate {
                file: "../../fora.md".into(),
                content: "Proibido".into(),
            },
        ];
        assert_eq!(s.record(Some(1), 10, 11, &updates).unwrap().len(), 2);
        assert!(s.record(Some(1), 10, 11, &updates).unwrap().is_empty());
        assert!(s.record(Some(1), 10, 12, &updates).unwrap().is_empty());
        let after = s.list(Some(1)).unwrap();
        let text = &after
            .iter()
            .find(|f| f.name == "README.md")
            .unwrap()
            .content;
        assert!(text.contains("Não apagar."));
        assert!(text.contains("conversa 10"));
        assert!(s
            .list(Some(2))
            .unwrap()
            .iter()
            .all(|f| !f.content.contains("CPU apenas")));
        assert!(
            fs::read_dir(s.directory(Some(1)).join("history"))
                .unwrap()
                .count()
                >= 3
        );
        assert!(s
            .save(Some(1), "README.md", "sobrescrever", Some(&readme.revision))
            .is_err());
        assert!(s.save(Some(1), "../fora.md", "", None).is_err());
        cleanup(&s);
    }
    #[test]
    fn all_markdown_memories_are_read_fresh_with_a_total_budget() {
        let s = store();
        let files = s.list(None).unwrap();
        for f in files {
            s.save(
                None,
                &f.name,
                &"conteúdo de memória\n".repeat(2000),
                Some(&f.revision),
            )
            .unwrap();
        }
        let context = s.context(None).unwrap();
        assert_eq!(context.len(), 5);
        assert!(
            context
                .iter()
                .map(|c| c.content.chars().count())
                .sum::<usize>()
                <= 16000
        );
        cleanup(&s);
    }
}

impl MemoryStore {
    pub fn history(
        &self,
        project_id: Option<i64>,
        name: &str,
    ) -> Result<Vec<MemoryVersion>, String> {
        if !Self::valid_name(name) {
            return Err("Nome inválido.".into());
        }
        let _guard = self.lock.lock().map_err(|e| e.to_string())?;
        let directory = self.directory(project_id).join("history");
        if !directory.is_dir() {
            return Ok(Vec::new());
        }
        let mut result = Vec::new();
        for entry in fs::read_dir(directory).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let id = entry.file_name().to_string_lossy().into_owned();
            if !id.ends_with(&format!("-{name}"))
                || !entry.file_type().map_err(|e| e.to_string())?.is_file()
            {
                continue;
            }
            let modified = entry
                .metadata()
                .and_then(|m| m.modified())
                .map_err(|e| e.to_string())?;
            result.push(MemoryVersion {
                id,
                content: fs::read_to_string(entry.path()).map_err(|e| e.to_string())?,
                saved_at: modified
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs(),
            });
        }
        result.sort_by(|a, b| b.saved_at.cmp(&a.saved_at));
        result.truncate(20);
        Ok(result)
    }
    fn directory(&self, project_id: Option<i64>) -> PathBuf {
        self.root.join(
            project_id
                .map(|id| format!("project-{id}"))
                .unwrap_or_else(|| "general".into()),
        )
    }

    fn valid_name(name: &str) -> bool {
        name.len() <= 120
            && name.to_lowercase().ends_with(".md")
            && !name.starts_with('.')
            && !name
                .chars()
                .any(|c| c.is_control() || "/\\:*?\"<>|".contains(c))
    }

    fn read_unlocked(&self, project_id: Option<i64>) -> Result<Vec<MemoryFile>, String> {
        let dir = self.directory(project_id);
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        for (name, text) in [
            ("AGENTS.md", "# Orientações do projeto\n\nRegistre aqui convenções e orientações de trabalho específicas deste projeto.\n"),
            ("README.md", "# Visão geral do projeto\n\nObjetivo, escopo e estado atual.\n"),
            ("CONTRIBUTING.md", "# Como trabalhar neste projeto\n\nFluxo de trabalho, critérios de revisão e validações.\n"),
            ("MEMORY.md", "# Memória do projeto\n\nContexto durável e informações que devem permanecer entre conversas.\n"),
            ("DECISOES.md", "# Registro de decisões\n\nEntradas automáticas são registros da conversa, sujeitos à revisão.\n"),
        ] {
            let path = dir.join(name);
            if !path.exists() { fs::write(path,text).map_err(|e|e.to_string())?; }
        }
        let mut files = Vec::new();
        for entry in fs::read_dir(&dir).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let name = entry.file_name().to_string_lossy().into_owned();
            if !Self::valid_name(&name) || !entry.file_type().map_err(|e| e.to_string())?.is_file()
            {
                continue;
            }
            if entry.metadata().map_err(|e| e.to_string())?.len() > 256_000 {
                return Err(format!(
                    "Memória {name} excede 256 KB; divida seu conteúdo antes de continuar."
                ));
            }
            let content = fs::read_to_string(entry.path()).map_err(|e| e.to_string())?;
            files.push(MemoryFile {
                name,
                revision: revision(&content),
                content,
            });
            if files.len() > 32 {
                return Err("Use até 32 arquivos Markdown de memória por projeto.".into());
            }
        }
        files.sort_by(|a, b| a.name.cmp(&b.name));
        Ok(files)
    }

    pub fn list(&self, project_id: Option<i64>) -> Result<Vec<MemoryFile>, String> {
        let _guard = self.lock.lock().map_err(|e| e.to_string())?;
        self.read_unlocked(project_id)
    }

    fn write_unlocked(
        &self,
        project_id: Option<i64>,
        name: &str,
        content: &str,
    ) -> Result<MemoryFile, String> {
        if !Self::valid_name(name) || content.len() > 256_000 {
            return Err("Nome ou tamanho de memória inválido.".into());
        }
        let dir = self.directory(project_id);
        fs::create_dir_all(dir.join("history")).map_err(|e| e.to_string())?;
        let dest = dir.join(name);
        if let Ok(previous) = fs::read(&dest) {
            let backup = dir
                .join("history")
                .join(format!("{}-{name}", uuid::Uuid::new_v4()));
            fs::write(backup, previous).map_err(|e| e.to_string())?;
        }
        let temp = dir.join(format!("{}.tmp", uuid::Uuid::new_v4()));
        fs::write(&temp, content).map_err(|e| e.to_string())?;
        if let Err(error) = fs::rename(&temp, &dest) {
            let _ = fs::remove_file(&temp);
            return Err(error.to_string());
        }
        Ok(MemoryFile {
            name: name.into(),
            content: content.into(),
            revision: revision(content),
        })
    }

    pub fn save(
        &self,
        project_id: Option<i64>,
        name: &str,
        content: &str,
        expected: Option<&str>,
    ) -> Result<MemoryFile, String> {
        let _guard = self.lock.lock().map_err(|e| e.to_string())?;
        let files = self.read_unlocked(project_id)?;
        let current = files.iter().find(|f| f.name.eq_ignore_ascii_case(name));
        match (current,expected) {
            (Some(file),Some(rev)) if rev==file.revision => self.write_unlocked(project_id,&file.name,content),
            (None,None) => self.write_unlocked(project_id,name,content),
            _ => Err("O arquivo mudou desde a leitura. Recarregue a memória antes de salvar; sua edição foi preservada na tela.".into()),
        }
    }

    pub fn context(&self, project_id: Option<i64>) -> Result<Vec<ContextSource>, String> {
        let environment = self.root.parent().map(|root| {
            root.join("environment").join(
                project_id
                    .map(|id| format!("project-{id}.json"))
                    .unwrap_or_else(|| "general.json".into()),
            )
        });
        let scene = environment
            .filter(|p| p.metadata().map(|m| m.len() < 64000).unwrap_or(false))
            .and_then(|p| fs::read_to_string(p).ok())
            .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok());
        let mut remaining = if scene.is_some() { 14000 } else { 16000 };
        let mut result = Vec::new();
        let files = self.list(project_id)?;
        let allowance = remaining / files.len().max(1);
        for file in files {
            let per_file = remaining.min(allowance.min(4000));
            let content = if file.content.chars().count() > per_file {
                let tail: String = file
                    .content
                    .chars()
                    .rev()
                    .take(per_file.saturating_sub(250))
                    .collect::<String>()
                    .chars()
                    .rev()
                    .collect();
                format!(
                    "{}\n[... conteúdo intermediário omitido ...]\n{}",
                    file.content.chars().take(160).collect::<String>(),
                    tail
                )
            } else {
                file.content
            };
            remaining = remaining.saturating_sub(content.chars().count());
            result.push(ContextSource {
                kind: "memory".into(),
                document_id: None,
                citation: format!("memoria:{}", file.name),
                filename: file.name,
                content,
            });
            if remaining == 0 {
                break;
            }
        }
        if let Some(scene) = scene {
            let mut summary=String::from("Perfil local de observação do ambiente. Estatísticas de detecções estáveis; não são rótulos humanos nem confirmação da presença física. Sem identificação de pessoas.\n");
            if let Some(classes) = scene["classes"].as_object() {
                for state in classes.values() {
                    if state["observations"].as_u64().unwrap_or(0) >= 3 {
                        summary.push_str(&format!(
                            "- {}: {} observações estáveis.\n",
                            state["label"].as_str().unwrap_or("objeto"),
                            state["observations"].as_u64().unwrap_or(0)
                        ));
                    }
                }
            }
            result.push(ContextSource {
                kind: "environment".into(),
                document_id: None,
                filename: "Ambiente — perfil local".into(),
                citation: "ambiente:perfil-local".into(),
                content: summary.chars().take(2000).collect(),
            });
        }
        Ok(result)
    }

    pub fn record(
        &self,
        project_id: Option<i64>,
        conversation: i64,
        message: i64,
        updates: &[MemoryUpdate],
    ) -> Result<Vec<String>, String> {
        let _guard = self.lock.lock().map_err(|e| e.to_string())?;
        let files = self.read_unlocked(project_id)?;
        let mut changed = Vec::new();
        for file in &files {
            let name = file.name.as_str();
            let items: Vec<_> = updates
                .iter()
                .filter(|u| {
                    u.file.eq_ignore_ascii_case(name)
                        && !u.content.trim().is_empty()
                        && u.content.len() <= 4000
                        && !file.content.contains(u.content.trim())
                })
                .take(5)
                .collect();
            if items.is_empty() {
                continue;
            }
            let file = files
                .iter()
                .find(|f| f.name == name)
                .ok_or("Memória não encontrada")?;
            let marker = format!("<!-- solaris:conversation:{conversation}:message:{message} -->");
            if file.content.contains(&marker) {
                continue;
            }
            let mut content = file.content.clone();
            content.push_str(&format!("\n\n{marker}\n### Registro automático · conversa {conversation}, resposta {message}\n\n"));
            for item in items {
                content.push_str(item.content.trim());
                content.push_str("\n\n");
            }
            self.write_unlocked(project_id, name, &content)?;
            changed.push(name.into());
        }
        Ok(changed)
    }
}
