import { useState, useEffect, useCallback } from "react"
import ChatPage from "./pages/ChatPage"
import ProjectsPage from "./pages/ProjectsPage"

import { invoke } from "@tauri-apps/api/core"
import VisionPage from "./pages/VisionPage"

import { Project } from "./projectApi"
import ProjectWorkspace from "./pages/ProjectWorkspace"
import MemoryPanel from "./components/MemoryPanel"

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

  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--sol-bg)" }}>
      {/* Sidebar */}
      <nav
        style={{
          width: 260,
          background: "var(--sol-surface)",
          borderRight: "1px solid var(--sol-border)",
          display: "flex",
          flexDirection: "column",
          padding: "var(--sol-space-6) var(--sol-space-3)",
          gap: "var(--sol-space-2)",
          flexShrink: 0,
        }}
      >
        {/* Logo */}
        <div
          style={{
            padding: "var(--sol-space-3) var(--sol-space-3) var(--sol-space-6)",
            fontWeight: 700,
            fontSize: 18,
            background: "var(--sol-sunset)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
            letterSpacing: "0.04em",
          }}
        >
          SOLARIS
        </div>

        {NAV_ITEMS.map((item) => (
          <button
            disabled={busy}
            key={item.id}
            onClick={() => {
              setView(item.id)
              if (item.id === "chat") setInitialConversationId(null)
            }}
            className="sol-focusable sol-transition"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sol-space-3)",
              padding: "var(--sol-space-3) var(--sol-space-4)",
              borderRadius: "var(--sol-radius-md)",
              border: "none",
              cursor: "pointer",
              background:
                view === item.id || (view === "project" && item.id === "projects")
                  ? "color-mix(in srgb, var(--sol-gold) 12%, transparent)"
                  : "transparent",
              color:
                view === item.id || (view === "project" && item.id === "projects")
                  ? "var(--sol-gold)"
                  : "var(--sol-text-muted)",
              fontSize: 14,
              fontFamily: "var(--sol-font-ui)",
              textAlign: "left",
              width: "100%",
            }}
          >
            <span style={{ fontSize: 18 }}>{item.icon}</span>
            {item.label}
          </button>
        ))}

        <label className="sol-stack">
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
        <div className="workspace-sidebar-projects">
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
          <button disabled={busy} className="btn-ghost" onClick={() => setView("project")}>
            Abrir projeto atual
          </button>
        )}
        {error && (
          <p role="alert" className="sol-error">
            {error}
          </p>
        )}
        {/* Status do backend */}
        <div
          style={{
            marginTop: "auto",
            padding: "var(--sol-space-3) var(--sol-space-3)",
            fontSize: 12,
            color: "var(--sol-text-muted)",
          }}
        >
          <BackendStatus />
        </div>
      </nav>

      {/* Main content */}
      <main style={{ flex: 1, overflow: "auto", position: "relative" }}>
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
            <h1>Memória · {activeProject?.name ?? "Sem projeto"}</h1>
            <p>
              A busca textual recupera até três trechos de outras conversas do projeto ativo.
              Conversas sem projeto compartilham apenas o contexto sem projeto.
            </p>
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

function BackendStatus() {
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
    <span style={{ display: "flex", alignItems: "center", gap: "var(--sol-space-2)" }}>
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: color,
          display: "inline-block",
        }}
      />
      {label}
    </span>
  )
}
