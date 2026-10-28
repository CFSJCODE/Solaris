import { useState, useCallback, useRef } from "react"

export interface ChatMessage {
  id?: number
  role: "user" | "assistant"
  content: string
  model?: string
  provider?: string
  inputTokens?: number
  outputTokens?: number
  costUsd?: number
}

export interface Conversation {
  id: number
  title: string
  projectId?: number
  createdAt: string
  updatedAt: string
}

export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingModel, setStreamingModel] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const loadConversations = useCallback(async () => {
    try {
      const res = await fetch("/api/chat/conversations")
      if (res.ok) {
        const data: any[] = await res.json()
        setConversations(
          data.map((c) => ({
            id: c.id,
            title: c.title,
            projectId: c.project_id ?? undefined,
            createdAt: c.created_at,
            updatedAt: c.updated_at,
          }))
        )
      }
    } catch {}
  }, [])

  const loadConversation = useCallback(async (id: number) => {
    try {
      const res = await fetch(`/api/chat/conversations/${id}`)
      if (res.ok) {
        const data = await res.json()
        setActiveConversation({
          id: data.id,
          title: data.title,
          projectId: data.project_id ?? undefined,
          createdAt: data.created_at,
          updatedAt: data.updated_at,
        })
        setMessages(
          data.messages.map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            model: m.model ?? undefined,
            provider: m.provider ?? undefined,
            inputTokens: m.input_tokens,
            outputTokens: m.output_tokens,
            costUsd: m.cost_usd,
          }))
        )
      }
    } catch {}
  }, [])

  const newConversation = useCallback(async (): Promise<Conversation | null> => {
    try {
      const res = await fetch("/api/chat/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "Nova conversa" }),
      })
      if (res.ok) {
        const c = await res.json()
        const conv: Conversation = {
          id: c.id,
          title: c.title,
          projectId: c.project_id ?? undefined,
          createdAt: c.created_at,
          updatedAt: c.updated_at,
        }
        setActiveConversation(conv)
        setMessages([])
        await loadConversations()
        return conv
      }
    } catch {}
    return null
  }, [loadConversations])

  const deleteConversation = useCallback(
    async (id: number) => {
      try {
        await fetch(`/api/chat/conversations/${id}`, { method: "DELETE" })
        if (activeConversation?.id === id) {
          setActiveConversation(null)
          setMessages([])
        }
        await loadConversations()
      } catch {}
    },
    [activeConversation, loadConversations]
  )

  const sendMessage = useCallback(
    async (text: string) => {
      if (isStreaming) return

      let convId = activeConversation?.id
      if (!convId) {
        const conv = await newConversation()
        if (!conv) return
        convId = conv.id
      }

      // Optimistically add user message
      setMessages((prev) => [...prev, { role: "user", content: text }])
      // Placeholder for streaming assistant response
      setMessages((prev) => [...prev, { role: "assistant", content: "" }])
      setIsStreaming(true)

      abortRef.current = new AbortController()

      try {
        const res = await fetch(`/api/chat/conversations/${convId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ conversation_id: convId, message: text }),
          signal: abortRef.current.signal,
        })

        if (!res.ok || !res.body) throw new Error("Stream failed")

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split("\n")
          buffer = lines.pop() ?? ""

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue
            try {
              const ev = JSON.parse(line.slice(6))
              if (ev.type === "model") {
                setStreamingModel(`${ev.provider}/${ev.model}`)
              } else if (ev.type === "delta") {
                setMessages((prev) => {
                  const next = [...prev]
                  const last = next[next.length - 1]
                  next[next.length - 1] = { ...last, content: last.content + ev.text }
                  return next
                })
              } else if (ev.type === "done") {
                setMessages((prev) => {
                  const next = [...prev]
                  next[next.length - 1] = {
                    ...next[next.length - 1],
                    id: ev.message_id,
                    model: ev.usage?.model,
                    provider: ev.usage?.provider,
                    inputTokens: ev.usage?.input_tokens,
                    outputTokens: ev.usage?.output_tokens,
                    costUsd: ev.usage?.cost_usd,
                  }
                  return next
                })
                setStreamingModel(null)
                // Refresh sidebar title
                await loadConversations()
              } else if (ev.type === "error") {
                setMessages((prev) => {
                  const next = [...prev]
                  next[next.length - 1] = {
                    ...next[next.length - 1],
                    content: `Erro: ${ev.message}`,
                  }
                  return next
                })
              }
            } catch {}
          }
        }
      } catch (err: any) {
        if (err.name !== "AbortError") {
          setMessages((prev) => {
            const next = [...prev]
            next[next.length - 1] = {
              ...next[next.length - 1],
              content: "Erro ao conectar com o backend.",
            }
            return next
          })
        }
      } finally {
        setIsStreaming(false)
        setStreamingModel(null)
      }
    },
    [isStreaming, activeConversation, newConversation, loadConversations]
  )

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return {
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
  }
}
