import { useCallback, useEffect, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import {
  FolderFile,
  IndexReport,
  ProjectFolder,
  attachFolder,
  describeIndex,
  formatDate,
} from "../projectApi"
import EditProposals from "./EditProposals"
import Modal from "./Modal"

/**
 * Pastas locais vinculadas ao projeto: o chat lê os arquivos (busca + @menções) e pode
 * propor edições, que só são gravadas após aprovação.
 */
export default function FolderPanel({
  projectId,
  compact = false,
  onOpenTab,
}: {
  projectId: number
  compact?: boolean
  onOpenTab?: () => void
}) {
  const [folders, setFolders] = useState<ProjectFolder[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [files, setFiles] = useState<FolderFile[]>([])
  const [filter, setFilter] = useState("")
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [preview, setPreview] = useState<{ name: string; text: string } | null>(null)
  const [detaching, setDetaching] = useState<ProjectFolder | null>(null)
  const [copied, setCopied] = useState("")

  const load = useCallback(async () => {
    const list = await invoke<ProjectFolder[]>("folder_list", { projectId })
    setFolders(list)
    setSelected((current) =>
      current && list.some((f) => f.id === current) ? current : (list[0]?.id ?? null),
    )
  }, [projectId])
  useEffect(() => {
    void load().catch((err) => setError(String(err)))
  }, [load])
  useEffect(() => {
    if (compact || selected === null) {
      setFiles([])
      return
    }
    const timer = setTimeout(() => {
      invoke<FolderFile[]>("folder_files", { projectId, folderId: selected, filter, limit: 500 })
        .then(setFiles)
        .catch((err) => setError(String(err)))
    }, 150)
    return () => clearTimeout(timer)
  }, [projectId, selected, filter, compact, folders])

  async function run(label: string, action: () => Promise<IndexReport | null | void>) {
    setBusy(label)
    setError("")
    setNotice("")
    try {
      const report = await action()
      if (report) {
        setNotice(describeIndex(report))
        setSelected(report.folder.id)
      }
      await load()
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy("")
    }
  }
  async function openFile(file: FolderFile) {
    setError("")
    try {
      const text = await invoke<string>("folder_read", {
        projectId,
        folderId: file.folder_id,
        relPath: file.rel_path,
      })
      setPreview({ name: file.rel_path, text })
    } catch (err) {
      setError(String(err))
    }
  }
  async function copyMention(file: FolderFile) {
    const mention = /\s/.test(file.rel_path) ? `@"${file.rel_path}"` : `@${file.rel_path}`
    try {
      await navigator.clipboard.writeText(mention)
      setCopied(file.rel_path)
      setTimeout(() => setCopied(""), 1600)
    } catch {
      setNotice(`Use ${mention} no chat para enviar o arquivo inteiro.`)
    }
  }

  const current = folders.find((f) => f.id === selected) ?? null
  return (
    <section className={compact ? "workspace-panel" : "workspace-library"}>
      <div className="workspace-section-heading">
        <div>
          <h2>
            Pastas locais <span className="workspace-count">{folders.length}</span>
          </h2>
          <p>O chat lê os arquivos destas pastas e pode propor edições para você aprovar.</p>
        </div>
        <button
          className="btn-ghost"
          disabled={!!busy}
          onClick={() => void run("attach", () => attachFolder(projectId))}
        >
          {busy === "attach" ? "Indexando…" : "Anexar pasta"}
        </button>
      </div>
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
      <div className="workspace-file-list">
        {folders.map((folder) => (
          <div
            className={`workspace-file folder-row${!compact && folder.id === selected ? " active" : ""}`}
            key={folder.id}
          >
            <button
              className="file-open"
              onClick={() => (compact ? onOpenTab?.() : setSelected(folder.id))}
              title={folder.path}
            >
              <span className="file-extension">DIR</span>
              <span>
                <strong>{folder.label}</strong>
                <small>
                  {folder.indexed_count}/{folder.file_count} arquivos indexados
                  {folder.truncated ? " · lista limitada" : ""}
                  {folder.last_indexed_at ? ` · ${formatDate(folder.last_indexed_at)}` : ""}
                </small>
                {!compact && <small className="folder-path">{folder.path}</small>}
              </span>
            </button>
            <label className="file-context-toggle">
              <input
                type="checkbox"
                checked={folder.enabled}
                disabled={!!busy}
                onChange={() =>
                  void run("toggle", () =>
                    invoke("folder_set_enabled", {
                      projectId,
                      folderId: folder.id,
                      enabled: !folder.enabled,
                    }),
                  )
                }
              />
              Contexto
            </label>
            {!compact && (
              <>
                <button
                  className="btn-ghost"
                  disabled={!!busy}
                  onClick={() =>
                    void run(`reindex-${folder.id}`, () =>
                      invoke<IndexReport>("folder_reindex", { projectId, folderId: folder.id }),
                    )
                  }
                >
                  {busy === `reindex-${folder.id}` ? "Atualizando…" : "Atualizar índice"}
                </button>
                <button
                  className="btn-ghost"
                  disabled={!!busy}
                  onClick={() => setDetaching(folder)}
                >
                  Desvincular
                </button>
              </>
            )}
          </div>
        ))}
      </div>
      {!folders.length && (
        <p className="workspace-muted">
          Anexe a pasta de um firmware, projeto de software ou documentação. Arquivos .env, chaves e
          pastas como .git, node_modules e build são ignorados.
        </p>
      )}
      {!compact && current && (
        <div className="folder-browser">
          <input
            className="workspace-input"
            type="search"
            aria-label={`Filtrar arquivos de ${current.label}`}
            placeholder={`Filtrar arquivos de ${current.label}`}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <div className="folder-tree">
            {files.map((file) => (
              <div className="folder-tree-row" key={file.rel_path}>
                <button
                  className="folder-tree-open"
                  onClick={() => void openFile(file)}
                  title={file.note || file.rel_path}
                >
                  <span className={`folder-tree-dot${file.indexed ? " indexed" : ""}`} />
                  <span className="folder-tree-path">{file.rel_path}</span>
                  <small>
                    {(file.byte_size / 1024).toFixed(1)} KB{file.note ? ` · ${file.note}` : ""}
                  </small>
                </button>
                <button className="btn-ghost" onClick={() => void copyMention(file)}>
                  {copied === file.rel_path ? "Copiado" : "Citar no chat"}
                </button>
              </div>
            ))}
            {!files.length && <p className="workspace-muted">Nenhum arquivo encontrado.</p>}
            {files.length >= 500 && (
              <p className="workspace-muted">Mostrando 500 arquivos. Use o filtro para refinar.</p>
            )}
          </div>
        </div>
      )}
      {!compact && <EditProposals projectId={projectId} showHistory refreshKey={folders.length} />}
      {compact && folders.length > 0 && (
        <button className="btn-ghost" onClick={() => onOpenTab?.()}>
          Navegar nos arquivos
        </button>
      )}
      {preview && (
        <Modal title={preview.name} onClose={() => setPreview(null)}>
          <p className="workspace-muted">Conteúdo atual lido da pasta vinculada.</p>
          <pre className="file-preview">{preview.text}</pre>
        </Modal>
      )}
      {detaching && (
        <Modal
          title="Desvincular pasta?"
          onClose={() => {
            if (!busy) setDetaching(null)
          }}
        >
          <p>
            {detaching.label} deixará de ser lida pelo chat e o índice local será apagado. Nenhum
            arquivo da pasta será alterado ou excluído.
          </p>
          <div className="workspace-actions">
            <button className="btn-ghost" disabled={!!busy} onClick={() => setDetaching(null)}>
              Cancelar
            </button>
            <button
              className="btn-danger"
              disabled={!!busy}
              onClick={() =>
                void run("detach", async () => {
                  await invoke("folder_detach", { projectId, folderId: detaching.id })
                  setDetaching(null)
                })
              }
            >
              Desvincular
            </button>
          </div>
        </Modal>
      )}
    </section>
  )
}
