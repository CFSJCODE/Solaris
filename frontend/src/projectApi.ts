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
  kind: "file" | "memory" | "environment" | "folder"
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

// ── Pastas locais ───────────────────────────────────────────────────────────

export interface ProjectFolder {
  id: number
  project_id: number
  path: string
  label: string
  enabled: boolean
  file_count: number
  indexed_count: number
  skipped_count: number
  truncated: boolean
  last_indexed_at: string | null
  created_at: string
}
export interface FolderFile {
  folder_id: number
  rel_path: string
  kind: "text" | "pdf" | "docx"
  byte_size: number
  indexed: boolean
  note: string
}
export interface FolderEdit {
  id: number
  project_id: number
  folder_id: number
  folder_label: string
  rel_path: string
  original: string | null
  proposed: string
  status: "pending" | "applied" | "rejected" | "conflict" | "failed" | "superseded"
  detail: string
  conversation_id: number | null
  message_id: number | null
  created_at: string
  decided_at: string | null
}
export interface IndexReport {
  folder: ProjectFolder
  added: number
  updated: number
  removed: number
  unchanged: number
  unreadable: number
  skipped: number
  truncated: boolean
}

export function describeIndex(report: IndexReport): string {
  const parts = [
    `${report.folder.indexed_count} de ${report.folder.file_count} arquivos com conteúdo indexado`,
  ]
  if (report.added) parts.push(`${report.added} novos`)
  if (report.updated) parts.push(`${report.updated} atualizados`)
  if (report.removed) parts.push(`${report.removed} removidos`)
  if (report.unreadable) parts.push(`${report.unreadable} sem texto legível`)
  if (report.truncated) parts.push("lista limitada a 4.000 arquivos")
  return `${report.folder.label}: ${parts.join(" · ")}.`
}

/** Abre o seletor nativo e vincula a pasta escolhida; `null` quando o usuário cancela. */
export async function attachFolder(projectId: number): Promise<IndexReport | null> {
  const path = await invoke<string | null>("folder_pick")
  if (!path) return null
  return invoke<IndexReport>("folder_attach", { projectId, path })
}

/** Menção inserida no chat para enviar um arquivo inteiro como contexto. */
export function mentionFor(relPath: string): string {
  return /\s/.test(relPath) ? `@"${relPath}"` : `@${relPath}`
}
