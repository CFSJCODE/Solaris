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
        if (current) {
          setStatus(value)
          setError("")
        }
      } catch (err) {
        if (current) setError(String(err))
      } finally {
        pending = false
      }
    }
    void refresh()
    const timer = setInterval(() => void refresh(), 3000)
    return () => {
      current = false
      clearInterval(timer)
    }
  }, [projectId, refreshRevision])
  async function trainNow() {
    setBusy(true)
    try {
      const receipt = await invoke<{ message: string }>("learning_train_now", { projectId })
      setStatus(await invoke<LearningStatus>("learning_status", { projectId }))
      setError("")
      setFeedback(receipt.message)
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }
  const [feedback, setFeedback] = useState("")
  async function toggle() {
    if (!status) return
    setBusy(true)
    try {
      const value = await invoke<LearningStatus>("learning_status", {
        projectId,
        enabled: !status.enabled,
      })
      setStatus(value)
      setError("")
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }
  const states: Record<string, string> = {
    awaiting_evidence: "Pesos ajustados; aguardando evidência para ativar",
    training: "Treinando",
    paused: "Aguardando recursos",
    interrupted: "Interrompido",
    approved: "Aprovado",
    rejected: "Avaliado; não ativado",
    failed: "Falhou",
    queued: "Na fila",
    preparing: "Preparando dados",
    verifying: "Verificando revisão",
    blocked: "Aguardando dados ou novo ciclo",
    evaluated: "Pesos ajustados e avaliados; versão não ativada",
    superseded: "Agrupado com outro pedido",
  }
  return (
    <section className="sol-learning-panel sol-stack" aria-label="Aprendizado autônomo">
      <div className="sol-toolbar">
        <h2>Aprendizado autônomo</h2>
        <button className="btn-ghost" disabled={!status || busy} onClick={() => void toggle()}>
          {busy ? "Atualizando…" : status?.enabled ? "Pausar aprendizado" : "Retomar aprendizado"}
        </button>
        <button
          className="btn-ghost"
          disabled={!status?.runtime_ready || busy}
          onClick={() => void trainNow()}
        >
          Treinar contexto agora
        </button>
      </div>
      <p role="status">{status ? status.message : "Consultando o motor de aprendizado…"}</p>
      {error && (
        <p role="alert" className="sol-error">
          {error}
        </p>
      )}
      {feedback && <p role="status">{feedback}</p>}
      {status && (
        <>
          <dl className="sol-learning-metrics">
            <div>
              <dt>Exemplos coletados</dt>
              <dd>{Object.values(status.samples).reduce((sum, n) => sum + n, 0)}</dd>
            </div>
            <div>
              <dt>Exemplos verificados</dt>
              <dd>{status.samples.labeled ?? 0}</dd>
            </div>
            <div>
              <dt>Identificação incerta</dt>
              <dd>{status.samples.uncertain ?? 0}</dd>
            </div>
            <div>
              <dt>Modelos de treinamento</dt>
              <dd>YOLO26s e YOLO26x</dd>
            </div>
          </dl>
          <p>
            Quando ativo, o sistema guarda imagens selecionadas da detecção ao vivo neste
            computador. Verifica exemplos e treina quando há recursos, com prioridade para manter a
            detecção responsiva. Rótulos automáticos podem conter erros.
          </p>
          <p>
            Serviço local:{" "}
            {status.runtime_ready
              ? status.worker_running
                ? "Em execução"
                : "Aguardando inicialização"
              : "Ainda não preparado"}
            . O escaneamento alimenta ciclos automáticos a cada quatro exemplos novos verificados,
            sem exigir marcação nem parar a câmera. Candidatas que preservam a referência podem
            acumular os ajustes enquanto aguardam avaliação suficiente. O botão pode iniciar uma
            candidata com uma revisão confirmada; ativar classes novas exige evidências de outras
            sessões.
          </p>
          <p>
            Treino concorrente: a câmera continua ligada enquanto o aprendizado usa um processo
            separado e um núcleo lógico dedicado, quando a reserva está disponível. A carga é
            reduzida entre lotes; memória insuficiente ou latência crítica podem pausar somente o
            treino. Pesos são ajustados em candidatas; métricas são medidas antes de trocar a versão
            ativa.
          </p>
          {!!status.requests?.length && (
            <ul aria-label="Solicitações de treinamento">
              {status.requests.map((request) => (
                <li key={request.id}>
                  <strong>{request.model.toUpperCase()}</strong> ·{" "}
                  {states[request.state] ?? "Em processamento"} · {request.message}
                </li>
              ))}
            </ul>
          )}
          {(status.jobs.length > 0 || status.events.length > 0) && (
            <details>
              <summary>Histórico do aprendizado</summary>
              <ul>
                {status.jobs.map((job) => (
                  <li key={job.id}>
                    {new Date(job.created * 1000).toLocaleString("pt-BR")} ·{" "}
                    {states[job.state] ?? "Em processamento"} · {job.message}
                    <MetricSummary raw={job.metrics} />
                  </li>
                ))}
              </ul>
              <ul>
                {status.events.map((event, index) => (
                  <li key={`${event.created}-${index}`}>
                    {new Date(event.created * 1000).toLocaleString("pt-BR")} · {event.message}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      <DiscoveryPanel projectId={projectId} />
    </section>
  )
}

interface VisualCluster {
  id: number
  size: number
  views: number
  sessions: number
  name: string | null
  suggestion: string
  suggestion_share: number
  stable: boolean
  thumbnail: string | null
}

interface ClusterListing {
  clusters: VisualCluster[]
  regions: number
  uncertain: number
  stable_views: number
  stable_sessions: number
}

function DiscoveryPanel({ projectId }: { projectId: number | null }) {
  const [listing, setListing] = useState<ClusterListing | null>(null)
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [error, setError] = useState("")
  useEffect(() => {
    let current = true
    setListing(null)
    async function refresh() {
      try {
        const value = await invoke<ClusterListing>("vision_clusters", { projectId })
        if (current) {
          setListing(value)
          setError("")
        }
      } catch (err) {
        if (current) setError(String(err))
      }
    }
    void refresh()
    const timer = setInterval(() => void refresh(), 10000)
    return () => {
      current = false
      clearInterval(timer)
    }
  }, [projectId])
  async function rename(cluster: VisualCluster) {
    const name = (drafts[cluster.id] ?? cluster.name ?? "").trim()
    try {
      await invoke("vision_cluster_rename", {
        projectId,
        clusterId: cluster.id,
        name: name || null,
      })
      setListing(await invoke<ClusterListing>("vision_clusters", { projectId }))
      setError("")
    } catch (err) {
      setError(String(err))
    }
  }
  return (
    <details className="sol-discovery">
      <summary>Objetos descobertos{listing ? ` · ${listing.clusters.length} grupos` : ""}</summary>
      <p>
        Sem rotular nada, o aprendizado recorta as regiões detectadas, extrai a aparência com o CLIP
        e agrupa objetos parecidos. Um grupo fica estável com {listing?.stable_views ?? 10} vistas
        independentes em pelo menos {listing?.stable_sessions ?? 2} sessões; quadros seguidos contam
        como uma vista. Objetos muito semelhantes podem ser unidos. Dar nome é opcional.
      </p>
      {error && (
        <p role="alert" className="sol-error">
          {error}
        </p>
      )}
      {listing && listing.clusters.length === 0 && (
        <p role="status">
          Nenhum grupo ainda ({listing.regions} regiões analisadas, {listing.uncertain} incertas).
          Os grupos surgem enquanto a câmera coleta exemplos e o modelo CLIP está instalado.
        </p>
      )}
      {!!listing?.clusters.length && (
        <ul className="sol-discovery-grid" aria-label="Grupos de objetos descobertos">
          {listing.clusters.map((cluster) => (
            <li key={cluster.id} className="sol-discovery-card">
              {cluster.thumbnail ? (
                <img src={`data:image/jpeg;base64,${cluster.thumbnail}`} alt="" />
              ) : (
                <div className="sol-discovery-empty" aria-hidden="true" />
              )}
              <strong>{cluster.name || `Grupo ${cluster.id}`}</strong>
              <span>
                {cluster.views} vistas · {cluster.sessions} sessões ·{" "}
                {cluster.stable ? "estável" : "em formação"}
              </span>
              {cluster.suggestion && (
                <span>
                  Sugestão do detector: {cluster.suggestion} (
                  {Math.round(cluster.suggestion_share * 100)}%)
                </span>
              )}
              <form
                className="sol-toolbar"
                onSubmit={(event) => {
                  event.preventDefault()
                  void rename(cluster)
                }}
              >
                <input
                  className="project-input"
                  aria-label={`Nome do grupo ${cluster.id}`}
                  maxLength={60}
                  placeholder="Nome opcional"
                  value={drafts[cluster.id] ?? cluster.name ?? ""}
                  onChange={(event) =>
                    setDrafts((value) => ({ ...value, [cluster.id]: event.target.value }))
                  }
                />
                <button className="btn-ghost" type="submit">
                  Salvar
                </button>
              </form>
            </li>
          ))}
        </ul>
      )}
    </details>
  )
}

function MetricSummary({ raw }: { raw?: string | null }) {
  if (!raw) return null
  try {
    const report = JSON.parse(raw) as {
      model?: string
      before: { reference: number; local_proxy: number }
      after: { reference: number; local_proxy: number }
      local_evaluation_available?: boolean
      weights_changed?: boolean
    }
    if (!Number.isFinite(report.before?.reference) || !Number.isFinite(report.after?.reference))
      return null
    return (
      <p>
        {report.model?.toUpperCase()} · mAP de referência:{" "}
        {(report.before.reference * 100).toFixed(1)}% → {(report.after.reference * 100).toFixed(1)}
        %.{" "}
        {report.local_evaluation_available
          ? `mAP local (pode incluir rótulos automáticos): ${(report.before.local_proxy * 100).toFixed(1)}% → ${(report.after.local_proxy * 100).toFixed(1)}%.`
          : "Ainda não há avaliação local separada suficiente para comprovar generalização."}{" "}
        {report.weights_changed ? "Alteração dos pesos confirmada." : ""}
      </p>
    )
  } catch {
    return null
  }
}
