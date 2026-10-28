import { useState } from "react";
import ChatPage from "./pages/ChatPage";

type View = "chat" | "projects" | "rag" | "vision";

const NAV_ITEMS: { id: View; label: string; icon: string }[] = [
  { id: "projects", label: "Projetos", icon: "⊞" },
  { id: "chat",     label: "Chat",     icon: "◎" },
  { id: "rag",      label: "Memória",  icon: "⊹" },
  { id: "vision",   label: "Visão",    icon: "◉" },
];

function Placeholder({ label }: { label: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "var(--sol-space-4)", color: "var(--sol-text-muted)" }}>
      <span style={{ fontSize: 48, opacity: 0.3 }}>◌</span>
      <p style={{ fontSize: 16 }}>{label} — em breve</p>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("chat");

  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--sol-bg)" }}>
      {/* Sidebar */}
      <nav style={{
        width: 220,
        background: "var(--sol-surface)",
        borderRight: "1px solid var(--sol-border)",
        display: "flex",
        flexDirection: "column",
        padding: "var(--sol-space-6) var(--sol-space-3)",
        gap: "var(--sol-space-2)",
        flexShrink: 0,
      }}>
        {/* Logo */}
        <div style={{
          padding: "var(--sol-space-3) var(--sol-space-3) var(--sol-space-6)",
          fontWeight: 700,
          fontSize: 18,
          background: "var(--sol-sunset)",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          backgroundClip: "text",
          letterSpacing: "0.04em",
        }}>
          SOLARIS
        </div>

        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            onClick={() => setView(item.id)}
            className="sol-focusable sol-transition"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sol-space-3)",
              padding: "var(--sol-space-3) var(--sol-space-4)",
              borderRadius: "var(--sol-radius-md)",
              border: "none",
              cursor: "pointer",
              background: view === item.id ? "rgba(251,185,49,.12)" : "transparent",
              color: view === item.id ? "var(--sol-gold)" : "var(--sol-text-muted)",
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

        {/* Status do backend */}
        <div style={{ marginTop: "auto", padding: "var(--sol-space-3) var(--sol-space-3)", fontSize: 12, color: "var(--sol-text-muted)" }}>
          <BackendStatus />
        </div>
      </nav>

      {/* Main content */}
      <main style={{ flex: 1, overflow: "auto", position: "relative" }}>
        {view === "chat"     && <ChatPage />}
        {view === "projects" && <Placeholder label="Projetos" />}
        {view === "rag"      && <Placeholder label="Memória / RAG" />}
        {view === "vision"   && <Placeholder label="Visão Computacional" />}
      </main>
    </div>
  );
}

function BackendStatus() {
  const [status, setStatus] = useState<"checking" | "ok" | "offline">("checking");

  // Simple health check on mount
  useState(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? setStatus("ok") : setStatus("offline")))
      .catch(() => setStatus("offline"));
  });

  const color = status === "ok" ? "var(--sol-success)" : status === "offline" ? "var(--sol-error)" : "var(--sol-text-muted)";
  const label = status === "ok" ? "Backend online" : status === "offline" ? "Backend offline" : "Verificando…";

  return (
    <span style={{ display: "flex", alignItems: "center", gap: "var(--sol-space-2)" }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: color, display: "inline-block" }} />
      {label}
    </span>
  );
}
