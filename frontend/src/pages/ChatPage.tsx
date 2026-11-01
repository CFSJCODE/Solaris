import { useEffect, useRef, useState, KeyboardEvent, FormEvent } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { invoke } from "@tauri-apps/api/core"
import { ProjectFile, FILE_ACCEPT, uploadProjectFile } from "../projectApi"
import { useChat, ChatMessage, Conversation } from "../hooks/useChat"
import { LiquidSurface } from "../design/LiquidSurface"

// ── Formatting helpers ──────────────────────────────────────────────────────

function formatCost(usd: number): string {
  if (usd === 0) return "grátis"
  if (usd < 0.001) return `$${usd.toFixed(6)}`
  return `$${usd.toFixed(4)}`
}

function providerLabel(provider?: string, model?: string): string {
  if (!provider) return ""
  const shortModel =
    model
      ?.split("/")
      .pop()
      ?.replace(/:free$/, "") ??
    model ??
    ""
  const p = provider === "anthropic" ? "Anthropic" : "OpenRouter"
  return `${p} · ${shortModel}`
}

// ── Sub-components ──────────────────────────────────────────────────────────

function StreamingDots() {
  return (
    <span style={{ display: "inline-flex", gap: 3, alignItems: "center", height: 16 }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 5,
            height: 5,
            borderRadius: "50%",
            background: "var(--sol-flare)",
            animation: `sol-pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </span>
  )
}

interface MessageBubbleProps {
  msg: ChatMessage
  isLast: boolean
  isStreaming: boolean
}

function MessageBubble({ msg, isLast, isStreaming }: MessageBubbleProps) {
  const isUser = msg.role === "user"
  const isEmpty = !msg.content && isStreaming && isLast

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
        gap: 4,
        maxWidth: "100%",
      }}
    >
      <div
        style={{
          maxWidth: isUser ? "70%" : "85%",
          padding: "var(--sol-space-3) var(--sol-space-4)",
          borderRadius: isUser
            ? "var(--sol-radius-lg) var(--sol-radius-lg) var(--sol-radius-sm) var(--sol-radius-lg)"
            : "var(--sol-radius-lg) var(--sol-radius-lg) var(--sol-radius-lg) var(--sol-radius-sm)",
          background: isUser
            ? "var(--sol-sunset)"
            : "var(--sol-optical-surface, var(--sol-surface))",
          border: isUser ? "none" : "1px solid var(--sol-border)",
          color: isUser ? "var(--sol-ink-950)" : "var(--sol-text)",
          fontSize: 14,
          lineHeight: 1.6,
          wordBreak: "break-word",
        }}
      >
        {isEmpty ? (
          <StreamingDots />
        ) : isUser ? (
          <span style={{ whiteSpace: "pre-wrap" }}>{msg.content}</span>
        ) : (
          <div className="sol-md">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => (
                  <a
                    href={href}
                    onClick={(e) => {
                      e.preventDefault()
                      if (href) window.open(href, "_blank")
                    }}
                  >
                    {children}
                  </a>
                ),
              }}
            >
              {msg.content}
            </ReactMarkdown>
            {isLast && isStreaming && (
              <span
                style={{
                  display: "inline-block",
                  width: 2,
                  height: "1em",
                  background: "var(--sol-flare)",
                  marginLeft: 2,
                  verticalAlign: "text-bottom",
                  animation: "sol-blink 0.9s step-end infinite",
                }}
              />
            )}
          </div>
        )}
        {isUser && isLast && isStreaming && msg.content && (
          <span
            style={{
              display: "inline-block",
              width: 2,
              height: "1em",
              background: "rgba(255,255,255,0.8)",
              marginLeft: 2,
              verticalAlign: "text-bottom",
              animation: "sol-blink 0.9s step-end infinite",
            }}
          />
        )}
      </div>

      {!isUser && !!msg.sources?.length && (
        <details className="message-sources">
          <summary>
            Fontes consultadas · {[...new Set(msg.sources.map((s) => s.filename))].join(", ")}
          </summary>
          {msg.sources.map((source, i) => (
            <div key={i}>
              <strong>{source.filename}</strong>
              <small>
                {source.kind === "memory"
                  ? "Memória do projeto"
                  : source.kind === "environment"
                    ? "Perfil de observação do ambiente"
                    : "Arquivo de referência"}{" "}
                · {source.citation}
              </small>
              <p>{source.content}</p>
            </div>
          ))}
        </details>
      )}
      {!isUser &&
        !msg.memoryReport &&
        /vou (salvar|registrar)|salvei|memória atualizada/i.test(msg.content) && (
          <p className="workspace-muted">
            Esta resposta não possui confirmação de gravação da memória.
          </p>
        )}
      {!isUser && msg.memoryReport && (
        <div className={`message-memory-report ${msg.memoryReport.state}`} role="status">
          <strong>
            {msg.memoryReport.state === "saved"
              ? "Memória gravada"
              : msg.memoryReport.state === "unchanged"
                ? "Memória já atualizada"
                : "Memória não gravada"}
          </strong>
          {!!msg.memoryReport.files.length && <span>{msg.memoryReport.files.join(", ")}</span>}
          <p>{msg.memoryReport.detail}</p>
        </div>
      )}
      {/* Model + cost badge for assistant messages */}
      {!isUser && msg.provider && (
        <div
          style={{
            fontSize: 11,
            color: "var(--sol-text-muted)",
            display: "flex",
            gap: "var(--sol-space-3)",
            paddingLeft: 4,
          }}
        >
          <span>{providerLabel(msg.provider, msg.model)}</span>
          {msg.costUsd !== undefined && (
            <span style={{ color: "var(--sol-gold)", opacity: 0.7 }}>
              {formatCost(msg.costUsd)}
            </span>
          )}
          {msg.inputTokens !== undefined && (
            <span>{msg.inputTokens + (msg.outputTokens ?? 0)} tok</span>
          )}
        </div>
      )}
    </div>
  )
}

interface SidebarProps {
  conversations: Conversation[]
  activeId?: number
  onSelect: (id: number) => void
  onNew: () => void
  onDelete: (id: number) => void
}

function ConversationSidebar({ conversations, activeId, onSelect, onNew, onDelete }: SidebarProps) {
  return (
    <aside className="chat-conversations sol-structural" aria-label="Conversas">
      <div style={{ padding: "var(--sol-space-3)", borderBottom: "1px solid var(--sol-border)" }}>
        <button onClick={onNew} className="sol-btn-accent sol-focusable">
          + Nova conversa
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "var(--sol-space-2)" }}>
        {conversations.length === 0 && (
          <p
            style={{
              fontSize: 12,
              color: "var(--sol-text-muted)",
              padding: "var(--sol-space-3)",
              textAlign: "center",
            }}
          >
            Nenhuma conversa
          </p>
        )}
        {conversations.map((conv) => (
          <div key={conv.id} className={`chat-conv-row${conv.id === activeId ? " active" : ""}`}>
            <button
              onClick={() => onSelect(conv.id)}
              aria-current={conv.id === activeId ? "true" : undefined}
              className="sol-focusable sol-transition"
              style={{
                flex: 1,
                padding: "var(--sol-space-2) var(--sol-space-3)",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: conv.id === activeId ? "var(--sol-gold)" : "var(--sol-text)",
                fontSize: 13,
                fontFamily: "var(--sol-font-ui)",
                textAlign: "left",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={conv.title}
            >
              {conv.title}
            </button>
            <button
              onClick={() => onDelete(conv.id)}
              className="chat-conv-delete sol-focusable"
              aria-label={`Apagar conversa ${conv.title}`}
              title="Apagar conversa"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </aside>
  )
}

// ── Main ChatPage ───────────────────────────────────────────────────────────

export default function ChatPage({
  initialConversationId,
  projectId,
  memoryEnabled,
  projects,
  onBusy,
}: {
  initialConversationId: number | null
  projectId: number | null
  memoryEnabled: boolean
  projects: { id: number; name: string }[]
  onBusy: (busy: boolean) => void
}) {
  const {
    error,
    memorySources,
    contextSources,
    memorySaved,
    memoryWarning,
    conversations,
    activeConversation,
    messages,
    isStreaming,
    streamingModel,
    loadConversations,
    loadConversation,
    newConversation,
    deleteConversation,
    sendMessage,
    moveConversation,
  } = useChat(projectId, memoryEnabled)

  const [files, setFiles] = useState<ProjectFile[]>([])
  const [attachmentIds, setAttachmentIds] = useState<number[]>([])
  const [useProjectFiles, setUseProjectFiles] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [fileError, setFileError] = useState("")
  const attachmentInput = useRef<HTMLInputElement>(null)
  const initialLoaded = useRef(false)
  useEffect(() => {
    invoke<ProjectFile[]>("project_list_files", { projectId })
      .then(setFiles)
      .catch((err) => setFileError(String(err)))
  }, [projectId])
  useEffect(() => {
    if (
      initialConversationId &&
      conversations.some((c) => c.id === initialConversationId) &&
      !initialLoaded.current
    ) {
      initialLoaded.current = true
      void loadConversation(initialConversationId)
    }
  }, [initialConversationId, conversations, loadConversation])
  useEffect(() => {
    onBusy(isStreaming || uploading)
    return () => onBusy(false)
  }, [isStreaming, uploading, onBusy])
  async function attach(incoming: FileList | null) {
    if (!incoming) return
    setUploading(true)
    setFileError("")
    const errors: string[] = []
    const ids: number[] = []
    for (const file of Array.from(incoming).slice(0, 12)) {
      try {
        ids.push(await uploadProjectFile(projectId, file))
      } catch (err) {
        errors.push(String(err))
      }
    }
    try {
      setFiles(await invoke<ProjectFile[]>("project_list_files", { projectId }))
      setAttachmentIds((prev) => [...new Set([...prev, ...ids])].slice(0, 12))
    } catch (err) {
      errors.push(String(err))
    }
    setFileError(errors.join("\n"))
    setUploading(false)
  }

  const [input, setInput] = useState("")
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const handleSend = async (e?: FormEvent) => {
    e?.preventDefault()
    const text = input.trim()
    if (!text || isStreaming) return
    setInput("")
    if (textareaRef.current) textareaRef.current.style.height = "auto"
    await sendMessage(text, attachmentIds, useProjectFiles)
    setAttachmentIds([])
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleTextareaInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }

  const handleNew = async () => {
    if (!isStreaming) await newConversation()
  }

  return (
    <>
      {/* CSS animations + markdown styles */}
      <style>{`
        @keyframes sol-pulse {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1); opacity: 1; }
        }
        @keyframes sol-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }

        /* Semantic tokens for markdown — derived from design system, no hardcoded colors */
        :root {
          --sol-md-code-tint: color-mix(in srgb, var(--sol-gold) 12%, transparent);
          --sol-md-code-block: var(--sol-ink-900, #11141B);
          --sol-md-table-head: color-mix(in srgb, var(--sol-gold) 8%, transparent);
          --sol-md-table-stripe: color-mix(in srgb, var(--sol-text) 2%, transparent);
        }

        /* Markdown rendering */
        .sol-md { font-size: 14px; line-height: 1.7; }
        .sol-md > *:first-child { margin-top: 0; }
        .sol-md > *:last-child { margin-bottom: 0; }
        .sol-md p { margin: 0 0 0.6em; }
        .sol-md p:last-child { margin-bottom: 0; }
        .sol-md h1, .sol-md h2, .sol-md h3, .sol-md h4 {
          font-family: var(--sol-font-display);
          color: var(--sol-gold);
          margin: 0.9em 0 0.3em;
          line-height: 1.3;
        }
        .sol-md h1 { font-size: 1.2em; }
        .sol-md h2 { font-size: 1.1em; }
        .sol-md h3 { font-size: 1em; }
        .sol-md strong { font-weight: 600; color: var(--sol-text); }
        .sol-md em { font-style: italic; opacity: 0.9; }
        .sol-md ul, .sol-md ol { margin: 0.4em 0 0.6em 1.4em; padding: 0; }
        .sol-md li { margin: 0.2em 0; }
        .sol-md code {
          font-family: var(--sol-font-mono, monospace);
          font-size: 0.88em;
          padding: 0.15em 0.4em;
          border-radius: 4px;
          background: var(--sol-md-code-tint);
          color: var(--sol-gold);
        }
        .sol-md pre {
          margin: 0.5em 0;
          border-radius: var(--sol-radius-md);
          background: var(--sol-md-code-block);
          border: 1px solid var(--sol-border);
          overflow-x: auto;
        }
        .sol-md pre code {
          display: block;
          padding: 0.8em 1em;
          background: transparent;
          color: var(--sol-text);
          font-size: 0.85em;
          line-height: 1.6;
        }
        .sol-md table {
          border-collapse: collapse;
          width: 100%;
          margin: 0.5em 0;
          font-size: 0.9em;
        }
        .sol-md th, .sol-md td {
          border: 1px solid var(--sol-border);
          padding: 0.35em 0.7em;
          text-align: left;
        }
        .sol-md th {
          background: var(--sol-md-table-head);
          color: var(--sol-gold);
          font-weight: 600;
        }
        .sol-md tr:nth-child(even) td {
          background: var(--sol-md-table-stripe);
        }
        .sol-md blockquote {
          margin: 0.5em 0;
          padding: 0.4em 0.8em;
          border-left: 3px solid var(--sol-gold);
          opacity: 0.8;
          font-style: italic;
        }
        .sol-md hr {
          border: none;
          border-top: 1px solid var(--sol-border);
          margin: 0.8em 0;
        }
        .sol-md a {
          color: var(--sol-flare);
          text-decoration: underline;
          text-underline-offset: 2px;
          cursor: pointer;
        }
      `}</style>

      <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
        <ConversationSidebar
          conversations={conversations}
          activeId={activeConversation?.id}
          onSelect={(id) => {
            if (!isStreaming) void loadConversation(id)
          }}
          onNew={handleNew}
          onDelete={(id) => {
            if (!isStreaming) void deleteConversation(id)
          }}
        />

        {/* Main chat area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div className="chat-scroll">
            {/* Topbar: Functional Glass, conteúdo rola por baixo */}
            <LiquidSurface
              as="header"
              variant="clear"
              refract
              bezel={16}
              strength={40}
              className="sol-topbar"
            >
              <h1 className="sol-topbar-title">{activeConversation?.title ?? "Chat"}</h1>
              {activeConversation && (
                <label>
                  Mover conversa para
                  <select
                    className="project-input"
                    disabled={isStreaming}
                    value={projectId ?? ""}
                    onChange={(e) =>
                      void moveConversation(e.target.value ? Number(e.target.value) : null)
                    }
                  >
                    <option value="">Sem projeto</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {streamingModel && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--sol-space-2)",
                    fontSize: 12,
                    color: "var(--sol-flare)",
                  }}
                >
                  <StreamingDots />
                  <span>{streamingModel}</span>
                </div>
              )}
            </LiquidSurface>

            {error && (
              <p role="alert" className="sol-error">
                {error}
              </p>
            )}
            {memorySources.length > 0 && (
              <details className="sol-memory-sources">
                <summary>Contexto recuperado de {memorySources.length} trechos do projeto</summary>
                {memorySources.map((source, i) => (
                  <div key={i}>
                    <strong>{source.title}</strong>
                    <p>{source.content}</p>
                  </div>
                ))}
              </details>
            )}
            {/* Messages */}
            <div className="chat-messages">
              {messages.length === 0 && !isStreaming && (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    flex: 1,
                    gap: "var(--sol-space-4)",
                    color: "var(--sol-text-muted)",
                  }}
                >
                  <div
                    style={{
                      fontSize: 32,
                      fontWeight: 700,
                      background: "var(--sol-sunset)",
                      WebkitBackgroundClip: "text",
                      WebkitTextFillColor: "transparent",
                      backgroundClip: "text",
                      letterSpacing: "0.08em",
                    }}
                  >
                    SOLARIS
                  </div>
                  <p style={{ fontSize: 15 }}>Olá, como posso ajudar?</p>
                </div>
              )}

              {messages.map((msg, i) => (
                <MessageBubble
                  key={i}
                  msg={msg}
                  isLast={i === messages.length - 1}
                  isStreaming={isStreaming}
                />
              ))}
              <div ref={bottomRef} />
            </div>

            {/* Composer flutuante: Liquid Glass com refração (superfície L3) */}
            <div className="chat-dock">
              <LiquidSurface variant="regular" refract className="chat-composer">
                {(memorySaved.length > 0 || memoryWarning) && (
                  <p role="status" className="chat-context-status">
                    {memoryWarning || `Memórias atualizadas: ${memorySaved.join(", ")}`}
                  </p>
                )}
                {contextSources.length > 0 && isStreaming && (
                  <p className="chat-context-status">
                    Consultando {new Set(contextSources.map((s) => s.filename)).size} arquivos do
                    projeto.
                  </p>
                )}
                {fileError && (
                  <p role="alert" className="workspace-error">
                    {fileError}
                  </p>
                )}
                <div className="chat-attachment-bar">
                  <input
                    ref={attachmentInput}
                    className="sr-only"
                    type="file"
                    multiple
                    accept={FILE_ACCEPT}
                    onChange={(e) => {
                      void attach(e.target.files)
                      e.target.value = ""
                    }}
                  />
                  <button
                    className="btn-ghost"
                    disabled={isStreaming || uploading}
                    onClick={() => attachmentInput.current?.click()}
                  >
                    {uploading ? "Lendo arquivos…" : "Anexar arquivos"}
                  </button>
                  <details>
                    <summary>Arquivos do projeto ({files.length})</summary>
                    <div className="chat-file-picker sol-glass sol-glass--acrylic">
                      {files.map((file) => (
                        <label key={file.id}>
                          <input
                            type="checkbox"
                            disabled={
                              isStreaming ||
                              uploading ||
                              (!attachmentIds.includes(file.id) && attachmentIds.length >= 12)
                            }
                            checked={attachmentIds.includes(file.id)}
                            onChange={(e) =>
                              setAttachmentIds((prev) =>
                                e.target.checked
                                  ? [...prev, file.id]
                                  : prev.filter((id) => id !== file.id),
                              )
                            }
                          />
                          {file.filename}
                        </label>
                      ))}
                      {!files.length && <p>Nenhum arquivo adicionado.</p>}
                    </div>
                  </details>
                  <label>
                    <input
                      type="checkbox"
                      checked={useProjectFiles}
                      disabled={isStreaming}
                      onChange={(e) => setUseProjectFiles(e.target.checked)}
                    />
                    Buscar no projeto
                  </label>
                  {attachmentIds.length > 0 && (
                    <span>{attachmentIds.length} anexo(s) selecionado(s)</span>
                  )}
                </div>
                {/* Input area */}
                <form onSubmit={handleSend} className="chat-composer-row">
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    onInput={handleTextareaInput}
                    placeholder="Mensagem… (Enter para enviar, Shift+Enter nova linha)"
                    rows={1}
                    disabled={isStreaming || uploading}
                    aria-label="Mensagem"
                    className="chat-input sol-focusable"
                  />

                  {isStreaming ? (
                    <button
                      type="button"
                      disabled
                      title="Aguarde a conclusão da resposta"
                      aria-label="Aguarde a conclusão da resposta"
                      className="chat-send busy"
                    >
                      …
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={!input.trim() || uploading}
                      className={`chat-send sol-focusable${input.trim() ? " ready sol-lit" : ""}`}
                      title="Enviar"
                      aria-label="Enviar"
                    >
                      ➤
                    </button>
                  )}
                </form>
              </LiquidSurface>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
