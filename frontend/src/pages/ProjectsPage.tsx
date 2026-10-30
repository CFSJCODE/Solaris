import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";

interface Project {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    const list = await invoke<Project[]>("list_projects");
    setProjects(list);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setLoading(true);
    try {
      await invoke("create_project", {
        name: newName.trim(),
        description: newDesc.trim() || null,
      });
      setNewName("");
      setNewDesc("");
      await load();
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: number) {
    await invoke("delete_project", { id });
    await load();
  }

  function startEdit(p: Project) {
    setEditId(p.id);
    setEditName(p.name);
    setEditDesc(p.description ?? "");
  }

  async function handleRename(e: React.FormEvent) {
    e.preventDefault();
    if (!editId || !editName.trim()) return;
    await invoke("rename_project", {
      id: editId,
      name: editName.trim(),
      description: editDesc.trim() || null,
    });
    setEditId(null);
    await load();
  }

  return (
    <div className="projects-page">
      <h2 className="projects-title">Projetos</h2>

      <form className="project-form" onSubmit={handleCreate}>
        <input
          className="project-input"
          placeholder="Nome do projeto"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          required
        />
        <input
          className="project-input"
          placeholder="Descrição (opcional)"
          value={newDesc}
          onChange={e => setNewDesc(e.target.value)}
        />
        <button className="btn-primary" type="submit" disabled={loading}>
          {loading ? "Criando…" : "Criar projeto"}
        </button>
      </form>

      {projects.length === 0 ? (
        <p className="projects-empty">Nenhum projeto ainda. Crie um acima.</p>
      ) : (
        <ul className="project-list">
          {projects.map(p => (
            <li key={p.id} className="project-item">
              {editId === p.id ? (
                <form className="project-edit-form" onSubmit={handleRename}>
                  <input
                    className="project-input"
                    value={editName}
                    onChange={e => setEditName(e.target.value)}
                    required
                    autoFocus
                  />
                  <input
                    className="project-input"
                    value={editDesc}
                    onChange={e => setEditDesc(e.target.value)}
                    placeholder="Descrição"
                  />
                  <button className="btn-primary" type="submit">Salvar</button>
                  <button className="btn-ghost" type="button" onClick={() => setEditId(null)}>
                    Cancelar
                  </button>
                </form>
              ) : (
                <>
                  <div className="project-info">
                    <span className="project-name">{p.name}</span>
                    {p.description && (
                      <span className="project-desc">{p.description}</span>
                    )}
                  </div>
                  <div className="project-actions">
                    <button className="btn-ghost" onClick={() => startEdit(p)}>Editar</button>
                    <button
                      className="btn-danger"
                      onClick={() => handleDelete(p.id)}
                    >
                      Excluir
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
