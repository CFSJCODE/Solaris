import { useEffect, useState } from "react"
import { invoke } from "@tauri-apps/api/core"

interface LearningStatus {
  concurrent?: boolean
  learning_cpu?: number | null
  enabled: number
  runtime_ready: boolean
  worker_running: boolean
  message: string
  samples: Record<string, number>
  jobs: { id: string; state: string; message: string; created: number; metrics?: string | null }[]
  events: { created: number; message: string }[]
  requests?: { id: string; model: string; state: string; message: string }[]
}

function parseBatchProgress(msg: string): { current: number; total: number; loss: number | null; model: string } | null {
  // "YOLO26S · lote 39/87 · perda 2.9265"
  const m = msg.match(/^(\w+)\s*·\s*lote\s*(\d+)\/(\d+)(?:\s*·\s*perda\s*([\d.]+))?/i)
  if (!m) return null
  return {
    model: m[1].toUpperCase(),
    current: parseInt(m[2]),
    total: parseInt(m[3]),
    loss: m[4] ? parseFloat(m[4]) : null,
  }
}

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

const STATE_LABELS: Record<string, string> = {
  awaiting_evidence: "Aguardando evidência",
  training: "Treinando",
  paused: "Pausado",
  interrupted: "Interrompido",
  approved: "Aprovado",
  rejected: "Recusado",
  failed: "Falhou",
  queued: "Na fila",
  preparing: "Preparando",
  verifying: "Verificando",
  blocked: "Bloqueado",
  evaluated: "Avaliado",
  superseded: "Agrupado",
}

const STATE_COLOR: Record<string, string> = {
  training: "sol-badge-active",
  queued: "sol-badge-queue",
  approved: "sol-badge-ok",
  rejected: "sol-badge-warn",
  failed: "sol-badge-warn",
  blocked: "sol-badge-warn",
  paused: "sol-badge-idle",
  interrupted: "sol-badge-idle",
}

function Badge({ state }: { state: string }) {
  return <span className={`sol-badge ${STATE_COLOR[state] ?? "sol-badge-idle"}`}>{STATE_LABELS[state] ?? state}</span>
}

function MetricSummary({ raw }: { raw?: string | null }) {
  if (!raw) return null
  try {
    const r = JSON.parse(raw) as {
      model?: string
      before: { reference: number; local_proxy: number }
      after: { reference: number; local_proxy: number }
      local_evaluation_available?: boolean
      weights_changed?: boolean
    }
    if (!Number.isFinite(r.before?.reference) || !Number.isFinite(r.after?.reference)) return null
    const delta = r.after.reference - r.before.reference
    return (
      <p className={`sol-metric-delta ${delta >= 0 ? "sol-metric-up" : "sol-metric-down"}`}>
        {r.model?.toUpperCase()} mAP {(r.before.reference * 100).toFixed(1)}%
        {" → "}{(r.after.reference * 100).toFixed(1)}%
        {" ("}{delta >= 0 ? "+" : ""}{(delta * 100).toFixed(1)}{"%)"}
        {r.weights_changed ? " · pesos aplicados" : ""}
      </p>
    )
  } catch {
    return null
  }
}

export default function LearningPanel({
  projectId,
  refreshRevision = 0,
}: {
  projectId: number | null
  refreshRevision?: number
}) {
  const [status, setStatus] = useState<LearningStatus | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState("")

  useEffect(() => {
    let current = true
    let pending = false
    setStatus(null)
    setFeedback("")
    setError("")
    async function refresh() {
      if (pending) return
      pending = true
      try {
        const value = await invoke<LearningStatus>("learning_status", { projectId })
        if (current) { setStatus(value); setError("") }
      } catch (err) {
        if (current) setError(String(err))
      } finally {
        pending = false }
    }
    void refresh()
    const timer = setInterval(() => void refresh(), 3000)
    return () => { current = false; clearInterval(timer) }
  }, [projectId, refreshRevision])

  async function trainNow() {
    setBusy(true)
    try {
      const receipt = await invoke<{ message: string }>("learning_train_now", { projectId })
      setStatus(await invoke<LearningStatus>("learning_status", { projectId }))
      setError("")
      setFeedback(receipt.message)
    } catch (err) { setError(String(err)) }
    finally { setBusy(false) }
  }

  async function toggle() {
    if (!status) return
    setBusy(true)
    try {
      const value = await invoke<LearningStatus>("learning_status", { projectId, enabled: !status.enabled })
      setStatus(value); setError("")
    } catch (err) { setError(String(err)) }
    finally { setBusy(false) }
  }

  // Derive active training job
  const activeJob = status?.jobs.find(j => j.state === "training")
  const progress = activeJob ? parseBatchProgress(activeJob.message) : null

  // Requests: hide superseded ones in the main list; show in history
  const visibleRequests = (status?.requests ?? []).filter(r => r.state !== "superseded")
  const supersededCount = (status?.requests ?? []).filter(r => r.state === "superseded").length

  // Recent learnings: approved jobs
  const recentApproved = (status?.jobs ?? []).filter(j => j.state === "approved")
  // Doubts: uncertain samples + rejected candidates
  const uncertainCount = status?.samples.uncertain ?? 0
  const rejectedJobs = (status?.jobs ?? []).filter(j => j.state === "rejected")

  const totalSamples = Object.values(status?.samples ?? {}).reduce((s, n) => s + n, 0)
  const labeledSamples = status?.samples.labeled ?? 0

  return (
    <section className="sol-learning-panel sol-stack" aria-label="Aprendizado autônomo">
      {/* ── Toolbar ── */}
      <div className="sol-toolbar">
        <h2>Aprendizado autônomo</h2>
        <button className="btn-ghost" disabled={!status || busy} onClick={() => void toggle()}>
          {busy ? "Atualizando…" : status?.enabled ? "Pausar" : "Retomar"}
        </button>
        <button className="btn-ghost" disabled={!status?.runtime_ready || busy} onClick={() => void trainNow()}>
          Treinar agora
        </button>
      </div>

      {error && <p role="alert" className="sol-error">{error}</p>}
      {feedback && <p role="status" className="sol-feedback">{feedback}</p>}

      {!status && <p role="status" className="sol-muted">Consultando o motor de aprendizado…</p>}

      {status && (
        <>
          {/* ── Active training card ── */}
          {activeJob && (
            <div className="sol-train-card" aria-live="polite" aria-label="Treinamento em andamento">
              <div className="sol-train-header">
                <span className="sol-train-label">
                  {progress ? `Treinando ${progress.model}` : activeJob.message}
                </span>
                {progress?.loss != null && (
                  <span className="sol-train-loss">perda {progress.loss.toFixed(4)}</span>
                )}
              </div>
              {progress && (
                <>
                  <div className="sol-progress-bar" role="progressbar"
                    aria-valuenow={progress.current} aria-valuemax={progress.total}
                    aria-label={`Lote ${progress.current} de ${progress.total}`}>
                    <div
                      className="sol-progress-fill"
                      style={{ width: `${Math.min(100, (progress.current / progress.total) * 100).toFixed(1)}%` }}
                    />
                  </div>
                  <div className="sol-progress-label">
                    Lote {progress.current} / {progress.total}
                    {" · "}{Math.round((progress.current / progress.total) * 100)}%
                  </div>
                </>
              )}
            </div>
          )}

          {/* ── Status idle ── */}
          {!activeJob && (
            <p role="status" className="sol-status-msg">
              {status.runtime_ready
                ? status.worker_running
                  ? status.message
                  : "Aguardando inicialização do worker"
                : "Motor de aprendizado ainda não preparado"}
            </p>
          )}

          {/* ── Metrics row ── */}
          <dl className="sol-learning-metrics">
            <div><dt>Exemplos coletados</dt><dd>{totalSamples}</dd></div>
            <div><dt>Verificados</dt><dd>{labeledSamples}</dd></div>
            <div>
              <dt>Em dúvida</dt>
              <dd className={uncertainCount > 0 ? "sol-warn-value" : ""}>{uncertainCount}</dd>
            </div>
            <div><dt>Modelo</dt><dd>YOLO26s</dd></div>
          </dl>

          {/* ── Request queue ── */}
          {visibleRequests.length > 0 && (
            <div className="sol-queue" aria-label="Fila de treinamento">
              <h3>Fila</h3>
              <ul>
                {visibleRequests.map(r => (
                  <li key={r.id} className="sol-queue-item">
                    <Badge state={r.state} />
                    <span className="sol-queue-model">{r.model.toUpperCase()}</span>
                    <span className="sol-queue-msg">{r.message}</span>
                  </li>
                ))}
                {supersededCount > 0 && (
                  <li className="sol-queue-item sol-muted">
                    +{supersededCount} pedido{supersededCount > 1 ? "s" : ""} agrupado{supersededCount > 1 ? "s" : ""}
                  </li>
                )}
              </ul>
            </div>
          )}

          {/* ── Aprendeu recentemente ── */}
          {recentApproved.length > 0 && (
            <div className="sol-discoveries" aria-label="Aprendizados recentes">
              <h3>Aprendeu recentemente</h3>
              <ul>
                {recentApproved.map(j => (
                  <li key={j.id}>
                    <span className="sol-time">{fmt(j.created)}</span>
                    <MetricSummary raw={j.metrics} />
                    {!j.metrics && <span>{j.message}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ── Dúvidas e recusas ── */}
          {(uncertainCount > 0 || rejectedJobs.length > 0) && (
            <div className="sol-doubts" aria-label="Dúvidas e recusas">
              <h3>Em dúvida / Recusado</h3>
              {uncertainCount > 0 && (
                <p>
                  <strong>{uncertainCount}</strong> exemplo{uncertainCount > 1 ? "s" : ""} com
                  identificação incerta — YOLO e verificador discordaram. O sistema aguarda mais
                  observações antes de incluí-los no treino.
                </p>
              )}
              {rejectedJobs.map(j => (
                <div key={j.id} className="sol-rejected-job">
                  <span className="sol-time">{fmt(j.created)}</span>
                  <Badge state="rejected" />
                  <MetricSummary raw={j.metrics} />
                  {!j.metrics && <span className="sol-muted">{j.message}</span>}
                </div>
              ))}
            </div>
          )}

          {/* ── Event feed ── */}
          {status.events.length > 0 && (
            <details className="sol-events-details">
              <summary>Atividade recente ({status.events.length})</summary>
              <ul className="sol-event-list">
                {status.events.map((e, i) => (
                  <li key={`${e.created}-${i}`}>
                    <span className="sol-time">{fmt(e.created)}</span>
                    {e.message}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {/* ── Full history ── */}
          {status.jobs.filter(j => !["training"].includes(j.state)).length > 0 && (
            <details>
              <summary>Histórico de ciclos</summary>
              <ul>
                {status.jobs
                  .filter(j => j.state !== "training")
                  .map(j => (
                    <li key={j.id}>
                      {fmt(j.created)} · <Badge state={j.state} /> {j.message}
                      <MetricSummary raw={j.metrics} />
                    </li>
                  ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  )
}
