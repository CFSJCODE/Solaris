import {
  createElement,
  CSSProperties,
  forwardRef,
  HTMLAttributes,
  ReactNode,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
} from "react"
import { useGlassScene } from "./GlassBackdrop"
import { domeBezel, lensMapDataUrl, specularMapDataUrl } from "./lensMap"
import { lightAngle, subscribeLight } from "./lightField"
import { useMaterial } from "./MaterialProvider"
import { animate, ELASTIC, SpringValue } from "./springAnimator"

/**
 * Material contract for SOLARIS surfaces (Fluent layer → Liquid Glass material).
 *
 *   regular  — Functional Glass Layer (sidebar, topbar, composer): blur + rim light
 *   clear    — lighter tint for small floating controls over rich content
 *   acrylic  — Overlay Layer (menus, popovers): denser tint, higher elevation
 *
 * `refract` opts the surface into the SVG lens (tier "liquid" only). Keep it to
 * the 2–4 surfaces that benefit from it (design system §4, "regra de ouro").
 * The lens is a dome over the whole surface (`bezel="auto"`), not only a rim.
 *
 * `webgl` hands the surface to the WebGL2 scene (GlassBackdrop) when it is
 * active: the shader draws its glass, so it works without SVG backdrop
 * filters. Use it for surfaces whose backdrop is the L0 canvas (sidebar).
 */
export type GlassVariant = "regular" | "clear" | "acrylic"

type Props = HTMLAttributes<HTMLElement> & {
  as?: keyof JSX.IntrinsicElements
  variant?: GlassVariant
  refract?: boolean
  webgl?: boolean
  /** Width (px) of the refracting profile; "auto" = dome over the whole surface. */
  bezel?: number | "auto"
  /** Displacement strength (px) of feDisplacementMap. */
  strength?: number
  children?: ReactNode
  [key: `data-${string}`]: string | undefined
}

interface LensState {
  url: string | null
  specular: string | null
  width: number
  height: number
}

export const LiquidSurface = forwardRef<HTMLElement, Props>(function LiquidSurface(
  {
    as = "div",
    variant = "regular",
    refract = false,
    webgl = false,
    bezel = "auto",
    strength = 64,
    className,
    style,
    children,
    ...rest
  },
  forwarded,
) {
  const { tier } = useMaterial()
  const ref = useRef<HTMLElement>(null)
  useImperativeHandle(forwarded, () => ref.current as HTMLElement)
  const filterId = `sol-lens-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`
  const [lens, setLens] = useState<LensState | null>(null)
  const scene = useGlassScene()
  const [onScene, setOnScene] = useState(false)
  const active = refract && tier === "liquid" && !onScene
  const lit = tier !== "solid"
  const displacement = useRef<SVGFEDisplacementMapElement>(null)

  // WebGL slab: register with the scene; width jumps (collapse) give it a
  // spring impulse, presses squash it.
  useEffect(() => {
    const el = ref.current
    if (!webgl || !el) return
    const handle = scene.register(el)
    setOnScene(!!handle)
    if (!handle) return
    let lastWidth = el.getBoundingClientRect().width
    const ro = new ResizeObserver(() => {
      const w = el.getBoundingClientRect().width
      const delta = w - lastWidth
      if (Math.abs(delta) > 24) handle.kick(Math.sign(delta) * -0.5, Math.sign(delta) * 0.35)
      lastWidth = w
    })
    ro.observe(el)
    const down = (e: PointerEvent) => e.button === 0 && handle.press(true)
    const up = () => handle.press(false)
    el.addEventListener("pointerdown", down)
    window.addEventListener("pointerup", up)
    window.addEventListener("pointercancel", up)
    return () => {
      ro.disconnect()
      el.removeEventListener("pointerdown", down)
      window.removeEventListener("pointerup", up)
      window.removeEventListener("pointercancel", up)
      handle.unregister()
      setOnScene(false)
    }
  }, [webgl, scene])

  // Dynamic specular: rotate the contour highlight toward the live light.
  useEffect(() => {
    const el = ref.current
    if (!lit || onScene || !el) return
    return subscribeLight(() => {
      el.style.setProperty(
        "--sol-light-rot",
        `${lightAngle(el.getBoundingClientRect()).toFixed(1)}deg`,
      )
    })
  }, [lit, onScene])

  // Pressing a refracting surface deepens the lens with an elastic spring.
  useEffect(() => {
    const el = ref.current
    if (!active || !el) return
    const spring = new SpringValue(0, ELASTIC)
    let running = false
    const apply = () => {
      displacement.current?.setAttribute("scale", String(strength * (1 + 0.5 * spring.value)))
    }
    const go = (target: number) => {
      spring.target = target
      if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
        spring.snap()
        apply()
        return
      }
      if (running) return
      running = true
      animate((dt) => {
        const moving = spring.step(dt)
        apply()
        running = moving
        return moving
      })
    }
    const down = (e: PointerEvent) => e.button === 0 && go(1)
    const up = () => go(0)
    el.addEventListener("pointerdown", down)
    window.addEventListener("pointerup", up)
    window.addEventListener("pointercancel", up)
    return () => {
      el.removeEventListener("pointerdown", down)
      window.removeEventListener("pointerup", up)
      window.removeEventListener("pointercancel", up)
    }
  }, [active, strength])

  useEffect(() => {
    const el = ref.current
    if (!lit || onScene || !el || typeof ResizeObserver === "undefined") {
      setLens(null)
      return
    }
    let frame = 0
    const measure = () => {
      frame = 0
      const rect = el.getBoundingClientRect()
      if (rect.width < 8 || rect.height < 8) return
      const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0
      const width = Math.round(rect.width)
      const height = Math.round(rect.height)
      const geometry = {
        width,
        height,
        radius,
        bezel: bezel === "auto" ? domeBezel(width, height) : bezel,
      }
      setLens({
        url: active ? lensMapDataUrl(geometry) : null,
        specular: specularMapDataUrl(geometry),
        width,
        height,
      })
    }
    const ro = new ResizeObserver(() => {
      if (!frame) frame = requestAnimationFrame(measure)
    })
    ro.observe(el)
    return () => {
      ro.disconnect()
      cancelAnimationFrame(frame)
    }
  }, [active, lit, onScene, bezel])

  const refracting = active && !!lens?.url
  const lensStyle = {
    ...(refracting ? { "--sol-lens": `url(#${filterId})` } : {}),
    ...(lens?.specular ? { "--sol-specular-map": `url(${lens.specular})` } : {}),
  } as CSSProperties

  const classes = [
    "sol-glass",
    `sol-glass--${variant}`,
    "sol-lit",
    onScene && "sol-glass--webgl",
    refracting && "sol-glass--refract",
    lens?.specular && "sol-glass--mapped",
    className,
  ]
    .filter(Boolean)
    .join(" ")

  return createElement(
    as,
    { ...rest, ref, className: classes, style: { ...style, ...lensStyle } },
    refracting && lens?.url && (
      <svg className="sol-lens-defs" aria-hidden="true" focusable="false" width="0" height="0">
        <filter
          id={filterId}
          x="0"
          y="0"
          width={lens.width}
          height={lens.height}
          filterUnits="userSpaceOnUse"
          primitiveUnits="userSpaceOnUse"
          colorInterpolationFilters="sRGB"
        >
          <feImage
            href={lens.url}
            x="0"
            y="0"
            width={lens.width}
            height={lens.height}
            preserveAspectRatio="none"
            result="lens"
          />
          <feDisplacementMap
            ref={displacement}
            in="SourceGraphic"
            in2="lens"
            scale={strength}
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </svg>
    ),
    children,
  )
})
