import { invoke } from "@tauri-apps/api/core"

export interface Project {
  id: number
  name: string
  description: string | null
  instructions: string
  pinned: boolean
  conversation_count: number
  file_count: number
  created_at: string
  updated_at: string
}
export interface ProjectFile {
  id: number
  filename: string
  mime_type: string
  byte_size: number
  enabled: boolean
  chunk_count: number
  created_at: string
}
export interface MemoryFile {
  name: string
  content: string
  revision: string
}
export interface ContextSource {
  kind: "file" | "memory" | "environment"
  document_id: number | null
  filename: string
  citation: string
  content: string
}

export const FILE_ACCEPT =
  ".md,.txt,.pdf,.docx,.csv,.json,.py,.rs,.ts,.tsx,.js,.jsx,.sql,.html,.css,.yaml,.yml,.xml,.log"

export async function uploadProjectFile(projectId: number | null, file: File): Promise<number> {
  if (file.size > 10_000_000) throw new Error(`${file.name}: máximo de 10 MB por arquivo.`)
  const extension = file.name.toLowerCase().split(".").pop() ?? ""
  if (!FILE_ACCEPT.split(",").includes(`.${extension}`))
    throw new Error(`${file.name}: formato não suportado.`)
  const contentB64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(",")[1])
    reader.onerror = () => reject(new Error(`Não foi possível ler ${file.name}.`))
    reader.readAsDataURL(file)
  })
  const mimeType =
    extension === "pdf"
      ? "application/pdf"
      : extension === "docx"
        ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        : "text/plain"
  return invoke<number>("project_upload_file", {
    projectId,
    filename: file.name,
    mimeType,
    contentB64,
  })
}

export function formatDate(value: string): string {
  const date = new Date(value.includes("T") ? value : `${value.replace(" ", "T")}Z`)
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })
}
