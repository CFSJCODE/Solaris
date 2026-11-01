import { test, expect, type Page } from "@playwright/test"

interface TestState {
  detections: number
  stream: MediaStream | null
  saved: Record<string, unknown> | null
  incorporated?: Record<string, unknown>
  failIncorporation?: boolean
  trained?: boolean
}
type TestWindow = Window & { __visionTest: TestState }

async function prepare(page: Page) {
  await page.addInitScript(() => {
    const state: TestState = { detections: 0, stream: null, saved: null }
    Object.assign(window, {
      __visionTest: state,
      __TAURI_INTERNALS__: {
        invoke: async (command: string, args: Record<string, unknown>) => {
          if (command === "list_projects")
            return [
              {
                id: 1,
                name: "Projeto de teste",
                description: "",
                pinned: false,
                conversation_count: 0,
                file_count: 0,
                updated_at: "2026-10-31",
                created_at: "2026-10-31",
              },
            ]
          if (command === "engine_status")
            return {
              vision: {
                model: "yolo26x",
                model_available: true,
                loaded: true,
                loading: false,
                error: null,
              },
            }
          if (command === "learning_status")
            return {
              enabled: 0,
              runtime_ready: true,
              worker_running: false,
              message: "Aprendizado isolado para teste",
              samples: {},
              jobs: [],
              events: [],
            }
          if (command === "vision_detect") {
            state.detections++
            return {
              model: "yolo26s",
              width: 640,
              height: 480,
              elapsed_ms: 140,
              detections: [
                {
                  class_id: 28,
                  label: "mala",
                  confidence: 0.9,
                  x: 80,
                  y: 80,
                  width: 120,
                  height: 100,
                },
              ],
            }
          }
          if (command === "learning_train_now") {
            state.trained = true
            return { message: "Solicitação registrada para os dois modelos." }
          }
          if (command === "learning_incorporate") {
            if (!state.saved) throw new Error("Revisão não foi salva")
            if (state.failIncorporation) throw new Error("Falha de incorporação simulada")
            state.incorporated = args
            return {
              runtime_ready: true,
              incorporated: 1,
              message: "Solicitação registrada para os dois modelos.",
            }
          }
          if (command === "save_vision_sample") {
            state.saved = args
            return 42
          }
          throw new Error(`Comando inesperado no teste: ${command}`)
        },
      },
    })
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: async () => {
        const canvas = document.createElement("canvas")
        canvas.width = 640
        canvas.height = 480
        const ctx = canvas.getContext("2d")!
        const stream = canvas.captureStream(10)
        state.stream = stream
        const timer = setInterval(() => {
          if (stream.getVideoTracks()[0].readyState === "ended") {
            clearInterval(timer)
            return
          }
          ctx.fillStyle = "#444"
          ctx.fillRect(0, 0, 640, 480)
          ctx.fillStyle = "#aaa"
          ctx.fillRect(80, 80, 120, 100)
        }, 50)
        return stream
      },
    })
  })
  await page.goto("/")
  await page.getByRole("button", { name: "Visão", exact: true }).click()
}

async function draw(page: Page, start: [number, number], end: [number, number]) {
  const layer = page.getByLabel("Área de marcação de objetos", { exact: true })
  await layer.scrollIntoViewIfNeeded()
  const area = await layer.boundingBox()
  if (!area) throw new Error("Área de marcação não encontrada")
  await page.mouse.move(
    area.x + (start[0] / 640) * area.width,
    area.y + (start[1] / 480) * area.height,
  )
  await page.mouse.down()
  await page.mouse.move(
    area.x + (end[0] / 640) * area.width,
    area.y + (end[1] / 480) * area.height,
    { steps: 6 },
  )
  await page.mouse.up()
}

test("freeze releases camera, stops inference, and saves named graphical annotations", async ({
  page,
}) => {
  await prepare(page)
  await page.getByRole("button", { name: "Abrir câmera", exact: true }).click()
  await page.getByRole("button", { name: "Iniciar detecção ao vivo", exact: true }).click()
  await expect
    .poll(() => page.evaluate(() => (window as TestWindow).__visionTest.detections))
    .toBeGreaterThan(0)
  await page.getByRole("button", { name: "Pausar e revisar quadro", exact: true }).click()
  await expect(page.getByRole("heading", { name: "Revisar quadro", exact: true })).toBeVisible()
  expect(
    await page.evaluate(
      () => (window as TestWindow).__visionTest.stream?.getVideoTracks()[0].readyState,
    ),
  ).toBe("ended")
  const requests = await page.evaluate(() => (window as TestWindow).__visionTest.detections)
  await page.waitForTimeout(700)
  expect(await page.evaluate(() => (window as TestWindow).__visionTest.detections)).toBe(requests)

  await draw(page, [320, 240], [500, 400])
  const name = page.getByRole("textbox", { name: "O que é este objeto?" })
  await expect(name).toBeFocused()
  await name.fill("caixa de ferramentas")
  await page
    .getByRole("textbox", { name: "Descrição ou observação (opcional)" })
    .fill("Caixa azul com ferramentas")
  await page.getByRole("button", { name: "Salvar revisão", exact: true }).click()
  await expect(page.getByText(/Revisão 42 salva com imagem, marcações e nomes/)).toBeVisible()
  const saved = await page.evaluate(() => (window as TestWindow).__visionTest.saved)
  expect(saved?.projectId).toBeNull()
  const payload = saved?.payload as {
    detections: {
      label: string
      description?: string
      source?: string
      x: number
      y: number
      width: number
      height: number
    }[]
  }
  expect(payload.detections).toHaveLength(2)
  expect(payload.detections[1]).toMatchObject({
    label: "caixa de ferramentas",
    description: "Caixa azul com ferramentas",
    source: "human",
  })
  expect(payload.detections[1].x).toBeCloseTo(320, 0)
  expect(payload.detections[1].width).toBeCloseTo(180, 0)

  await page.getByRole("button", { name: "Remover esta marcação" }).click()
  await expect(page.getByRole("heading", { name: "Objetos · 1" })).toBeVisible()
  await page.getByRole("button", { name: "Desfazer marcação" }).click()
  await expect(page.getByRole("heading", { name: "Objetos · 2" })).toBeVisible()
  await page.getByRole("combobox", { name: "Projeto ativo" }).selectOption("1")
  await expect(page.getByRole("heading", { name: "Revisar quadro", exact: true })).toHaveCount(0)
})

test("manual capture can draw without running the detector and resume explicitly", async ({
  page,
}) => {
  await prepare(page)
  await page.getByRole("button", { name: "Abrir câmera", exact: true }).click()
  await page.getByRole("button", { name: "Capturar quadro", exact: true }).click()
  await draw(page, [500, 400], [300, 200])
  await expect(page.getByRole("button", { name: "Salvar revisão", exact: true })).toBeDisabled()
  await page.getByRole("textbox", { name: "O que é este objeto?" }).fill("maleta")
  await expect(page.getByRole("button", { name: "Salvar revisão", exact: true })).toBeEnabled()
  expect(await page.evaluate(() => (window as TestWindow).__visionTest.detections)).toBe(0)
  await page.getByRole("button", { name: "Retomar câmera ao vivo", exact: true }).click()
  await expect(page.getByRole("button", { name: "Pausar detecção", exact: true })).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => (window as TestWindow).__visionTest.detections))
    .toBeGreaterThan(0)
})

test("existing boxes can move and resize, while Escape discards an unfinished drawing", async ({
  page,
}) => {
  await prepare(page)
  await page.getByRole("button", { name: "Abrir câmera", exact: true }).click()
  await page.getByRole("button", { name: "Capturar quadro", exact: true }).click()
  await draw(page, [200, 180], [380, 320])
  await page.getByRole("textbox", { name: "O que é este objeto?" }).fill("mala")
  const layer = page.getByLabel("Área de marcação de objetos", { exact: true })
  const area = await layer.boundingBox()
  if (!area) throw new Error("Quadro não encontrado")
  const box = layer.locator("g.selected > rect")
  const start = await box.boundingBox()
  if (!start) throw new Error("Caixa não encontrada")
  await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2)
  await page.mouse.down()
  await page.mouse.move(start.x + start.width / 2 + 30, start.y + start.height / 2 + 20, {
    steps: 5,
  })
  await page.mouse.up()
  expect(Number(await box.getAttribute("x"))).toBeGreaterThan(200)
  const handle = await layer.locator(".sol-annotation-handle.se").boundingBox()
  if (!handle) throw new Error("Canto não encontrado")
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2)
  await page.mouse.down()
  await page.mouse.move(handle.x + handle.width / 2 + 25, handle.y + handle.height / 2 + 20, {
    steps: 5,
  })
  await page.mouse.up()
  expect(Number(await box.getAttribute("width"))).toBeGreaterThan(180)
  await page.getByRole("button", { name: "Desenhar marcação", exact: true }).click()
  await layer.scrollIntoViewIfNeeded()
  const current = await layer.boundingBox()
  if (!current) throw new Error("Quadro não encontrado")
  await page.mouse.move(current.x + 20, current.y + 20)
  await page.mouse.down()
  await page.mouse.move(current.x + 100, current.y + 100)
  await page.keyboard.press("Escape")
  await page.mouse.up()
  await expect(page.getByRole("heading", { name: "Objetos · 1" })).toBeVisible()
  await expect(layer.locator(".sol-annotation-preview")).toHaveCount(0)
})

test("incorporation saves first, carries completeness explicitly and reports partial failure", async ({
  page,
}) => {
  await prepare(page)
  await page.getByRole("button", { name: "Abrir câmera", exact: true }).click()
  await page.getByRole("button", { name: "Capturar quadro", exact: true }).click()
  await draw(page, [100, 100], [240, 280])
  await page.getByRole("textbox", { name: "O que é este objeto?" }).fill("gaveteiro")
  await page
    .getByRole("button", { name: "Incorporar marcação e treinar agora", exact: true })
    .click()
  await expect(page.getByText(/1 marcações incorporadas/)).toBeVisible()
  expect(await page.evaluate(() => (window as TestWindow).__visionTest.incorporated)).toMatchObject(
    { revisionId: 42, complete: false, projectId: null },
  )
  await page.getByRole("checkbox", { name: /Revisei a imagem inteira/ }).check()
  await page.evaluate(() => {
    ;(window as TestWindow).__visionTest.failIncorporation = true
  })
  await page
    .getByRole("button", { name: "Incorporar marcação e treinar agora", exact: true })
    .click()
  await expect(page.getByRole("alert")).toContainText("foi salva, mas a incorporação não concluiu")
})

test("training button explicitly queues both model requests", async ({ page }) => {
  await prepare(page)
  await page.getByRole("button", { name: "Treinar contexto agora", exact: true }).click()
  await expect(page.getByText("Solicitação registrada para os dois modelos.")).toBeVisible()
  expect(await page.evaluate(() => (window as TestWindow).__visionTest.trained)).toBe(true)
})
