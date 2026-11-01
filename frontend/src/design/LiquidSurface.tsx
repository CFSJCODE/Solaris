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
import { lensMapDataUrl, specularMapDataUrl } from "./lensMap"
import { useMaterial } from "./MaterialProvider"

/**
 * Material contract for SOLARIS surfaces (Fluent layer → Liquid Glass material).
 *
 *   regular  — Functional Glass Layer (sidebar, topbar, composer): blur + rim light
 *   clear    — lighter tint for small floating controls over rich content
 *   acrylic  — Overlay Layer (menus, popovers): denser tint, higher elevation
 *
 * `refract` opts the surface into the SVG lens (tier "liquid" only). Keep it to
 * the 2–4 surfaces that benefit from it (design system §4, "regra de ouro").
 */
export type GlassVariant = "regular" | "clear" | "acrylic"

type Props = HTMLAttributes<HTMLElement> & {
  as?: keyof JSX.IntrinsicElements
  variant?: GlassVariant
  refract?: boolean
  /** Rim width (px) of the refracting lens. */
  bezel?: number
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
    bezel = 22,
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
  const active = refract && tier === "liquid"
  const lit = tier !== "solid"

  useEffect(() => {
    const el = ref.current
    if (!lit || !el || typeof ResizeObserver === "undefined") {
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
      const geometry = { width, height, radius, bezel }
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
  }, [active, lit, bezel])

  const refracting = active && !!lens?.url
  const lensStyle = {
    ...(refracting ? { "--sol-lens": `url(#${filterId})` } : {}),
    ...(lens?.specular ? { "--sol-specular-map": `url(${lens.specular})` } : {}),
  } as CSSProperties

  const classes = [
    "sol-glass",
    `sol-glass--${variant}`,
    "sol-lit",
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
