import { useEffect, useRef, useState, KeyboardEvent, FormEvent } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { useChat, ChatMessage, Conversation } from "../hooks/useChat"

// ── Formatting helpers ──────────────────────────────────────────────────────

function formatCost(usd: number): string {
  if (usd === 0) return "grátis"
  if (usd < 0.001) return `$${usd.toFixed(6)}`
  return `$${usd.toFixed(4)}`
}

function providerLabel(provider?: string, model?: string): string {
  if (!provider) return ""
  const shortModel = model?.split("/").pop()?.replace(/:free$/, "") ?? model ?? ""
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
          maxWidth: "70%",
          padding: "var(--sol-space-3) var(--sol-space-4)",
          borderRadius: isUser
            ? "var(--sol-radius-lg) var(--sol-radius-lg) var(--sol-radius-sm) var(--sol-radius-lg)"
            : "var(--sol-radius-lg) var(--sol-radius-lg) var(--sol-radius-lg) var(--sol-radius-sm)",
          background: isUser ? "var(--sol-sunset)" : "var(--sol-optical-surface, var(--sol-surface))",
          border: isUser ? "none" : "1px solid var(--sol-border)",
          color: isUser ? "#fff" : "var(--sol-text)",
          fontSize: 14,
          lineHeight: 1.6,
          whiteSpace: isUser ? "pre-wrap" : "normal",
          wordBreak: "break-word",
        }}
      >
        {isEmpty ? (
          <StreamingDots />
        ) : isUser ? (
          msg.content
        ) : (
          <div className="sol-md">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
              }}
            >
              {msg.content}
            </ReactMarkdown>
          </div>
        )}
        {isLast && isStreaming && msg.content && (
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
    <aside
      style={{
        width: 220,
        flexShrink: 0,
        background: "var(--sol-surface)",
        borderRight: "1px solid var(--sol-border)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div style={{ padding: "var(--sol-space-3)", borderBottom: "1px solid var(--sol-border)" }}>
        <button
          onClick={onNew}
          className="sol-focusable sol-transition"
          style={{
            width: "100%",
            padding: "var(--sol-space-2) var(--sol-space-3)",
            background: "var(--sol-sunset)",
            border: "none",
            borderRadius: "var(--sol-radius-md)",
            color: "#fff",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: "var(--sol-font-ui)",
          }}
        >
          + Nova conversa
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "var(--sol-space-2)" }}>
        {conversations.length === 0 && (
          <p style={{ fontSize: 12, color: "var(--sol-text-muted)", padding: "var(--sol-space-3)", textAlign: "center" }}>
            Nenhuma conversa
          </p>
        )}
        {conversations.map((conv) => (
          <div
            key={conv.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 2,
              borderRadius: "var(--sol-radius-md)",
              background: conv.id === activeId ? "rgba(251,185,49,.10)" : "transparent",
            }}
          >
            <button
              onClick={() => onSelect(conv.id)}
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
              className="sol-focusable sol-transition"
              style={{
                padding: "var(--sol-space-1) var(--sol-space-2)",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: "var(--sol-text-muted)",
                fontSize: 12,
                opacity: 0,
                transition: "opacity var(--sol-duration-fast)",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
              onMouseLeave={(e) => (e.currentTarget.style.opacity = "0")}
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

export default function ChatPage() {
  const {
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
    stopStreaming,
  } = useChat()

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
    await sendMessage(text)
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
    await newConversation()
  }

  return (
    <>
      {/* CSS animations */}
      <style>{`
        @keyframes sol-pulse {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1); opacity: 1; }
        }
        @keyframes sol-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        .sol-md > :first-child { margin-top: 0; }
        .sol-md > :last-child { margin-bottom: 0; }
        .sol-md p, .sol-md ul, .sol-md ol, .sol-md pre, .sol-md table, .sol-md blockquote { margin: var(--sol-space-2) 0; }
        .sol-md h1, .sol-md h2, .sol-md h3, .sol-md h4 { margin: var(--sol-space-4) 0 var(--sol-space-2); font-weight: 600; line-height: 1.3; }
        .sol-md h1 { font-size: 18px; }
        .sol-md h2 { font-size: 16px; }
        .sol-md h3, .sol-md h4 { font-size: 14px; }
        .sol-md ul, .sol-md ol { padding-left: var(--sol-space-6); }
        .sol-md li + li { margin-top: var(--sol-space-1); }
        .sol-md strong { font-weight: 600; color: var(--sol-glow); }
        .sol-md a { color: var(--sol-gold); }
        .sol-md code { font-family: var(--sol-font-mono); font-size: 13px; background: var(--sol-ink-900); border: 1px solid var(--sol-border); border-radius: var(--sol-radius-sm); padding: 0 var(--sol-space-1); }
        .sol-md pre { background: var(--sol-ink-950); border: 1px solid var(--sol-border); border-radius: var(--sol-radius-md); padding: var(--sol-space-3); overflow-x: auto; }
        .sol-md pre code { background: none; border: none; padding: 0; }
        .sol-md blockquote { border-left: 3px solid var(--sol-flare); padding-left: var(--sol-space-3); color: var(--sol-text-muted); }
        .sol-md table { border-collapse: collapse; display: block; overflow-x: auto; max-width: 100%; }
        .sol-md th, .sol-md td { border: 1px solid var(--sol-border); padding: var(--sol-space-1) var(--sol-space-3); text-align: left; vertical-align: top; }
        .sol-md th { background: var(--sol-ink-800); font-weight: 600; }
        .sol-md hr { border: none; border-top: 1px solid var(--sol-border); margin: var(--sol-space-4) 0; }
      `}</style>

      <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
        <ConversationSidebar
          conversations={conversations}
          activeId={activeConversation?.id}
          onSelect={loadConversation}
          onNew={handleNew}
          onDelete={deleteConversation}
        />

        {/* Main chat area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {/* Header */}
          <div style={{
            padding: "var(--sol-space-3) var(--sol-space-6)",
            borderBottom: "1px solid var(--sol-border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--sol-surface)",
            flexShrink: 0,
          }}>
            <div>
              <span style={{ fontSize: 14, fontWeight: 600, color: "var(--sol-text)" }}>
                {activeConversation?.title ?? "Chat"}
              </span>
            </div>
            {streamingModel && (
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--sol-space-2)",
                fontSize: 12,
                color: "var(--sol-flare)",
              }}>
                <StreamingDots />
                <span>{streamingModel}</span>
              </div>
            )}
          </div>

          {/* Messages */}
          <div style={{
            flex: 1,
            overflowY: "auto",
            padding: "var(--sol-space-6)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--sol-space-4)",
          }}>
            {messages.length === 0 && !isStreaming && (
              <div style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                flex: 1,
                gap: "var(--sol-space-4)",
                color: "var(--sol-text-muted)",
              }}>
                <div style={{
                  fontSize: 32,
                  fontWeight: 700,
                  background: "var(--sol-sunset)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                  letterSpacing: "0.08em",
                }}>
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

          {/* Input area */}
          <form
            onSubmit={handleSend}
            style={{
              padding: "var(--sol-space-4) var(--sol-space-6)",
              borderTop: "1px solid var(--sol-border)",
              background: "var(--sol-surface)",
              display: "flex",
              gap: "var(--sol-space-3)",
              alignItems: "flex-end",
              flexShrink: 0,
            }}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onInput={handleTextareaInput}
              placeholder="Mensagem… (Enter para enviar, Shift+Enter nova linha)"
              rows={1}
              disabled={isStreaming}
              className="sol-focusable"
              style={{
                flex: 1,
                resize: "none",
                padding: "var(--sol-space-3) var(--sol-space-4)",
                borderRadius: "var(--sol-radius-lg)",
                border: "1px solid var(--sol-border)",
                background: "var(--sol-bg)",
                color: "var(--sol-text)",
                fontSize: 14,
                fontFamily: "var(--sol-font-ui)",
                lineHeight: 1.5,
                outline: "none",
                minHeight: 42,
                maxHeight: 180,
                overflowY: "auto",
                transition: "border-color var(--sol-duration-fast)",
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = "var(--sol-gold)"
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = "var(--sol-border)"
              }}
            />

            {isStreaming ? (
              <button
                type="button"
                onClick={stopStreaming}
                className="sol-focusable sol-transition"
                title="Parar"
                style={{
                  width: 42,
                  height: 42,
                  flexShrink: 0,
                  borderRadius: "var(--sol-radius-lg)",
                  border: "1px solid var(--sol-error)",
                  background: "transparent",
                  color: "var(--sol-error)",
                  cursor: "pointer",
                  fontSize: 16,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                ◼
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                className="sol-focusable sol-transition"
                title="Enviar"
                style={{
                  width: 42,
                  height: 42,
                  flexShrink: 0,
                  borderRadius: "var(--sol-radius-lg)",
                  border: "none",
                  background: input.trim() ? "var(--sol-sunset)" : "var(--sol-border)",
                  color: input.trim() ? "#fff" : "var(--sol-text-muted)",
                  cursor: input.trim() ? "pointer" : "default",
                  fontSize: 16,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "background var(--sol-duration-fast), color var(--sol-duration-fast)",
                }}
              >
                ➤
              </button>
            )}
          </form>
        </div>
      </div>
    </>
  )
}
