import { useState, useCallback, useRef } from "react"
import { invoke } from "@tauri-apps/api/core"
import { Channel } from "@tauri-apps/api/core"

import { ContextSource } from "../projectApi"

export interface MemoryReport {
  state: "saved" | "unchanged" | "failed"
  files: string[]
  detail: string
}

export interface ChatMessage {
  memoryReport?: MemoryReport
  sources?: ContextSource[]
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
export interface MemorySource {
  conversation_id: number
  title: string
  content: string
}

type ChatEvent =
  | { type: "memory"; sources: MemorySource[] }
  | { type: "context"; sources: ContextSource[] }
  | { type: "memory_saved"; files: string[] }
  | { type: "memory_warning"; message: string }
  | { type: "replace"; text: string }
  | { type: "memory_report"; report: MemoryReport }
  | { type: "delta"; text: string }
  | { type: "edit_proposals"; edits: unknown[]; errors: string[] }
  | {
      type: "done"
      usage: {
        model?: string
        provider?: string
        input_tokens?: number
        output_tokens?: number
        cost_usd?: number
      }
    }
  | { type: "error"; message: string }

export function useChat(projectId: number | null, memoryEnabled: boolean) {
  const [contextSources, setContextSources] = useState<ContextSource[]>([])
  const [memorySaved, setMemorySaved] = useState<string[]>([])
  const [memoryWarning, setMemoryWarning] = useState("")
  const [memorySources, setMemorySources] = useState<MemorySource[]>([])
  const [editsVersion, setEditsVersion] = useState(0)
  const requestVersion = useRef(0)
  const sending = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingModel, setStreamingModel] = useState<string | null>(null)

  const loadConversations = useCallback(async () => {
    try {
      const data = await invoke<Conversation[]>("list_conversations", { projectId })
      setConversations(data)
    } catch (err) {
      setError(String(err))
    }
  }, [projectId])

  const loadConversation = useCallback(
    async (id: number) => {
      try {
        const version = ++requestVersion.current
        const msgs = await invoke<
          (ChatMessage & { cost_usd?: number; memory_report?: MemoryReport })[]
        >("get_conversation", { id })
        if (version !== requestVersion.current) return
        const conv = conversations.find((c) => c.id === id) ?? null
        setMemorySources([])
        setActiveConversation(conv)
        setMessages(
          msgs.map((m) => ({
            memoryReport: m.memory_report,
            sources: m.sources,
            id: m.id,
            role: m.role,
            content: m.content,
            model: m.model ?? undefined,
            provider: m.provider ?? undefined,
            costUsd: m.cost_usd ?? undefined,
          })),
        )
      } catch (err) {
        setError(String(err))
      }
    },
    [conversations],
  )

  const newConversation = useCallback(async (): Promise<Conversation | null> => {
    try {
      const id = await invoke<number>("new_conversation", { title: "Nova conversa", projectId })
      await loadConversations()
      const conv: Conversation = {
        id,
        title: "Nova conversa",
        project_id: projectId ?? undefined,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      requestVersion.current++
      setMemorySources([])
      setActiveConversation(conv)
      setMessages([])
      return conv
    } catch (err) {
      setError(String(err))
    }
    return null
  }, [loadConversations, projectId])

  const deleteConversation = useCallback(
    async (id: number) => {
      try {
        await invoke("delete_conversation", { id })
        if (activeConversation?.id === id) {
          requestVersion.current++
          setMemorySources([])
          setActiveConversation(null)
          setMessages([])
        }
        await loadConversations()
      } catch (err) {
        setError(String(err))
      }
    },
    [activeConversation, loadConversations],
  )

  const sendMessage = useCallback(
    async (text: string, attachmentIds: number[] = [], useProjectFiles = true) => {
      if (sending.current) return
      sending.current = true
      setIsStreaming(true)
      setError(null)

      let conv = activeConversation
      if (!conv) {
        conv = await newConversation()
        if (!conv) {
          sending.current = false
          setIsStreaming(false)
          return
        }
      }

      setMemorySources([])
      setContextSources([])
      setMemorySaved([])
      setMemoryWarning("")
      // Optimistic UI
      setMessages((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: "" },
      ])
      setIsStreaming(true)

      try {
        const channel = new Channel<ChatEvent>()
        let runSources: ContextSource[] = []

        channel.onmessage = (event) => {
          if (event.type === "replace") {
            setMessages((prev) =>
              prev.map((m, i) => (i === prev.length - 1 ? { ...m, content: event.text } : m)),
            )
          } else if (event.type === "memory_report") {
            setMessages((prev) =>
              prev.map((m, i) =>
                i === prev.length - 1 ? { ...m, memoryReport: event.report } : m,
              ),
            )
          } else if (event.type === "edit_proposals") {
            setEditsVersion((v) => v + 1)
          } else if (event.type === "context") {
            runSources = event.sources
            setContextSources(event.sources)
          } else if (event.type === "memory_saved") {
            setMemorySaved(event.files)
          } else if (event.type === "memory_warning") {
            setMemoryWarning(event.message)
          } else if (event.type === "memory") {
            setMemorySources(event.sources)
          } else if (event.type === "delta") {
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
                sources: runSources,
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
          memoryEnabled,
          attachmentIds,
          useProjectFiles,
          onEvent: channel,
        })
      } catch (err: unknown) {
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: `Erro ao enviar mensagem: ${String(err)}`,
          }
          return next
        })
      } finally {
        sending.current = false
        setIsStreaming(false)
        setStreamingModel(null)
      }
    },
    [isStreaming, activeConversation, newConversation, loadConversations, memoryEnabled],
  )

  const moveConversation = useCallback(
    async (projectId: number | null) => {
      if (!activeConversation || isStreaming) return
      try {
        await invoke("move_conversation", { id: activeConversation.id, projectId })
        requestVersion.current++
        setMemorySources([])
        setActiveConversation(null)
        setMessages([])
        await loadConversations()
      } catch (err) {
        setError(String(err))
      }
    },
    [activeConversation, isStreaming, loadConversations],
  )

  return {
    editsVersion,
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
  }
}
