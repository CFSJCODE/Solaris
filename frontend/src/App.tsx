import { useState, useEffect, useCallback, useLayoutEffect, useRef, CSSProperties } from "react"
import ChatPage from "./pages/ChatPage"
import ProjectsPage from "./pages/ProjectsPage"

import { invoke } from "@tauri-apps/api/core"
import VisionPage from "./pages/VisionPage"

import { Project } from "./projectApi"
import ProjectWorkspace from "./pages/ProjectWorkspace"
import MemoryPanel from "./components/MemoryPanel"
import { LiquidSurface } from "./design/LiquidSurface"
import { useMaterial } from "./design/MaterialProvider"
import { MaterialPreference } from "./design/materialTier"

type View = "project" | "chat" | "projects" | "rag" | "vision"

const NAV_ITEMS: { id: View; label: string; icon: string }[] = [
  { id: "projects", label: "Projetos", icon: "⊞" },
  { id: "chat", label: "Chat", icon: "◎" },
  { id: "rag", label: "Memória", icon: "⊹" },
  { id: "vision", label: "Visão", icon: "◉" },
]

export default function App() {
  const [view, setView] = useState<View>("projects")

  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [memoryEnabled, setMemoryEnabled] = useState(
    () => localStorage.getItem("solaris.memory") !== "off",
  )
  const [initialConversationId, setInitialConversationId] = useState<number | null>(null)
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("solaris.nav") === "rail"
    } catch {
      return false
    }
  })
  const toggleCollapsed = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem("solaris.nav", c ? "full" : "rail")
      } catch {
        /* ignore */
      }
      return !c
    })
  const refreshProjects = useCallback(async () => {
    const list = await invoke<Project[]>("list_projects")
    setProjects(list)
    setProjectId((id) => (list.some((p) => p.id === id) ? id : null))
  }, [])
  useEffect(() => {
    void refreshProjects().catch((err) => setError(String(err)))
  }, [view, refreshProjects])
  const activeProject = projects.find((p) => p.id === projectId)
  function openProject(id: number) {
    setProjectId(id)
    setView("project")
  }
  function openChat(id: number | null) {
    setInitialConversationId(id)
    setView("chat")
  }

  const navActive = (id: View) => view === id || (view === "project" && id === "projects")

  return (
    <div className="sol-shell sol-mica">
      <LiquidSurface
        as="nav"
        variant="regular"
        refract
        webgl
        className="sol-nav"
        aria-label="Navegação principal"
        data-collapsed={collapsed ? "" : undefined}
      >
        <div className="sol-nav-head">
          <span className="sol-nav-logo">{collapsed ? "S" : "SOLARIS"}</span>
          <button
            type="button"
            className="sol-nav-toggle sol-focusable"
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Expandir navegação" : "Recolher navegação"}
            title={collapsed ? "Expandir navegação" : "Recolher navegação"}
            onClick={() => toggleCollapsed()}
          >
            {collapsed ? "»" : "«"}
          </button>
        </div>

        <NavList
          items={NAV_ITEMS}
          isActive={navActive}
          disabled={busy}
          collapsed={collapsed}
          onSelect={(id) => {
            setView(id)
            if (id === "chat") setInitialConversationId(null)
          }}
        />

        <label className="sol-stack sol-nav-expanded-only">
          Projeto ativo
          <select
            className="project-input"
            value={projectId ?? ""}
            disabled={busy}
            onChange={(e) => {
              setProjectId(e.target.value ? Number(e.target.value) : null)
              setInitialConversationId(null)
              if (view === "project" && !e.target.value) setView("projects")
            }}
          >
            <option value="">Sem projeto</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <div className="workspace-sidebar-projects sol-nav-expanded-only">
          <span className="workspace-eyebrow">PROJETOS FIXADOS</span>
          {projects
            .filter((p) => p.pinned)
            .map((p) => (
              <button
                disabled={busy}
                key={p.id}
                className={projectId === p.id ? "active" : ""}
                onClick={() => openProject(p.id)}
              >
                {p.name}
              </button>
            ))}
          {!projects.some((p) => p.pinned) && <p>Fixe projetos para acessá-los por aqui.</p>}
        </div>
        {activeProject && (
          <button
            disabled={busy}
            className="btn-ghost sol-nav-expanded-only"
            onClick={() => setView("project")}
          >
            Abrir projeto atual
          </button>
        )}
        {error && (
          <p role="alert" className="sol-error sol-nav-expanded-only">
            {error}
          </p>
        )}
        <div className="sol-nav-footer">
          <MaterialSetting />
          <BackendStatus compact={collapsed} />
        </div>
      </LiquidSurface>

      {/* Main content */}
      <main>
        {view === "chat" && (
          <ChatPage
            key={`${projectId ?? "none"}-${initialConversationId ?? "new"}`}
            initialConversationId={initialConversationId}
            projectId={projectId}
            projects={projects}
            memoryEnabled={memoryEnabled}
            onBusy={setBusy}
          />
        )}
        {view === "projects" && (
          <ProjectsPage projects={projects} onChanged={refreshProjects} onOpen={openProject} />
        )}
        {view === "project" && activeProject && (
          <ProjectWorkspace
            key={activeProject.id}
            project={activeProject}
            onChanged={refreshProjects}
            onChat={openChat}
            onBack={() => setView("projects")}
          />
        )}
        {view === "rag" && (
          <section className="sol-page sol-stack">
            <h1>Memória · {activeProject?.name ?? "Geral"}</h1>
            <p>
              A busca textual recupera até três trechos de outras conversas do projeto ativo.
              Conversas sem projeto compartilham apenas o contexto geral.
            </p>
            {!projectId && projects.length > 0 && (
              <div className="sol-project-hint">
                <span>Selecione um projeto para ver sua memória específica:</span>
                <div className="sol-project-hint-list">
                  {projects.map((p) => (
                    <button key={p.id} className="btn-ghost" onClick={() => setProjectId(p.id)}>
                      {p.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <label>
              <input
                type="checkbox"
                checked={memoryEnabled}
                onChange={(e) => {
                  setMemoryEnabled(e.target.checked)
                  localStorage.setItem("solaris.memory", e.target.checked ? "on" : "off")
                }}
              />{" "}
              Consultar e atualizar memórias nas próximas mensagens
            </label>
            <p>
              Desativar a recuperação preserva o histórico. O histórico da própria conversa continua
              sendo enviado ao provedor ao conversar.
            </p>
            <MemoryPanel key={projectId ?? "general"} projectId={projectId} />
          </section>
        )}
        {view === "vision" && <VisionPage projectId={projectId} />}
      </main>
    </div>
  )
}

function BackendStatus({ compact }: { compact: boolean }) {
  const [status, setStatus] = useState<"checking" | "ok" | "offline">("checking")

  // Simple health check on mount
  useEffect(() => {
    let active = true
    invoke("engine_status")
      .then(() => {
        if (active) setStatus("ok")
      })
      .catch(() => {
        if (active) setStatus("offline")
      })
    return () => {
      active = false
    }
  }, [])

  const color =
    status === "ok"
      ? "var(--sol-success)"
      : status === "offline"
        ? "var(--sol-error)"
        : "var(--sol-text-muted)"
  const label =
    status === "ok"
      ? "Motor conectado"
      : status === "offline"
        ? "Motor indisponível"
        : "Verificando…"

  return (
    <span
      role="status"
      title={label}
      style={{ display: "flex", alignItems: "center", gap: "var(--sol-space-2)" }}
    >
      <span className="sol-status-dot" style={{ background: color }} />
      {compact ? <span className="sr-only">{label}</span> : label}
    </span>
  )
}

const MATERIAL_OPTIONS: { value: MaterialPreference; label: string }[] = [
  { value: "auto", label: "Automático" },
  { value: "liquid", label: "Vidro líquido" },
  { value: "glass", label: "Vidro" },
  { value: "solid", label: "Sólido" },
]

/** Accessibility setting: lets the user lower transparency regardless of OS. */
function MaterialSetting() {
  const { preference, setPreference, tier } = useMaterial()
  return (
    <label className="sol-nav-expanded-only">
      Superfícies
      <select
        className="project-input"
        value={preference}
        onChange={(e) => setPreference(e.target.value as MaterialPreference)}
        aria-describedby="sol-material-tier"
      >
        {MATERIAL_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <span id="sol-material-tier" className="sr-only">
        Renderização atual: {MATERIAL_OPTIONS.find((o) => o.value === tier)?.label}
      </span>
    </label>
  )
}

/**
 * Navigation list with a single selection indicator that morphs between items
 * (translateY + height on a spring), instead of each item toggling its own
 * background. Active items keep the original accent (gold) styling.
 */
function NavList({
  items,
  isActive,
  disabled,
  collapsed,
  onSelect,
}: {
  items: { id: View; label: string; icon: string }[]
  isActive: (id: View) => boolean
  disabled: boolean
  collapsed: boolean
  onSelect: (id: View) => void
}) {
  const listRef = useRef<HTMLDivElement>(null)
  const [indicator, setIndicator] = useState<{ y: number; h: number } | null>(null)
  const activeId = items.find((i) => isActive(i.id))?.id

  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return
    const measure = () => {
      const el = list.querySelector<HTMLElement>(`[data-nav="${activeId}"]`)
      setIndicator(el ? { y: el.offsetTop, h: el.offsetHeight } : null)
    }
    measure()
    if (typeof ResizeObserver === "undefined") return
    const ro = new ResizeObserver(measure)
    ro.observe(list)
    return () => ro.disconnect()
  }, [activeId, collapsed])

  return (
    <div className="sol-nav-list" ref={listRef}>
      <span
        className="sol-nav-indicator"
        aria-hidden="true"
        style={
          {
            opacity: indicator ? 1 : 0,
            "--sol-indicator-y": `${indicator?.y ?? 0}px`,
            "--sol-indicator-h": `${indicator?.h ?? 44}px`,
          } as CSSProperties
        }
      />
      {items.map((item) => (
        <button
          disabled={disabled}
          key={item.id}
          data-nav={item.id}
          aria-current={isActive(item.id) ? "page" : undefined}
          aria-label={collapsed ? item.label : undefined}
          title={collapsed ? item.label : undefined}
          onClick={() => onSelect(item.id)}
          className="sol-nav-item sol-focusable"
        >
          <span className="sol-nav-icon" aria-hidden="true">
            {item.icon}
          </span>
          <span className="sol-nav-label">{item.label}</span>
        </button>
      ))}
    </div>
  )
}
