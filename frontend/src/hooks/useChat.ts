import { useState, useCallback } from "react"
import { invoke } from "@tauri-apps/api/core"
import { Channel } from "@tauri-apps/api/core"

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
  project_id?: number
  created_at: string
  updated_at: string
}

// Events emitted by the Rust chat_send command via Channel
type ChatEvent =
  | { type: "delta"; text: string }
  | { type: "done"; usage: { model?: string; provider?: string; input_tokens?: number; output_tokens?: number; cost_usd?: number } }
  | { type: "error"; message: string }

export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingModel, setStreamingModel] = useState<string | null>(null)

  const loadConversations = useCallback(async () => {
    try {
      const data = await invoke<Conversation[]>("list_conversations")
      setConversations(data)
    } catch {}
  }, [])

  const loadConversation = useCallback(async (id: number) => {
    try {
      const msgs = await invoke<ChatMessage[]>("get_conversation", { id })
      const conv = conversations.find((c) => c.id === id) ?? null
      setActiveConversation(conv)
      setMessages(
        msgs.map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          model: m.model ?? undefined,
          provider: m.provider ?? undefined,
          costUsd: m.cost_usd ?? undefined,
        }))
      )
    } catch {}
  }, [conversations])

  const newConversation = useCallback(async (): Promise<Conversation | null> => {
    try {
      const id = await invoke<number>("new_conversation", { title: "Nova conversa", projectId: null })
      await loadConversations()
      const conv: Conversation = {
        id,
        title: "Nova conversa",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      setActiveConversation(conv)
      setMessages([])
      return conv
    } catch {}
    return null
  }, [loadConversations])

  const deleteConversation = useCallback(
    async (id: number) => {
      try {
        await invoke("delete_conversation", { id })
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

      let conv = activeConversation
      if (!conv) {
        conv = await newConversation()
        if (!conv) return
      }

      // Optimistic UI
      setMessages((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: "" },
      ])
      setIsStreaming(true)

      try {
        const channel = new Channel<ChatEvent>()

        channel.onmessage = (event) => {
          if (event.type === "delta") {
            setMessages((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              next[next.length - 1] = { ...last, content: last.content + event.text }
              return next
            })
          } else if (event.type === "done") {
            const u = event.usage
            if (u.model) setStreamingModel(`${u.provider ?? ""}/${u.model}`)
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = {
                ...next[next.length - 1],
                model: u.model,
                provider: u.provider,
                inputTokens: u.input_tokens,
                outputTokens: u.output_tokens,
                costUsd: u.cost_usd,
              }
              return next
            })
            setStreamingModel(null)
            loadConversations()
          } else if (event.type === "error") {
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = {
                ...next[next.length - 1],
                content: `Erro: ${event.message}`,
              }
              return next
            })
          }
        }

        await invoke("chat_send", {
          conversationId: conv.id,
          message: text,
          model: null,
          provider: null,
          onEvent: channel,
        })
      } catch (err: any) {
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: "Erro ao enviar mensagem.",
          }
          return next
        })
      } finally {
        setIsStreaming(false)
        setStreamingModel(null)
      }
    },
    [isStreaming, activeConversation, newConversation, loadConversations]
  )

  const stopStreaming = useCallback(() => {
    // Tauri channels don't have a cancel mechanism at the hook level;
    // the command completes naturally. This is a no-op placeholder.
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
