import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react"
import {
  loadPreference,
  MATERIAL_MEDIA_QUERIES,
  MaterialPreference,
  MaterialTier,
  readEnvironment,
  resolveTier,
  savePreference,
} from "./materialTier"

interface MaterialContextValue {
  tier: MaterialTier
  preference: MaterialPreference
  setPreference: (pref: MaterialPreference) => void
}

const MaterialContext = createContext<MaterialContextValue>({
  tier: "solid",
  preference: "auto",
  setPreference: () => {},
})

export function useMaterial() {
  return useContext(MaterialContext)
}

/** Elements whose specular highlight follows the pointer (Interactive Lighting). */
export const LIT_SELECTOR = ".sol-lit, .btn-primary, .sol-btn-accent"

/**
 * One delegated, rAF-throttled pointer listener drives every lit surface: it
 * writes the pointer position into `--sol-light-x/y` on the hovered element
 * only, so lighting costs one style write per frame regardless of how many
 * surfaces exist, and nothing runs while the pointer is still.
 */
function usePointerLight(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return
    let frame = 0
    let last: PointerEvent | null = null
    let current: HTMLElement | null = null
    const apply = () => {
      frame = 0
      if (!last) return
      const target = (last.target as Element | null)?.closest?.(LIT_SELECTOR) as HTMLElement | null
      if (current && current !== target) {
        current.style.removeProperty("--sol-light-x")
        current.style.removeProperty("--sol-light-y")
        current.removeAttribute("data-lit")
      }
      current = target
      if (!target) return
      const r = target.getBoundingClientRect()
      target.style.setProperty("--sol-light-x", `${Math.round(last.clientX - r.left)}px`)
      target.style.setProperty("--sol-light-y", `${Math.round(last.clientY - r.top)}px`)
      target.setAttribute("data-lit", "")
    }
    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return
      last = e
      if (!frame) frame = requestAnimationFrame(apply)
    }
    const onLeave = () => {
      last = null
      if (current) {
        current.removeAttribute("data-lit")
        current = null
      }
    }
    document.addEventListener("pointermove", onMove, { passive: true })
    document.documentElement.addEventListener("pointerleave", onLeave)
    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener("pointermove", onMove)
      document.documentElement.removeEventListener("pointerleave", onLeave)
    }
  }, [enabled])
}

export function MaterialProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<MaterialPreference>(loadPreference)
  const [tier, setTier] = useState<MaterialTier>(() => resolveTier(preference, readEnvironment()))

  useEffect(() => {
    const update = () => setTier(resolveTier(preference, readEnvironment()))
    update()
    const lists = MATERIAL_MEDIA_QUERIES.map((q) => window.matchMedia?.(q)).filter(Boolean)
    lists.forEach((l) => l!.addEventListener("change", update))
    return () => lists.forEach((l) => l!.removeEventListener("change", update))
  }, [preference])

  useEffect(() => {
    document.documentElement.dataset.material = tier
  }, [tier])

  usePointerLight(tier !== "solid")

  const setPreference = useCallback((pref: MaterialPreference) => {
    savePreference(pref)
    setPreferenceState(pref)
  }, [])

  return (
    <MaterialContext.Provider value={{ tier, preference, setPreference }}>
      {children}
    </MaterialContext.Provider>
  )
}
