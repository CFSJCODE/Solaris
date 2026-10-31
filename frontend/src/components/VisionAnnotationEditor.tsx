import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { drawnBox, imagePoint, movedBox, resizedBox, type AnnotationBox, type Corner, type Point } from './annotationGeometry'

export interface Detection extends AnnotationBox {
  track_id?: number
  stable?: boolean
  familiar?: boolean
  label: string
  confidence: number
  class_id: number
  source?: 'human' | 'model'
  description?: string
}

type Drag = { pointer: number; kind: 'draw'; start: Point; current: Point }
  | { pointer: number; kind: 'move' | 'resize'; start: Point; current: Point; index: number; original: Detection; corner?: Corner }

export default function VisionAnnotationEditor({ image, width, height, boxes, disabled, onChange }: {
  image: string; width: number; height: number; boxes: Detection[]; disabled: boolean; onChange: (boxes: Detection[]) => void
}) {
  const [mode, setMode] = useState<'draw' | 'select'>('draw')
  const [selected, setSelected] = useState<number | null>(null)
  const [preview, setPreview] = useState<AnnotationBox | null>(null)
  const [announcement, setAnnouncement] = useState('Arraste sobre o objeto para desenhar uma caixa.')
  const svg = useRef<SVGSVGElement>(null)
  const label = useRef<HTMLInputElement>(null)
  const drag = useRef<Drag | null>(null)
  const undo = useRef<Detection[][]>([])
  const [undoCount, setUndoCount] = useState(0)
  const picked = selected === null ? undefined : boxes[selected]
  const handleSize = Math.max(10, width / 65)

  function cancel() {
    const current = drag.current
    drag.current = null
    setPreview(null)
    if (current && svg.current?.hasPointerCapture(current.pointer)) svg.current.releasePointerCapture(current.pointer)
  }
  useEffect(() => {
    if (disabled) cancel()
  }, [disabled])
  useEffect(() => () => {
    drag.current = null
  }, [])
  function commit(next: Detection[]) {
    undo.current = [...undo.current.slice(-29), boxes.map(box => ({ ...box }))]
    setUndoCount(undo.current.length)
    onChange(next)
  }
  function point(event: PointerEvent<SVGSVGElement>): Point {
    return imagePoint(event.clientX, event.clientY, svg.current!.getBoundingClientRect(), width, height)
  }
  function begin(event: PointerEvent<SVGSVGElement>) {
    if (disabled || event.button !== 0) return
    if (mode === 'draw') {
      const start = point(event)
      drag.current = { pointer: event.pointerId, kind: 'draw', start, current: start }
      setPreview(drawnBox(start, start))
      svg.current?.setPointerCapture(event.pointerId)
      svg.current?.focus()
      event.preventDefault()
    } else setSelected(null)
  }
  function pick(event: PointerEvent<SVGRectElement>, index: number, corner?: Corner) {
    if (disabled || mode !== 'select' || event.button !== 0) return
    event.stopPropagation(); event.preventDefault()
    const bounds = svg.current!.getBoundingClientRect()
    const start = imagePoint(event.clientX, event.clientY, bounds, width, height)
    setSelected(index)
    drag.current = { pointer: event.pointerId, kind: corner ? 'resize' : 'move', start, current: start, index, original: { ...boxes[index] }, corner }
    svg.current?.setPointerCapture(event.pointerId)
    svg.current?.focus()
  }
  function geometry(current: Drag): AnnotationBox {
    if (current.kind === 'draw') return drawnBox(current.start, current.current)
    if (current.kind === 'move') return movedBox(current.original, current.current.x - current.start.x, current.current.y - current.start.y, width, height)
    return resizedBox(current.original, current.corner!, current.current, width, height)
  }
  function move(event: PointerEvent<SVGSVGElement>) {
    const current = drag.current
    if (!current || current.pointer !== event.pointerId) return
    current.current = point(event)
    setPreview(geometry(current))
  }
  function finish(event: PointerEvent<SVGSVGElement>) {
    const current = drag.current
    if (!current || current.pointer !== event.pointerId) return
    current.current = point(event)
    const box = geometry(current)
    cancel()
    if (disabled) return
    if (current.kind === 'draw') {
      if (box.width < 4 || box.height < 4) { setAnnouncement('Caixa muito pequena. Arraste ao redor do objeto.'); return }
      commit([...boxes, { ...box, label: '', confidence: 0, class_id: -1, source: 'human' }])
      setSelected(boxes.length)
      setMode('select')
      setAnnouncement('Caixa criada. Escreva o nome do objeto e salve a revisão.')
      requestAnimationFrame(() => label.current?.focus())
    } else {
      const original = current.original
      if (box.x !== original.x || box.y !== original.y || box.width !== original.width || box.height !== original.height) {
        commit(boxes.map((item, i) => i === current.index ? { ...item, ...box, source: 'human' } : item))
      }
    }
  }
  function update(field: 'label' | 'description', value: string) {
    if (selected === null) return
    onChange(boxes.map((box, i) => i === selected ? {
      ...box, [field]: value, source: 'human', ...(field === 'label' ? { class_id: -1 } : {}),
    } : box))
  }
  function remove() {
    if (selected === null || disabled) return
    commit(boxes.filter((_, index) => index !== selected)); setSelected(null)
    setAnnouncement('Marcação removida do rascunho. Salve para registrar a revisão.')
  }
  return <section className="sol-stack sol-annotation-editor" aria-label="Revisão e marcação do quadro">
    <div className="sol-toolbar">
      <h2>Revisar quadro</h2>
      <button className="btn-ghost" disabled={disabled} aria-pressed={mode === 'draw'} onClick={() => { cancel(); setMode('draw'); setAnnouncement('Arraste sobre o objeto para desenhar uma caixa.') }}>Desenhar marcação</button>
      <button className="btn-ghost" disabled={disabled} aria-pressed={mode === 'select'} onClick={() => { cancel(); setMode('select'); setAnnouncement('Clique em uma caixa para nomear, mover ou ajustar seus cantos.') }}>Selecionar e ajustar</button>
      <button className="btn-ghost" disabled={disabled || undoCount === 0} onClick={() => {
        cancel(); const previous = undo.current.pop(); if (previous) onChange(previous); setSelected(null); setUndoCount(undo.current.length)
      }}>Desfazer marcação</button>
    </div>
    <p id="vision-annotation-help">Desenhe uma caixa ao redor do objeto e escreva o que ele é. Para corrigir uma caixa, selecione e arraste o centro ou os cantos. Esc cancela o desenho. As alterações são gravadas em “Salvar revisão”.</p>
    <div className="sol-annotation-layout">
      <div className="sol-vision-canvas">
        <img src={image} alt="Quadro congelado para marcar e identificar objetos" draggable={false} />
        <svg ref={svg} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className={`sol-annotation-layer ${mode === 'draw' ? 'drawing' : ''}`}
          aria-label="Área de marcação de objetos" aria-describedby="vision-annotation-help" tabIndex={0}
          onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); cancel(); setMode('select') } }}
          onPointerDown={begin} onPointerMove={move} onPointerUp={finish} onPointerCancel={cancel} onLostPointerCapture={cancel}>
          {boxes.map((box, index) => {
            const displayed = drag.current?.kind !== 'draw' && drag.current?.index === index && preview ? { ...box, ...preview } : box
            return <g key={index} className={selected === index ? 'selected' : undefined}>
              <rect x={displayed.x} y={displayed.y} width={displayed.width} height={displayed.height} vectorEffect="non-scaling-stroke" onPointerDown={event => pick(event, index)} />
              <text x={displayed.x + 4} y={Math.max(18, displayed.y + 18)}>{index + 1}. {box.label || 'Escreva o nome'}</text>
            </g>
          })}
          {drag.current?.kind === 'draw' && preview && <rect className="sol-annotation-preview" {...preview} vectorEffect="non-scaling-stroke" />}
          {picked && mode === 'select' && !disabled && (['nw', 'ne', 'sw', 'se'] as Corner[]).map(corner => {
            const box = preview && drag.current?.kind !== 'draw' ? preview : picked
            return <rect key={corner} className={`sol-annotation-handle ${corner}`} x={(corner.includes('w') ? box.x : box.x + box.width) - handleSize / 2}
              y={(corner.includes('n') ? box.y : box.y + box.height) - handleSize / 2} width={handleSize} height={handleSize} onPointerDown={event => pick(event, selected!, corner)} />
          })}
        </svg>
      </div>
      <aside className="sol-stack sol-annotation-inspector" aria-label="Objetos marcados">
        <h3>Objetos · {boxes.length}</h3>
        {boxes.length === 0 && <p>Nenhum objeto marcado. Arraste sobre a imagem para adicionar o primeiro.</p>}
        <div className="sol-annotation-list">{boxes.map((box, index) => <button type="button" className="btn-ghost" key={index} aria-pressed={selected === index} disabled={disabled}
          onClick={() => { cancel(); setMode('select'); setSelected(index); requestAnimationFrame(() => label.current?.focus()) }}>{index + 1}. {box.label || 'Sem nome'}</button>)}</div>
        {picked && <fieldset disabled={disabled} className="sol-stack">
          <legend>Marcação {selected! + 1}</legend>
          <label>O que é este objeto?<input ref={label} className="project-input" value={picked.label} maxLength={120} placeholder="Ex.: mala, caixa de ferramentas, cadeira"
            onChange={event => update('label', event.target.value)} /></label>
          <label>Descrição ou observação (opcional)<textarea className="project-input" value={picked.description ?? ''} maxLength={1000} rows={3}
            placeholder="Ex.: mala preta com rodinhas" onChange={event => update('description', event.target.value)} /></label>
          <p>{picked.source === 'human' ? 'Marcação ou identificação feita por você.' : `Sugestão do detector · confiança ${(picked.confidence * 100).toFixed(0)}%.`}</p>
          <button type="button" className="btn-danger" onClick={remove}>Remover esta marcação</button>
        </fieldset>}
      </aside>
    </div>
    <p role="status" aria-live="polite">{announcement}</p>
    {boxes.some(box => !box.label.trim()) && <p role="status">Escreva o nome de todos os objetos marcados antes de salvar.</p>}
  </section>
}
