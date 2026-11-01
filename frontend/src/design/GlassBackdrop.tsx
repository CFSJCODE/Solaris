import { createContext, ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react"
import { subscribeLight } from "./lightField"
import { useMaterial } from "./MaterialProvider"
import { animate, ELASTIC, SpringValue } from "./springAnimator"
import { GlassPanel, GlassRenderer, readGlassUniforms } from "./webgl/GlassRenderer"
import { MAX_PANELS } from "./webgl/glassShader"

/**
 * L0 scene + WebGL glass (tier "liquid", WebGL2 available).
 *
 * A fixed full-viewport canvas behind the shell draws the canvas light fields
 * and the registered glass slabs with refraction over their whole surface,
 * per-channel dispersion, Fresnel and a specular that follows the pointer or
 * gyroscope. Unlike `backdrop-filter: url()`, this path does not depend on
 * Chromium's SVG-filter support: it runs in any WebGL2 engine.
 *
 * Without WebGL2 (or on context loss) nothing is registered and every
 * surface keeps its CSS/SVG material.
 */

export interface PanelHandle {
  /** Give the slab an impulse (px/s-ish units of deformation). */
  kick(vx: number, vy: number): void
  /** Press deformation target (0 = rest, 1 = pressed). */
  press(on: boolean): void
  unregister(): void
}

interface Registry {
  register(el: HTMLElement): PanelHandle | null
}

const SceneContext = createContext<Registry>({ register: () => null })

export function useGlassScene() {
  return useContext(SceneContext)
}

interface Entry {
  el: HTMLElement
  sx: SpringValue
  sy: SpringValue
}

function supportsWebGL2() {
  try {
    return !!document.createElement("canvas").getContext("webgl2")
  } catch {
    return false
  }
}

export function GlassBackdrop({ children }: { children: ReactNode }) {
  const { tier } = useMaterial()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [failed, setFailed] = useState(false)
  const [supported] = useState(() => typeof document !== "undefined" && supportsWebGL2())
  const enabled = tier === "liquid" && supported && !failed
  const entries = useRef(new Set<Entry>())
  const requestFrame = useRef<() => void>(() => {})
  const observe = useRef<(el: HTMLElement) => void>(() => {})
  const unobserve = useRef<(el: HTMLElement) => void>(() => {})

  useEffect(() => {
    const canvas = canvasRef.current
    if (!enabled || !canvas) return
    let renderer: GlassRenderer
    try {
      renderer = new GlassRenderer(canvas)
    } catch (err) {
      console.warn("[SOLARIS] WebGL glass desativado:", err)
      setFailed(true)
      return
    }
    const root = document.documentElement
    let uniforms = readGlassUniforms(root)
    let light: [number, number, number] = [0, 0, 420]
    let frame = 0

    const draw = () => {
      frame = 0
      if (renderer.lost) return
      const panels: GlassPanel[] = []
      for (const e of entries.current) {
        if (panels.length >= MAX_PANELS) break
        const r = e.el.getBoundingClientRect()
        if (r.width < 4 || r.height < 4) continue
        const radius = parseFloat(getComputedStyle(e.el).borderTopLeftRadius) || 0
        panels.push({
          x: r.left,
          y: r.top,
          width: r.width,
          height: r.height,
          radius,
          wobble: [e.sx.value, e.sy.value],
        })
      }
      renderer.render(uniforms, light, panels)
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(draw)
    }
    requestFrame.current = schedule

    const resize = () => {
      renderer.resize(window.innerWidth, window.innerHeight, window.devicePixelRatio || 1)
      schedule()
    }
    resize()
    root.dataset.scene = "webgl"

    const unsubscribe = subscribeLight((l) => {
      light = [l.x, l.y, l.z]
      schedule()
    })
    const ro = new ResizeObserver(schedule)
    for (const e of entries.current) ro.observe(e.el)
    observe.current = (el) => ro.observe(el)
    unobserve.current = (el) => ro.unobserve(el)

    // Theme / contrast changes re-read the colour tokens.
    const reread = () => {
      uniforms = readGlassUniforms(root)
      schedule()
    }
    const themeQueries = ["(prefers-color-scheme: dark)", "(prefers-contrast: more)"].map((q) =>
      window.matchMedia?.(q),
    )
    themeQueries.forEach((m) => m?.addEventListener("change", reread))
    const mo = new MutationObserver(reread)
    mo.observe(root, { attributes: true, attributeFilter: ["data-theme", "class", "style"] })

    const onLost = (e: Event) => {
      e.preventDefault()
      setFailed(true)
    }
    canvas.addEventListener("webglcontextlost", onLost)
    window.addEventListener("resize", resize)

    return () => {
      cancelAnimationFrame(frame)
      unsubscribe()
      ro.disconnect()
      mo.disconnect()
      themeQueries.forEach((m) => m?.removeEventListener("change", reread))
      canvas.removeEventListener("webglcontextlost", onLost)
      window.removeEventListener("resize", resize)
      observe.current = () => {}
      unobserve.current = () => {}
      requestFrame.current = () => {}
      delete root.dataset.scene
    }
  }, [enabled])

  const registry = useMemo<Registry>(
    () => ({
      register(el) {
        if (!enabled) return null
        const entry: Entry = {
          el,
          sx: new SpringValue(0, ELASTIC),
          sy: new SpringValue(0, ELASTIC),
        }
        entries.current.add(entry)
        observe.current(el)
        requestFrame.current()
        const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
        const run = () =>
          animate((dt) => {
            const movingX = entry.sx.step(dt)
            const movingY = entry.sy.step(dt)
            requestFrame.current()
            return (movingX || movingY) && entries.current.has(entry)
          })
        return {
          kick(vx, vy) {
            if (reduced()) return
            entry.sx.velocity += vx
            entry.sy.velocity += vy
            run()
          },
          press(on) {
            // Pressed glass spreads sideways and flattens (volume-preserving squash).
            entry.sx.target = on ? 0.006 : 0
            entry.sy.target = on ? -0.01 : 0
            if (reduced()) {
              entry.sx.snap()
              entry.sy.snap()
              requestFrame.current()
            } else run()
          },
          unregister() {
            entries.current.delete(entry)
            unobserve.current(el)
            requestFrame.current()
          },
        }
      },
    }),
    [enabled],
  )

  return (
    <SceneContext.Provider value={registry}>
      {enabled && <canvas ref={canvasRef} className="sol-scene" aria-hidden="true" />}
      {children}
    </SceneContext.Provider>
  )
}
