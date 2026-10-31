import { useCallback, useEffect, useRef, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import {
  Project,
  ProjectFile,
  MemoryFile,
  FILE_ACCEPT,
  formatDate,
  uploadProjectFile,
} from "../projectApi"
import { Conversation } from "../hooks/useChat"
import MemoryPanel from "../components/MemoryPanel"
import Modal from "../components/Modal"

export default function ProjectWorkspace({
  project,
  onChanged,
  onChat,
  onBack,
}: {
  project: Project
  onChanged: () => Promise<void>
  onChat: (id: number | null) => void
  onBack: () => void
}) {
  const [tab, setTab] = useState("overview")
  const [files, setFiles] = useState<ProjectFile[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [query, setQuery] = useState("")
  const [instructions, setInstructions] = useState(project.instructions)
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState("")
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [preview, setPreview] = useState<{ name: string; text: string } | null>(null)
  const [memoryImport, setMemoryImport] = useState<{
    name: string
    text: string
    revision: string | null
  } | null>(null)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(project.name)
  const [description, setDescription] = useState(project.description ?? "")
  const [deleting, setDeleting] = useState<ProjectFile | "project" | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const load = useCallback(async () => {
    const [docs, chats] = await Promise.all([
      invoke<ProjectFile[]>("project_list_files", { projectId: project.id }),
      invoke<Conversation[]>("list_conversations", { projectId: project.id }),
    ])
    setFiles(docs)
    setConversations(chats)
  }, [project.id])
  useEffect(() => {
    void load().catch((err) => setError(String(err)))
  }, [load])
  async function upload(incoming: FileList | File[] | null) {
    if (!incoming?.length || busy) return
    setBusy(true)
    setError("")
    setNotice("")
    const errors: string[] = []
    let count = 0
    for (const file of Array.from(incoming).slice(0, 20)) {
      setUploading(file.name)
      try {
        await uploadProjectFile(project.id, file)
        count++
      } catch (err) {
        errors.push(String(err))
      }
    }
    try {
      await load()
      await onChanged()
      setNotice(`${count} arquivo(s) adicionado(s) ao contexto do projeto.`)
    } catch (err) {
      errors.push(String(err))
    }
    setError(errors.join("\n"))
    setUploading("")
    setBusy(false)
  }
  async function settings() {
    setBusy(true)
    setError("")
    try {
      await invoke("project_settings", { id: project.id, instructions, pinned: project.pinned })
      await onChanged()
      setNotice("Instruções salvas para as próximas mensagens.")
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }
  async function toggle(file: ProjectFile) {
    try {
      await invoke("project_change_file", {
        id: file.id,
        projectId: project.id,
        enabled: !file.enabled,
      })
      await load()
    } catch (err) {
      setError(String(err))
    }
  }
  async function openFile(file: ProjectFile) {
    setError("")
    try {
      const text = await invoke<string>("project_read_file", { id: file.id, projectId: project.id })
      setPreview({ name: file.filename, text })
    } catch (err) {
      setError(String(err))
    }
  }
  async function prepareMemory(file: ProjectFile) {
    try {
      const [text, memories] = await Promise.all([
        invoke<string>("project_read_file", { id: file.id, projectId: project.id }),
        invoke<MemoryFile[]>("project_memory_files", { projectId: project.id }),
      ])
      const existing = memories.find((m) => m.name.toLowerCase() === file.filename.toLowerCase())
      setMemoryImport({
        name: existing?.name ?? file.filename,
        text,
        revision: existing?.revision ?? null,
      })
    } catch (err) {
      setError(String(err))
    }
  }
  async function importMemory() {
    if (!memoryImport) return
    setBusy(true)
    try {
      await invoke("project_memory_save", {
        projectId: project.id,
        name: memoryImport.name,
        content: memoryImport.text,
        revision: memoryImport.revision,
      })
      setMemoryImport(null)
      setTab("memory")
      setNotice("Markdown copiado para a memória viva do projeto.")
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }
  async function rename(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await invoke("rename_project", {
        id: project.id,
        name: name.trim(),
        description: description.trim() || null,
      })
      await onChanged()
      setEditing(false)
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }
  async function remove() {
    if (!deleting) return
    setBusy(true)
    try {
      if (deleting === "project") {
        await invoke("delete_project", { id: project.id })
        await onChanged()
        onBack()
      } else {
        await invoke("project_change_file", {
          id: deleting.id,
          projectId: project.id,
          enabled: null,
        })
        await load()
        await onChanged()
      }
      setDeleting(null)
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }
  const filtered = conversations.filter((c) => c.title.toLowerCase().includes(query.toLowerCase()))
  function fileLibrary(compact = false) {
    return (
      <section className={compact ? "workspace-panel" : "workspace-library"}>
        <div className="workspace-section-heading">
          <div>
            <h2>
              Arquivos de referência <span className="workspace-count">{files.length}</span>
            </h2>
            <p>Os trechos relevantes entram no contexto das respostas.</p>
          </div>
          <button className="btn-ghost" disabled={busy} onClick={() => fileInput.current?.click()}>
            Adicionar arquivos
          </button>
        </div>
        <div
          className={`file-dropzone ${dragging ? "dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            void upload(e.dataTransfer.files)
          }}
        >
          <strong>{uploading ? `Lendo ${uploading}…` : "Arraste seus arquivos para cá"}</strong>
          <span>PDF textual, DOCX, Markdown, TXT e código · até 10 MB por arquivo</span>
        </div>
        <div className="workspace-file-list">
          {files.slice(0, compact ? 5 : files.length).map((file) => (
            <div className="workspace-file" key={file.id}>
              <button className="file-open" onClick={() => void openFile(file)}>
                <span className="file-extension">
                  {file.filename.split(".").pop()?.toUpperCase()}
                </span>
                <span>
                  <strong>{file.filename}</strong>
                  <small>
                    {(file.byte_size / 1024).toFixed(1)} KB · {file.chunk_count} trechos
                  </small>
                </span>
              </button>
              <label className="file-context-toggle">
                <input type="checkbox" checked={file.enabled} onChange={() => void toggle(file)} />
                Contexto
              </label>
              {!compact && file.filename.toLowerCase().endsWith(".md") && (
                <button
                  className="btn-ghost"
                  disabled={busy}
                  onClick={() => void prepareMemory(file)}
                >
                  Usar como memória
                </button>
              )}
              {!compact && (
                <button className="btn-ghost" onClick={() => setDeleting(file)}>
                  Remover
                </button>
              )}
            </div>
          ))}
        </div>
        {!files.length && (
          <p className="workspace-muted">
            Adicione documentos para o chat responder com base no seu material.
          </p>
        )}
        {compact && files.length > 5 && (
          <button className="btn-ghost" onClick={() => setTab("files")}>
            Ver todos os arquivos
          </button>
        )}
      </section>
    )
  }
  return (
    <section className="workspace-page project-detail">
      <button className="workspace-back" onClick={onBack}>
        Voltar aos projetos
      </button>
      <header className="workspace-heading">
        <div>
          <span className="workspace-eyebrow">
            PROJETO · {project.pinned ? "FIXADO" : "PESSOAL"}
          </span>
          <h1>{project.name}</h1>
          <p>{project.description || "Um espaço para seus documentos, conversas e decisões."}</p>
        </div>
        <div className="workspace-actions">
          <button className="btn-ghost" onClick={() => setEditing(true)}>
            Editar projeto
          </button>
          <button className="btn-primary" onClick={() => onChat(null)}>
            Nova conversa
          </button>
        </div>
      </header>
      <nav className="workspace-tabs" aria-label="Áreas do projeto">
        {[
          ["overview", "Visão geral"],
          ["files", "Arquivos"],
          ["memory", "Memória e documentos"],
          ["instructions", "Instruções"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            aria-current={tab === key ? "page" : undefined}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      {error && (
        <p role="alert" className="workspace-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="workspace-notice">
          {notice}
        </p>
      )}
      <input
        ref={fileInput}
        className="sr-only"
        type="file"
        multiple
        accept={FILE_ACCEPT}
        onChange={(e) => {
          void upload(e.target.files)
          e.target.value = ""
        }}
      />
      {tab === "overview" && (
        <div className="project-detail-grid">
          <section>
            <div className="workspace-section-heading">
              <h2>
                Conversas <span className="workspace-count">{conversations.length}</span>
              </h2>
            </div>
            <input
              className="workspace-input"
              type="search"
              aria-label="Buscar conversas"
              placeholder="Buscar neste projeto"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className="workspace-conversations">
              {filtered.map((c) => (
                <button key={c.id} onClick={() => onChat(c.id)}>
                  <strong>{c.title}</strong>
                  <span>{formatDate(c.updated_at)}</span>
                </button>
              ))}
            </div>
            {!filtered.length && (
              <div className="workspace-empty compact">
                <h3>
                  {query ? "Nenhuma conversa encontrada" : "Comece uma conversa com contexto"}
                </h3>
                <p>
                  As instruções, os arquivos e as memórias deste projeto estarão disponíveis ao
                  chat.
                </p>
                <button className="btn-primary" onClick={() => onChat(null)}>
                  Iniciar conversa
                </button>
              </div>
            )}
          </section>
          <aside className="project-context-column">
            {fileLibrary(true)}
            <section className="workspace-panel">
              <div className="workspace-section-heading">
                <h2>Memória viva</h2>
                <button className="btn-ghost" onClick={() => setTab("memory")}>
                  Abrir
                </button>
              </div>
              <p>
                AGENTS.md, README.md, CONTRIBUTING.md, MEMORY.md e DECISOES.md são consultados e
                recebem registros de decisões ao longo das conversas.
              </p>
            </section>
            <section className="workspace-panel">
              <div className="workspace-section-heading">
                <h2>Instruções</h2>
                <button className="btn-ghost" onClick={() => setTab("instructions")}>
                  Editar
                </button>
              </div>
              <p className="instruction-preview">
                {project.instructions ||
                  "Defina como a IA deve trabalhar neste projeto: objetivo, tom, limites e critérios de qualidade."}
              </p>
            </section>
          </aside>
        </div>
      )}
      {tab === "files" && fileLibrary()}
      {tab === "memory" && <MemoryPanel projectId={project.id} />}
      {tab === "instructions" && (
        <section className="workspace-settings">
          <h2>Como a IA deve trabalhar neste projeto?</h2>
          <p>
            Estas orientações são incluídas em todas as novas mensagens do projeto. Arquivos
            anexados são material de referência.
          </p>
          <label>
            Instruções do projeto
            <textarea
              className="workspace-input"
              rows={14}
              maxLength={6000}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="Descreva o objetivo, as convenções e o formato esperado das respostas…"
            />
          </label>
          <div className="workspace-section-heading">
            <small>{instructions.length}/6.000 caracteres</small>
            <button className="btn-primary" disabled={busy} onClick={() => void settings()}>
              Salvar instruções
            </button>
          </div>
          <button className="workspace-danger-link" onClick={() => setDeleting("project")}>
            Excluir projeto
          </button>
        </section>
      )}
      {preview && (
        <Modal title={preview.name} onClose={() => setPreview(null)}>
          <p className="workspace-muted">Texto extraído e disponível para o contexto.</p>
          <pre className="file-preview">{preview.text}</pre>
        </Modal>
      )}
      {memoryImport && (
        <Modal
          title={`Usar ${memoryImport.name} como memória?`}
          onClose={() => {
            if (!busy) setMemoryImport(null)
          }}
        >
          <p>
            Uma cópia ficará nos documentos vivos deste projeto e poderá receber atualizações
            durante as conversas. O arquivo de referência original será preservado.
            {memoryImport.revision
              ? " A memória de mesmo nome será substituída por esta cópia, preservando a versão anterior no histórico."
              : ""}
          </p>
          <pre className="file-preview">{memoryImport.text}</pre>
          <div className="workspace-actions">
            <button className="btn-ghost" disabled={busy} onClick={() => setMemoryImport(null)}>
              Cancelar
            </button>
            <button className="btn-primary" disabled={busy} onClick={() => void importMemory()}>
              Usar como memória
            </button>
          </div>
          {error && (
            <p role="alert" className="workspace-error">
              {error}
            </p>
          )}
        </Modal>
      )}
      {editing && (
        <Modal
          title="Editar projeto"
          onClose={() => {
            if (!busy) setEditing(false)
          }}
        >
          <form className="workspace-form" onSubmit={(e) => void rename(e)}>
            <label>
              Nome
              <input
                className="workspace-input"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Descrição
              <textarea
                className="workspace-input"
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <button className="btn-primary" disabled={busy || !name.trim()}>
              Salvar alterações
            </button>
            {error && (
              <p role="alert" className="workspace-error">
                {error}
              </p>
            )}
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal
          title={deleting === "project" ? "Excluir projeto?" : "Remover arquivo?"}
          onClose={() => {
            if (!busy) setDeleting(null)
          }}
        >
          <p>
            {deleting === "project"
              ? "Conversas e arquivos serão preservados em “Sem projeto”. As memórias Markdown permanecem no armazenamento local."
              : `${deleting.filename} e seus trechos serão removidos da biblioteca. Respostas anteriores mantêm suas referências históricas.`}
          </p>
          <div className="workspace-actions">
            <button className="btn-ghost" disabled={busy} onClick={() => setDeleting(null)}>
              Cancelar
            </button>
            <button className="btn-danger" disabled={busy} onClick={() => void remove()}>
              Confirmar remoção
            </button>
          </div>
          {error && (
            <p className="workspace-error" role="alert">
              {error}
            </p>
          )}
        </Modal>
      )}
    </section>
  )
}
