import { useEffect, useRef, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import LearningPanel from "../components/LearningPanel"
import VisionAnnotationEditor, { type Detection } from "../components/VisionAnnotationEditor"

interface Result {
  model_warning?: string | null
  learning_warning?: string
  environment?: {
    frames: number
    stable_count: number
    recurring: string[]
    context?: { hypothesis: string; kind: string }
    warning: string | null
  }
  model: string
  detections: Detection[]
  width: number
  height: number
  elapsed_ms: number
}

export default function VisionPage({ projectId }: { projectId: number | null }) {
  const [live, setLive] = useState(false)
  const [liveResult, setLiveResult] = useState<Result | null>(null)
  const [targetRate, setTargetRate] = useState(3)
  const [liveRate, setLiveRate] = useState(0)
  const [roundTrip, setRoundTrip] = useState(0)
  const liveGeneration = useRef(0)
  const livePending = useRef(false)
  const liveFrame = useRef<{ image: string; data: Result } | null>(null)
  const [image, setImage] = useState("")
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [busy, setBusy] = useState(false)
  const [camera, setCamera] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [completeReview, setCompleteReview] = useState(false)
  const [learningRevision, setLearningRevision] = useState(0)
  const [modelStatus, setModelStatus] = useState<{
    model: string
    loaded: boolean
    loading: boolean
    error: string | null
  } | null>(null)
  const [available, setAvailable] = useState<boolean | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const media = useRef<MediaStream | null>(null)
  const version = useRef(0)
  const alive = useRef(true)
  const cameraVersion = useRef(0)

  useEffect(() => {
    alive.current = true
    async function refresh() {
      try {
        const r = await invoke<{
          vision: {
            model_available: boolean
            model: string
            loaded: boolean
            loading: boolean
            error: string | null
          }
        }>("engine_status")
        if (alive.current) {
          setAvailable(r.vision.model_available)
          setModelStatus(r.vision)
          if (r.vision.loaded || r.vision.error) clearInterval(poll)
        }
      } catch (err) {
        if (alive.current) setError(String(err))
      }
    }
    const poll = setInterval(() => void refresh(), 1500)
    void refresh()
    return () => {
      clearInterval(poll)
      liveGeneration.current++
      alive.current = false
      cameraVersion.current++
      version.current++
      media.current?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  useEffect(() => {
    const generation = ++liveGeneration.current
    let timer: ReturnType<typeof setTimeout> | undefined
    let lastCompletion = 0
    async function tick() {
      if (!live || !camera || !alive.current || generation !== liveGeneration.current) return
      const source = video.current
      if (document.hidden || livePending.current || !source?.videoWidth) {
        timer = setTimeout(() => void tick(), 300)
        return
      }
      livePending.current = true
      const started = performance.now()
      try {
        const canvas = document.createElement("canvas")
        const scale = Math.min(1, 640 / source.videoWidth)
        canvas.width = Math.round(source.videoWidth * scale)
        canvas.height = Math.round(source.videoHeight * scale)
        const ctx = canvas.getContext("2d")
        if (!ctx) throw new Error("Captura de vídeo indisponível.")
        ctx.drawImage(source, 0, 0, canvas.width, canvas.height)
        const frame = canvas.toDataURL("image/jpeg", 0.8)
        const data = await invoke<Result>("vision_detect", {
          contentB64: frame.split(",")[1],
          projectId,
          adapt: true,
        })
        if (alive.current && generation === liveGeneration.current) {
          const now = performance.now()
          setLiveResult(data)
          setRoundTrip(now - started)
          if (lastCompletion) setLiveRate(1000 / (now - lastCompletion))
          lastCompletion = now
          liveFrame.current = { image: frame, data }
        }
      } catch (err) {
        if (alive.current && generation === liveGeneration.current) {
          setLive(false)
          setError(`Detecção contínua pausada: ${String(err)}`)
        }
      } finally {
        livePending.current = false
      }
      if (alive.current && generation === liveGeneration.current)
        timer = setTimeout(
          () => void tick(),
          Math.max(0, 1000 / targetRate - (performance.now() - started)),
        )
    }
    if (!live) setLiveResult(null)
    if (live && camera) void tick()
    return () => {
      liveGeneration.current++
      if (timer) clearTimeout(timer)
    }
  }, [live, camera, targetRate, projectId])

  useEffect(() => {
    stopCamera()
    version.current++
    setImage("")
    setResult(null)
    setReviewing(false)
    setCompleteReview(false)
    setNotice("")
    setError("")
  }, [projectId])

  function freezeLive() {
    const frame = liveFrame.current
    if (!frame) return
    stopCamera()
    version.current++
    setCompleteReview(false)
    setImage(frame.image)
    setResult({ ...frame.data, detections: frame.data.detections.map((box) => ({ ...box })) })
    setReviewing(true)
    setNotice(
      "Captura interrompida. Desenhe uma marcação ou selecione uma caixa para escrever o nome do objeto.",
    )
    setError("")
    requestAnimationFrame(() =>
      document
        .getElementById("vision-review")
        ?.scrollIntoView({ block: "start", behavior: "auto" }),
    )
  }

  function stopCamera() {
    liveGeneration.current++
    setLive(false)
    setLiveResult(null)
    liveFrame.current = null
    setLiveRate(0)
    cameraVersion.current++
    media.current?.getTracks().forEach((track) => track.stop())
    media.current = null
    if (video.current) video.current.srcObject = null
    setCamera(false)
  }

  async function startCamera(resumeLive = false) {
    setCompleteReview(false)
    const token = ++cameraVersion.current
    try {
      setError("")
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 },
        audio: false,
      })
      if (!alive.current || token !== cameraVersion.current) {
        stream.getTracks().forEach((t) => t.stop())
        return
      }
      media.current = stream
      if (video.current) {
        video.current.srcObject = stream
        await video.current.play()
      }
      setCamera(true)
      setReviewing(false)
      if (resumeLive && modelStatus?.loaded) {
        setLiveRate(0)
        setLive(true)
      }
    } catch (err) {
      if (token !== cameraVersion.current) return
      media.current?.getTracks().forEach((track) => track.stop())
      media.current = null
      if (alive.current) {
        setCamera(false)
        setError(`Não foi possível abrir a câmera: ${String(err)}`)
      }
    }
  }

  function capture() {
    const source = video.current
    if (!source?.videoWidth) return
    const canvas = document.createElement("canvas")
    canvas.width = source.videoWidth
    canvas.height = source.videoHeight
    canvas.getContext("2d")?.drawImage(source, 0, 0)
    const frame = canvas.toDataURL("image/jpeg", 0.9)
    stopCamera()
    setCompleteReview(false)
    version.current++
    setImage(frame)
    setResult({
      width: canvas.width,
      height: canvas.height,
      model: "marcação manual",
      elapsed_ms: 0,
      detections: [],
    })
    setReviewing(true)
    setNotice("Captura interrompida. Arraste sobre o objeto para marcá-lo e escreva o nome.")
    setError("")
    requestAnimationFrame(() =>
      document
        .getElementById("vision-review")
        ?.scrollIntoView({ block: "start", behavior: "auto" }),
    )
  }

  async function loadFile(file?: File) {
    if (!file) return
    stopCamera()
    setCompleteReview(false)
    const current = ++version.current
    setResult(null)
    setImage("")
    setNotice("")
    setError("")
    if (!["image/png", "image/jpeg"].includes(file.type) || file.size > 12_000_000) {
      setError("Escolha uma imagem PNG ou JPEG de até 12 MB.")
      return
    }
    const reader = new FileReader()
    reader.onerror = () => setError("Não foi possível ler a imagem.")
    reader.onload = () => {
      const content = String(reader.result)
      const decoded = new Image()
      decoded.onload = () => {
        if (alive.current && current === version.current) {
          if (decoded.naturalWidth * decoded.naturalHeight > 20_000_000) {
            setError("Use uma imagem de até 20 megapixels.")
            return
          }
          setImage(content)
          setResult({
            width: decoded.naturalWidth,
            height: decoded.naturalHeight,
            model: "marcação manual",
            elapsed_ms: 0,
            detections: [],
          })
          setReviewing(true)
        }
      }
      decoded.onerror = () => {
        if (alive.current && current === version.current)
          setError("Não foi possível abrir esta imagem.")
      }
      decoded.src = content
    }
    reader.readAsDataURL(file)
  }

  async function detect() {
    const current = version.current
    setBusy(true)
    setError("")
    setNotice("")
    setCompleteReview(false)
    try {
      const data = await invoke<Result>("vision_detect", {
        contentB64: image.split(",")[1],
        projectId,
      })
      if (alive.current && current === version.current) setResult(data)
    } catch (err) {
      if (alive.current) setError(String(err))
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  async function save(learnNow = false) {
    if (!result || camera || live || result.detections.some((box) => !box.label.trim())) return
    const current = version.current
    setBusy(true)
    setError("")
    setNotice("")
    try {
      const id = await invoke<number>("save_vision_sample", {
        projectId,
        payload: {
          image,
          ...result,
          detections: result.detections.map((box) => ({
            ...box,
            label: box.label.trim(),
            description: box.description?.trim(),
          })),
          model: result.model,
          review: "human_corrected",
          schema_version: 2,
        },
      })
      if (learnNow) {
        try {
          const receipt = await invoke<{
            message: string
            runtime_ready: boolean
            incorporated: number
          }>("learning_incorporate", { projectId, revisionId: id, complete: completeReview })
          if (alive.current && current === version.current) {
            setNotice(
              `Revisão ${id} salva; ${receipt.incorporated} marcações incorporadas. ${receipt.message}${receipt.runtime_ready ? "" : " O motor de aprendizado precisa estar preparado."}`,
            )
            setLearningRevision((value) => value + 1)
          }
        } catch (err) {
          if (alive.current && current === version.current)
            setError(`A revisão ${id} foi salva, mas a incorporação não concluiu: ${String(err)}`)
        }
      } else if (alive.current && current === version.current)
        setNotice(
          `Revisão ${id} salva com imagem, marcações e nomes dos objetos. Salvar não inicia um treinamento imediato.`,
        )
    } catch (err) {
      if (alive.current && current === version.current) setError(String(err))
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  return (
    <section className="sol-page sol-stack">
      <h1>Visão computacional</h1>
      <p>Detecção local em CPU. Imagens e capturas permanecem no computador.</p>
      <LearningPanel
        key={projectId ?? "general"}
        projectId={projectId}
        refreshRevision={learningRevision}
      />
      <p role="status">
        Modelo: <strong>{modelStatus?.model ?? "Verificando…"}</strong> · CPU ·{" "}
        {modelStatus?.error
          ? `Falha no carregamento: ${modelStatus.error}`
          : modelStatus?.loaded
            ? "Carregado"
            : "Carregando o maior detector instalado…"}
      </p>
      {available === false && (
        <p role="status">
          Modelo de detecção não encontrado. Verifique a instalação do SOLARIS antes de detectar
          objetos.
        </p>
      )}
      <div className="sol-toolbar">
        <label className="btn-ghost">
          Abrir imagem
          <input
            aria-label="Escolher imagem"
            type="file"
            accept="image/png,image/jpeg"
            disabled={busy}
            onChange={(e) => void loadFile(e.target.files?.[0])}
          />
        </label>
        <button
          className="btn-ghost"
          disabled={busy}
          onClick={() => (camera ? stopCamera() : void startCamera(reviewing))}
        >
          {camera ? "Desligar câmera" : reviewing ? "Retomar câmera ao vivo" : "Abrir câmera"}
        </button>
        <button className="btn-ghost" disabled={!camera || busy || live} onClick={capture}>
          Capturar quadro
        </button>
        <button
          className="btn-primary"
          disabled={
            !image ||
            busy ||
            live ||
            camera ||
            result?.detections.some((box) => box.source === "human")
          }
          onClick={() => void detect()}
        >
          {busy ? "Processando…" : "Detectar objetos"}
        </button>
      </div>
      {camera && (
        <div className="sol-toolbar">
          <button
            className="btn-primary"
            disabled={busy || available === false || !modelStatus?.loaded}
            onClick={() => {
              setError("")
              setLiveRate(0)
              setLive(!live)
            }}
          >
            {live ? "Pausar detecção" : "Iniciar detecção ao vivo"}
          </button>
          <label>
            Limite de detecções por segundo
            <select
              className="project-input"
              value={targetRate}
              onChange={(e) => setTargetRate(Number(e.target.value))}
            >
              {[1, 3, 5, 10].map((rate) => (
                <option value={rate} key={rate}>
                  {rate}/s
                </option>
              ))}
            </select>
          </label>
          <button className="btn-ghost" disabled={!liveFrame.current || busy} onClick={freezeLive}>
            Pausar e revisar quadro
          </button>
          <span role="status">
            {live
              ? `${liveRate.toFixed(1)} detecções/s · ${roundTrip.toFixed(0)} ms no fluxo completo`
              : "Detecção contínua pausada"}
          </span>
        </div>
      )}
      {liveResult?.environment && (
        <p role="status">
          Adaptação do ambiente: {liveResult.environment.frames} quadros observados ·{" "}
          {liveResult.environment.stable_count} objetos estáveis · recorrentes:{" "}
          {liveResult.environment.recurring.join(", ") || "ainda em observação"}.
          {liveResult.environment.warning && ` ${liveResult.environment.warning}`}
        </p>
      )}
      {liveResult?.environment?.context && (
        <p role="status">
          Contexto provável: {liveResult.environment.context.hypothesis}. Hipótese usada para
          investigar objetos; não altera a confiança nem cria detecções.
        </p>
      )}
      {liveResult && (
        <p role="status">
          Detector ao vivo: {liveResult.model}
          {liveResult.model_warning && ` · ${liveResult.model_warning}`}
          {liveResult.learning_warning && ` · ${liveResult.learning_warning}`}
        </p>
      )}
      <div className="sol-live-camera" hidden={!camera}>
        <video ref={video} muted playsInline className="sol-camera" />
        {liveResult && (
          <svg
            viewBox={`0 0 ${liveResult.width} ${liveResult.height}`}
            aria-label="Objetos detectados na câmera"
          >
            {liveResult.detections.map((box, i) => (
              <g key={i}>
                <rect
                  x={box.x}
                  y={box.y}
                  width={box.width}
                  height={box.height}
                  strokeDasharray={box.stable === false ? "5 4" : undefined}
                />
                <text x={box.x + 4} y={Math.max(18, box.y + 18)}>
                  {box.label} {(box.confidence * 100).toFixed(0)}%
                  {box.familiar ? " · recorrente" : ""}
                </text>
              </g>
            ))}
          </svg>
        )}
      </div>
      {error && (
        <p role="alert" className="sol-error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {image && result && !camera && (
        <div id="vision-review" className="sol-stack">
          <VisionAnnotationEditor
            key={`${version.current}-${projectId ?? "general"}`}
            image={image}
            width={result.width}
            height={result.height}
            boxes={result.detections}
            disabled={busy || live}
            onChange={(detections) => {
              setResult({ ...result, detections })
              setCompleteReview(false)
              setNotice("Alterações no rascunho. Salve ou incorpore as marcações para aprender.")
            }}
          />
          <label>
            <input
              type="checkbox"
              checked={completeReview}
              disabled={busy}
              onChange={(event) => setCompleteReview(event.target.checked)}
            />{" "}
            Revisei a imagem inteira: todas as caixas estão corretas e nenhum objeto relevante ficou
            sem marcar.
          </label>
          <p>
            Para uma marcação parcial, apenas suas caixas serão consideradas confirmadas; o restante
            será verificado automaticamente. Incorporar solicita ajuste de pesos de YOLO26s e
            YOLO26x. Uma única imagem não comprova generalização.
          </p>
          <div className="sol-toolbar">
            <button
              className="btn-primary"
              disabled={busy || live || result.detections.some((b) => !b.label.trim())}
              onClick={() => void save()}
            >
              Salvar revisão
            </button>
            <button
              className="btn-primary"
              disabled={
                busy ||
                live ||
                !result.detections.length ||
                result.detections.some((b) => !b.label.trim()) ||
                (!completeReview && !result.detections.some((b) => b.source === "human"))
              }
              onClick={() => void save(true)}
            >
              {busy ? "Processando…" : "Incorporar marcação e treinar agora"}
            </button>
            <span>
              {result.detections.length} objetos marcados · {result.model}
            </span>
          </div>
        </div>
      )}
    </section>
  )
}
