import { test, expect, type Page } from "@playwright/test"

interface FolderTestState {
  attached: boolean
  decided: { editId: number; approve: boolean } | null
  mentionRead: string | null
}
type TestWindow = Window & { __folderTest: FolderTestState }

async function prepare(page: Page) {
  await page.addInitScript(() => {
    const state: FolderTestState = { attached: false, decided: null, mentionRead: null }
    const folder = {
      id: 7,
      project_id: 1,
      path: "D:\\Robos\\seguidor",
      label: "seguidor",
      enabled: true,
      file_count: 3,
      indexed_count: 3,
      skipped_count: 2,
      truncated: false,
      last_indexed_at: "2026-11-01 00:40:00",
      created_at: "2026-11-01 00:40:00",
    }
    const files = [
      {
        folder_id: 7,
        rel_path: "README.md",
        kind: "text",
        byte_size: 820,
        indexed: true,
        note: "",
      },
      {
        folder_id: 7,
        rel_path: "src/main.cpp",
        kind: "text",
        byte_size: 4096,
        indexed: true,
        note: "",
      },
      {
        folder_id: 7,
        rel_path: "src/pid.h",
        kind: "text",
        byte_size: 512,
        indexed: true,
        note: "",
      },
    ]
    const edit = {
      id: 3,
      project_id: 1,
      folder_id: 7,
      folder_label: "seguidor",
      rel_path: "src/pid.h",
      original: "#pragma once\nfloat kp = 1.0;\nfloat ki = 0.0;\n",
      proposed: "#pragma once\nfloat kp = 1.8;\nfloat ki = 0.05;\nfloat kd = 0.2;\n",
      status: "pending",
      detail: "",
      conversation_id: 1,
      message_id: 2,
      created_at: "2026-11-01 00:41:00",
      decided_at: null,
    }
    Object.assign(window, {
      __folderTest: state,
      __TAURI_INTERNALS__: {
        invoke: async (command: string, args: Record<string, unknown>) => {
          if (command === "list_projects")
            return [
              {
                id: 1,
                name: "Robô seguidor",
                description: "",
                instructions: "",
                pinned: false,
                conversation_count: 0,
                file_count: 0,
                updated_at: "2026-11-01",
                created_at: "2026-11-01",
              },
            ]
          if (command === "folder_list") return state.attached ? [folder] : []
          if (command === "folder_pick") return "D:\\Robos\\seguidor"
          if (command === "folder_attach") {
            state.attached = true
            return {
              folder,
              added: 3,
              updated: 0,
              removed: 0,
              unchanged: 0,
              unreadable: 0,
              skipped: 2,
              truncated: false,
            }
          }
          if (command === "folder_files")
            return files.filter((f) => f.rel_path.includes(String(args.filter ?? "")))
          if (command === "folder_read") {
            state.mentionRead = String(args.relPath)
            return "#pragma once\nfloat kp = 1.0;\n"
          }
          if (command === "folder_edits")
            return state.attached
              ? [{ ...edit, status: state.decided ? "applied" : "pending" }]
              : []
          if (command === "folder_edit_decide") {
            state.decided = { editId: Number(args.editId), approve: Boolean(args.approve) }
            return { ...edit, status: "applied", detail: "Gravado." }
          }
          if (command === "engine_status") return { vision: { loaded: false } }
          if (command === "learning_status")
            return { enabled: 0, samples: {}, jobs: [], events: [] }
          return []
        },
        transformCallback: () => 1,
      },
    })
  })
}

test("anexa pasta, navega nos arquivos e aprova uma edição com diff", async ({ page }) => {
  await prepare(page)
  await page.goto("/")
  await page
    .getByRole("button", { name: /Robô seguidor/ })
    .first()
    .click()
  await page.getByRole("button", { name: "Pastas locais" }).click()
  await page.getByRole("button", { name: "Anexar pasta" }).click()
  await expect(page.locator(".workspace-notice")).toContainText("seguidor: 3 de 3 arquivos")
  await expect(page.locator(".folder-tree-path", { hasText: "src/main.cpp" })).toBeVisible()
  await page.getByPlaceholder("Filtrar arquivos de seguidor").fill("pid")
  await expect(page.locator(".folder-tree-path", { hasText: "src/main.cpp" })).toHaveCount(0)
  await page.locator(".folder-tree-open", { hasText: "src/pid.h" }).click()
  await expect(page.locator(".file-preview")).toContainText("kp = 1.0")
  await page.getByRole("button", { name: "Fechar" }).click()
  await page.getByRole("button", { name: "Revisar" }).click()
  await expect(page.locator(".edit-diff-line.add")).toHaveCount(3)
  await expect(page.locator(".edit-diff-line.del")).toHaveCount(2)
  await page.getByRole("button", { name: "Aprovar e gravar" }).click()
  await expect
    .poll(() => page.evaluate(() => (window as unknown as TestWindow).__folderTest.decided))
    .toEqual({ editId: 3, approve: true })
  await expect(page.locator(".edit-status.applied")).toBeVisible()
})
