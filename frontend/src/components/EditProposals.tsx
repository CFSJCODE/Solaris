import { useCallback, useEffect, useMemo, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import { FolderEdit, formatDate } from "../projectApi"
import { collapse, diffStats, lineDiff } from "./lineDiff"
import Modal from "./Modal"

const STATUS_LABEL: Record<FolderEdit["status"], string> = {
  pending: "Aguardando aprovação",
  applied: "Gravada",
  rejected: "Recusada",
  conflict: "Conflito",
  failed: "Falhou",
  superseded: "Substituída",
}

function DiffView({ edit }: { edit: FolderEdit }) {
  const lines = useMemo(() => lineDiff(edit.original, edit.proposed), [edit])
  const view = useMemo(() => collapse(lines), [lines])
  return (
    <div className="edit-diff" role="table" aria-label={`Diferenças em ${edit.rel_path}`}>
      {view.map((line, i) =>
        line === null ? (
          <div key={i} className="edit-diff-gap" role="row">
            ⋯
          </div>
        ) : (
          <div key={i} className={`edit-diff-line ${line.kind}`} role="row">
            <span className="edit-diff-no">{line.oldNo ?? ""}</span>
            <span className="edit-diff-no">{line.newNo ?? ""}</span>
            <span className="edit-diff-sign">
              {line.kind === "add" ? "+" : line.kind === "del" ? "−" : " "}
            </span>
            <code>{line.text || " "}</code>
          </div>
        ),
      )}
    </div>
  )
}

/**
 * Propostas de edição de arquivos das pastas vinculadas. O modelo apenas propõe; a gravação
 * acontece somente quando o usuário aprova aqui, com verificação de conflito e backup.
 */
export default function EditProposals({
  projectId,
  refreshKey = 0,
  showHistory = false,
  compact = false,
}: {
  projectId: number
  refreshKey?: number
  showHistory?: boolean
  compact?: boolean
}) {
  const [edits, setEdits] = useState<FolderEdit[]>([])
  const [open, setOpen] = useState<FolderEdit | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const load = useCallback(async () => {
    const list = await invoke<FolderEdit[]>("folder_edits", {
      projectId,
      status: showHistory ? null : "pending",
    })
    setEdits(list)
  }, [projectId, showHistory])
  useEffect(() => {
    void load().catch((err) => setError(String(err)))
  }, [load, refreshKey])

  async function decide(edit: FolderEdit, approve: boolean) {
    setBusy(true)
    setError("")
    try {
      const result = await invoke<FolderEdit>("folder_edit_decide", {
        projectId,
        editId: edit.id,
        approve,
      })
      if (result.status !== "applied" && result.status !== "rejected")
        setError(`${result.rel_path}: ${result.detail}`)
      setOpen(null)
      await load()
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  const pending = edits.filter((e) => e.status === "pending")
  if (!edits.length && !error) return null
  return (
    <section className={compact ? "edit-proposals compact" : "edit-proposals"}>
      <div className="workspace-section-heading">
        <h2>
          Alterações propostas <span className="workspace-count">{pending.length}</span>
        </h2>
      </div>
      {!compact && (
        <p className="workspace-muted">
          Nada é gravado sem sua aprovação. Antes de gravar, o SOLARIS confere se o arquivo mudou no
          disco e guarda uma cópia da versão anterior.
        </p>
      )}
      {error && (
        <p role="alert" className="workspace-error">
          {error}
        </p>
      )}
      <div className="workspace-file-list">
        {edits.map((edit) => {
          const stats = diffStats(lineDiff(edit.original, edit.proposed))
          return (
            <div className="workspace-file" key={edit.id}>
              <button className="file-open" onClick={() => setOpen(edit)}>
                <span className="file-extension">
                  {edit.original === null ? "NOVO" : edit.rel_path.split(".").pop()?.toUpperCase()}
                </span>
                <span>
                  <strong>{edit.rel_path}</strong>
                  <small>
                    {edit.folder_label} · <span className="edit-stat add">+{stats.added}</span>{" "}
                    <span className="edit-stat del">−{stats.removed}</span> ·{" "}
                    {formatDate(edit.created_at)}
                  </small>
                </span>
              </button>
              <span className={`edit-status ${edit.status}`}>{STATUS_LABEL[edit.status]}</span>
              {edit.status === "pending" && (
                <>
                  <button className="btn-ghost" disabled={busy} onClick={() => setOpen(edit)}>
                    Revisar
                  </button>
                  <button
                    className="btn-ghost"
                    disabled={busy}
                    onClick={() => void decide(edit, false)}
                  >
                    Recusar
                  </button>
                </>
              )}
            </div>
          )
        })}
      </div>
      {open && (
        <Modal
          title={`${open.original === null ? "Criar" : "Alterar"} ${open.rel_path}`}
          onClose={() => {
            if (!busy) setOpen(null)
          }}
        >
          <p className="workspace-muted">
            Pasta {open.folder_label} · {STATUS_LABEL[open.status]}
            {open.detail ? ` · ${open.detail}` : ""}
          </p>
          <DiffView edit={open} />
          {open.status === "pending" && (
            <div className="workspace-actions">
              <button
                className="btn-ghost"
                disabled={busy}
                onClick={() => void decide(open, false)}
              >
                Recusar
              </button>
              <button
                className="btn-primary"
                disabled={busy}
                onClick={() => void decide(open, true)}
              >
                {open.original === null ? "Criar arquivo" : "Aprovar e gravar"}
              </button>
            </div>
          )}
          {error && (
            <p role="alert" className="workspace-error">
              {error}
            </p>
          )}
        </Modal>
      )}
    </section>
  )
}
