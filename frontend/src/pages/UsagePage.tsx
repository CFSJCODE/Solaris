import { useCallback, useEffect, useState } from "react"
import { invoke } from "@tauri-apps/api/core"

/** Espelha `usage::UsageLimits` (Rust). */
export interface UsageLimits {
  session_hours: number
  session_tokens: number
  weekly_tokens: number
  weekly_budget_usd: number | null
  reset_weekday: number
  reset_hour: number
  models: { model: string; share_pct: number }[]
}

interface Totals {
  input_tokens: number
  output_tokens: number
  tokens: number
  messages: number
  cost_usd: number
  cost_complete: boolean
}

interface UsageWindow extends Totals {
  limit_tokens: number
  percent: number
  started_at: number | null
  resets_at: number | null
}

interface ModelUsage extends Totals {
  model: string
  provider: string | null
  share_pct: number | null
  limit_tokens: number
  percent: number
}

export interface UsageSummary {
  now: number
  session: UsageWindow
  week: UsageWindow
  budget: { spent_usd: number; limit_usd: number; percent: number } | null
  models: ModelUsage[]
  limits: UsageLimits
}

const WEEKDAYS = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"]
const REFRESH_MS = 30_000

const nf = new Intl.NumberFormat("pt-BR")
const compact = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 })

function hhmm(d: Date) {
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
}

/** "Redefine às 22:00" no mesmo dia; "Redefine amanhã, 02:00" ou "sábado, 12:00" depois. */
export function resetLabel(resetsAt: number, now: Date = new Date()) {
  const d = new Date(resetsAt * 1000)
  const days = Math.round(
    (new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() -
      new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) /
      86_400_000,
  )
  if (days <= 0) return `às ${hhmm(d)}`
  if (days === 1) return `amanhã, ${hhmm(d)}`
  return `${WEEKDAYS[d.getDay()]}, ${hhmm(d)}`
}

export function formatUsd(value: number) {
  if (value === 0) return "US$ 0,00"
  const digits = value < 0.01 ? 4 : 2
  return `US$ ${value.toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`
}

function costText(t: Totals) {
  if (t.messages === 0) return null
  return t.cost_complete ? formatUsd(t.cost_usd) : `${formatUsd(t.cost_usd)}+`
}

function level(percent: number) {
  if (percent >= 100) return "over"
  if (percent >= 90) return "high"
  return "ok"
}

function UsageRow({
  label,
  details,
  percent,
  tone,
  used,
  limit,
  cost,
}: {
  label: string
  details: string[]
  percent: number
  tone: "session" | "week" | "model" | "budget"
  used: string
  limit: string
  cost?: string | null
}) {
  const clamped = Math.min(100, Math.max(0, percent))
  return (
    <div className="sol-usage-row">
      <div className="sol-usage-meta">
        <span className="sol-usage-label">{label}</span>
        {details.map((d) => (
          <span key={d} className="sol-usage-detail">
            {d}
          </span>
        ))}
      </div>
      <div
        className="sol-progress-bar sol-usage-bar"
        data-tone={tone}
        data-level={level(percent)}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(clamped)}
        aria-valuetext={`${Math.round(percent)}% usado — ${used} de ${limit}`}
      >
        <div className="sol-progress-fill" style={{ width: `${clamped}%` }} />
      </div>
      <div className="sol-usage-value">
        <span>{Math.round(percent)}% usado</span>
        <span className="sol-usage-detail" title={`${used} de ${limit}`}>
          {used} / {limit}
        </span>
        {cost && (
          <span
            className="sol-usage-detail"
            title={
              cost.endsWith("+")
                ? "Parcial: há respostas de modelos sem preço conhecido."
                : "Custo estimado"
            }
          >
            {cost}
          </span>
        )}
      </div>
    </div>
  )
}

export default function UsagePage() {
  const [summary, setSummary] = useState<UsageSummary | null>(null)
  const [error, setError] = useState("")
  const [editing, setEditing] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await invoke<UsageSummary>("usage_summary", {
        tzOffsetMinutes: -new Date().getTimezoneOffset(),
      })
      setSummary(data)
      setError("")
    } catch (err) {
      setError(String(err))
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), REFRESH_MS)
    const onFocus = () => void load()
    window.addEventListener("focus", onFocus)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener("focus", onFocus)
    }
  }, [load])

  // Recarrega no instante exato do próximo reinício (sessão ou semana).
  useEffect(() => {
    if (!summary) return
    const next = [summary.session.resets_at, summary.week.resets_at]
      .filter((t): t is number => t != null)
      .map((t) => t * 1000 - Date.now())
      .filter((ms) => ms > 0)
    if (!next.length) return
    const timer = window.setTimeout(() => void load(), Math.min(...next) + 1000)
    return () => window.clearTimeout(timer)
  }, [summary, load])

  if (!summary) {
    return (
      <section className="sol-page sol-stack">
        <h1>Uso</h1>
        {error ? (
          <p role="alert" className="sol-error">
            {error}
          </p>
        ) : (
          <p className="sol-usage-detail">Carregando métricas…</p>
        )}
      </section>
    )
  }

  const { session, week, budget, models, limits } = summary
  const tokens = (n: number) => compact.format(n)

  return (
    <section className="sol-page sol-stack sol-usage-page">
      <h1>Uso</h1>
      <section className="workspace-panel sol-usage-panel" aria-labelledby="sol-usage-title">
        <div className="workspace-section-heading">
          <div>
            <h2 id="sol-usage-title">Seu uso</h2>
            <p>
              <strong className="sol-usage-headline">
                {Math.round(week.percent)}% do seu limite semanal usado.
              </strong>
            </p>
          </div>
          <button type="button" className="btn-ghost" onClick={() => setEditing((v) => !v)}>
            {editing ? "Fechar limites" : "Ajustar limites"}
          </button>
        </div>

        {error && (
          <p role="alert" className="sol-error">
            {error}
          </p>
        )}

        <UsageRow
          label="Sessão atual"
          tone="session"
          percent={session.percent}
          details={[
            session.resets_at
              ? `Redefine ${resetLabel(session.resets_at)}`
              : `Inicia na próxima mensagem · janela de ${limits.session_hours} h`,
          ]}
          used={tokens(session.tokens)}
          limit={tokens(session.limit_tokens)}
          cost={costText(session)}
        />
        <UsageRow
          label="Esta semana"
          tone="week"
          percent={week.percent}
          details={[
            `Reinicia ${resetLabel(week.resets_at ?? summary.now)}`,
            `${nf.format(week.messages)} ${week.messages === 1 ? "resposta" : "respostas"}`,
          ]}
          used={tokens(week.tokens)}
          limit={tokens(week.limit_tokens)}
          cost={costText(week)}
        />
        {budget && (
          <UsageRow
            label="Orçamento semanal"
            tone="budget"
            percent={budget.percent}
            details={[`Reinicia ${resetLabel(week.resets_at ?? summary.now)}`]}
            used={formatUsd(budget.spent_usd)}
            limit={formatUsd(budget.limit_usd)}
          />
        )}

        {models.length > 0 && <h3 className="sol-usage-subhead">Por modelo</h3>}
        {models.map((m) => (
          <UsageRow
            key={m.model}
            label={m.model}
            tone="model"
            percent={m.percent}
            details={[
              m.share_pct != null
                ? `Até ${m.share_pct}% do seu limite semanal`
                : `Sem limite próprio · conta no limite semanal${m.provider ? ` · ${m.provider}` : ""}`,
              `Reinicia ${resetLabel(week.resets_at ?? summary.now)}`,
            ]}
            used={tokens(m.tokens)}
            limit={tokens(m.limit_tokens)}
            cost={costText(m)}
          />
        ))}

        <p className="sol-usage-note">
          Tokens de entrada + saída registrados a cada resposta concluída. Os limites são orçamentos
          definidos por você, não cotas dos provedores. O custo é estimado pela tabela de preços
          local, ou informado pelo OpenRouter quando disponível; “+” indica que há respostas de
          modelos sem preço conhecido.
        </p>
      </section>

      {editing && (
        <LimitsEditor
          limits={limits}
          knownModels={models.map((m) => m.model)}
          onSaved={() => {
            setEditing(false)
            void load()
          }}
        />
      )}
    </section>
  )
}

function LimitsEditor({
  limits,
  knownModels,
  onSaved,
}: {
  limits: UsageLimits
  knownModels: string[]
  onSaved: () => void
}) {
  const [draft, setDraft] = useState<UsageLimits>(limits)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const set = <K extends keyof UsageLimits>(key: K, value: UsageLimits[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))
  const setModel = (i: number, patch: Partial<UsageLimits["models"][number]>) =>
    setDraft((d) => ({
      ...d,
      models: d.models.map((m, j) => (j === i ? { ...m, ...patch } : m)),
    }))

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError("")
    try {
      await invoke("usage_set_limits", {
        limits: { ...draft, models: draft.models.map((m) => ({ ...m, model: m.model.trim() })) },
      })
      onSaved()
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  const num = (v: string) => (v === "" ? 0 : Number(v))

  return (
    <form className="workspace-panel sol-usage-limits" onSubmit={save}>
      <div className="workspace-section-heading">
        <h2>Limites</h2>
      </div>
      <div className="sol-usage-grid">
        <label className="sol-stack">
          Duração da sessão (horas)
          <input
            className="project-input"
            type="number"
            min={1}
            max={24}
            required
            value={draft.session_hours}
            onChange={(e) => set("session_hours", num(e.target.value))}
          />
        </label>
        <label className="sol-stack">
          Tokens por sessão
          <input
            className="project-input"
            type="number"
            min={1}
            step={1000}
            required
            value={draft.session_tokens}
            onChange={(e) => set("session_tokens", num(e.target.value))}
          />
        </label>
        <label className="sol-stack">
          Tokens por semana
          <input
            className="project-input"
            type="number"
            min={1}
            step={1000}
            required
            value={draft.weekly_tokens}
            onChange={(e) => set("weekly_tokens", num(e.target.value))}
          />
        </label>
        <label className="sol-stack">
          Orçamento semanal (US$, opcional)
          <input
            className="project-input"
            type="number"
            min={0}
            step={0.5}
            value={draft.weekly_budget_usd ?? ""}
            onChange={(e) =>
              set("weekly_budget_usd", e.target.value === "" ? null : Number(e.target.value))
            }
          />
        </label>
        <label className="sol-stack">
          Reinício semanal
          <select
            className="project-input"
            value={draft.reset_weekday}
            onChange={(e) => set("reset_weekday", Number(e.target.value))}
          >
            {WEEKDAYS.map((d, i) => (
              <option key={d} value={i}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="sol-stack">
          Hora do reinício
          <select
            className="project-input"
            value={draft.reset_hour}
            onChange={(e) => set("reset_hour", Number(e.target.value))}
          >
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>
                {String(h).padStart(2, "0")}:00
              </option>
            ))}
          </select>
        </label>
      </div>

      <h3 className="sol-usage-subhead">Limite por modelo (% do limite semanal)</h3>
      <datalist id="sol-usage-models">
        {knownModels.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
      {draft.models.map((m, i) => (
        <div key={i} className="sol-usage-model-limit">
          <input
            className="project-input"
            aria-label="Modelo"
            list="sol-usage-models"
            required
            value={m.model}
            onChange={(e) => setModel(i, { model: e.target.value })}
          />
          <input
            className="project-input"
            aria-label={`Percentual de ${m.model || "modelo"}`}
            type="number"
            min={1}
            max={100}
            required
            value={m.share_pct}
            onChange={(e) => setModel(i, { share_pct: num(e.target.value) })}
          />
          <button
            type="button"
            className="btn-ghost"
            onClick={() =>
              set(
                "models",
                draft.models.filter((_, j) => j !== i),
              )
            }
          >
            Remover
          </button>
        </div>
      ))}
      <div className="sol-usage-actions">
        <button
          type="button"
          className="btn-ghost"
          disabled={draft.models.length >= 32}
          onClick={() => set("models", [...draft.models, { model: "", share_pct: 50 }])}
        >
          Adicionar modelo
        </button>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Salvando…" : "Salvar limites"}
        </button>
      </div>
      {error && (
        <p role="alert" className="sol-error">
          {error}
        </p>
      )}
    </form>
  )
}
