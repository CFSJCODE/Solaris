// Adaptive rendering tiers for SOLARIS materials.
//
//   liquid — blur + SVG lens refraction + specular light (Chromium/WebView2)
//   glass  — blur + specular light, no refraction (other engines, modest HW)
//   solid  — opaque surfaces (reduced transparency, high contrast, forced colors)
//
// The user preference (Automático / Vidro líquido / Vidro / Sólido) always wins
// over automatic detection, except that forced-colors and an explicit
// "reduce transparency" system setting can only lower the tier, never raise it.

export type MaterialTier = "liquid" | "glass" | "solid"
export type MaterialPreference = "auto" | MaterialTier

export interface EnvironmentSignals {
  forcedColors: boolean
  reducedTransparency: boolean
  moreContrast: boolean
  supportsBackdrop: boolean
  supportsBackdropUrl: boolean
  hardwareConcurrency: number
  deviceMemoryGb?: number
  saveData: boolean
}

const RANK: Record<MaterialTier, number> = { solid: 0, glass: 1, liquid: 2 }

export function resolveTier(pref: MaterialPreference, env: EnvironmentSignals): MaterialTier {
  let ceiling: MaterialTier = "liquid"
  if (!env.supportsBackdropUrl) ceiling = "glass"
  if (!env.supportsBackdrop) ceiling = "solid"
  if (env.forcedColors || env.reducedTransparency) ceiling = "solid"

  let wanted: MaterialTier
  if (pref !== "auto") {
    wanted = pref
  } else if (env.moreContrast) {
    wanted = "solid"
  } else if (env.saveData || env.hardwareConcurrency < 4 || (env.deviceMemoryGb ?? 8) < 4) {
    wanted = "glass"
  } else {
    wanted = "liquid"
  }
  return RANK[wanted] <= RANK[ceiling] ? wanted : ceiling
}

function media(query: string): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.(query).matches
}

/** SVG filters as backdrop-filter inputs are a Chromium feature (WebView2 included). */
function isChromium(): boolean {
  if (typeof navigator === "undefined") return false
  const brands = (navigator as Navigator & { userAgentData?: { brands: { brand: string }[] } })
    .userAgentData?.brands
  if (brands) return brands.some((b) => /Chromium/i.test(b.brand))
  return /Chrome\/\d+/.test(navigator.userAgent) && !/Firefox\//.test(navigator.userAgent)
}

export function readEnvironment(): EnvironmentSignals {
  const css = typeof CSS !== "undefined" ? CSS : undefined
  const supportsBackdrop =
    !!css?.supports("backdrop-filter", "blur(1px)") ||
    !!css?.supports("-webkit-backdrop-filter", "blur(1px)")
  const nav = typeof navigator !== "undefined" ? navigator : undefined
  const connection = (nav as (Navigator & { connection?: { saveData?: boolean } }) | undefined)
    ?.connection
  return {
    forcedColors: media("(forced-colors: active)"),
    reducedTransparency: media("(prefers-reduced-transparency: reduce)"),
    moreContrast: media("(prefers-contrast: more)"),
    supportsBackdrop,
    supportsBackdropUrl: supportsBackdrop && isChromium(),
    hardwareConcurrency: nav?.hardwareConcurrency ?? 4,
    deviceMemoryGb: (nav as (Navigator & { deviceMemory?: number }) | undefined)?.deviceMemory,
    saveData: !!connection?.saveData,
  }
}

export const MATERIAL_MEDIA_QUERIES = [
  "(forced-colors: active)",
  "(prefers-reduced-transparency: reduce)",
  "(prefers-contrast: more)",
]

const STORAGE_KEY = "solaris.material"

export function loadPreference(): MaterialPreference {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === "liquid" || v === "glass" || v === "solid") return v
  } catch {
    /* storage unavailable: fall back to automatic */
  }
  return "auto"
}

export function savePreference(pref: MaterialPreference) {
  try {
    if (pref === "auto") localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, pref)
  } catch {
    /* ignore */
  }
}
