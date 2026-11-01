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
import { animate, ELASTIC, SpringValue } from "./springAnimator"

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

/** Controls that deform with the elastic spring when pressed. */
export const PRESS_SELECTOR =
  ".btn-primary, .sol-btn-accent, .btn-ghost, .btn-danger, .chat-send.ready, .sol-nav-item, .sol-nav-toggle"

/**
 * Liquid press: a delegated listener drives one SpringValue per pressed
 * control and writes it to `--sol-press`; CSS turns it into a
 * volume-preserving squash (wider, shorter) that rebounds on release with
 * the ELASTIC spring's single overshoot. The target can change mid-flight
 * (quick double press) without losing velocity, which CSS transitions cannot do.
 * Disabled under prefers-reduced-motion; CSS :active scale stays as fallback.
 */
function usePressSprings(enabled: boolean) {
  useEffect(() => {
    const root = document.documentElement
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")
    if (!enabled || reduced?.matches) return
    root.dataset.motion = "spring"
    const springs = new WeakMap<HTMLElement, SpringValue>()
    const running = new WeakSet<HTMLElement>()
    let pressed: HTMLElement | null = null

    const drive = (el: HTMLElement, target: number) => {
      let spring = springs.get(el)
      if (!spring) springs.set(el, (spring = new SpringValue(0, ELASTIC)))
      spring.target = target
      if (running.has(el)) return
      running.add(el)
      animate((dt) => {
        const moving = spring!.step(dt)
        if (moving || spring!.target !== 0) {
          el.style.setProperty("--sol-press", spring!.value.toFixed(4))
        } else el.style.removeProperty("--sol-press")
        if (!moving) running.delete(el)
        return moving
      })
    }
    const target = (e: Event) => {
      const el = (e.target as Element | null)?.closest?.(PRESS_SELECTOR) as HTMLElement | null
      return el && !(el as HTMLButtonElement).disabled ? el : null
    }
    const down = (e: PointerEvent) => {
      if (e.button !== 0) return
      pressed = target(e)
      if (pressed) drive(pressed, 1)
    }
    const release = () => {
      if (pressed) drive(pressed, 0)
      pressed = null
    }
    const keyDown = (e: KeyboardEvent) => {
      if ((e.key === " " || e.key === "Enter") && !e.repeat) {
        pressed = target(e)
        if (pressed) drive(pressed, 1)
      }
    }
    document.addEventListener("pointerdown", down, { passive: true })
    document.addEventListener("pointerup", release, { passive: true })
    document.addEventListener("pointercancel", release, { passive: true })
    document.addEventListener("keydown", keyDown)
    document.addEventListener("keyup", release)
    return () => {
      delete root.dataset.motion
      document.removeEventListener("pointerdown", down)
      document.removeEventListener("pointerup", release)
      document.removeEventListener("pointercancel", release)
      document.removeEventListener("keydown", keyDown)
      document.removeEventListener("keyup", release)
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
  usePressSprings(tier !== "solid")

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
