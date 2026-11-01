// Shared light source for specular highlights.
//
// The light sits above the screen at the pointer position (desktop) or is
// tilted by the device orientation (gyroscope, when the platform reports it).
// With no input it rests at the top-left, matching --sol-light-angle.

export interface LightState {
  /** Light position in viewport px (x, y) and height above the screen (z). */
  x: number
  y: number
  z: number
  /** True once the pointer or gyroscope has moved the light. */
  live: boolean
}

type Listener = (light: LightState) => void

const listeners = new Set<Listener>()
const light: LightState = { x: 0, y: 0, z: 420, live: false }
let installed = false
let frame = 0

function emit() {
  frame = 0
  for (const l of listeners) l(light)
}

function schedule() {
  if (!frame) frame = requestAnimationFrame(emit)
}

function install() {
  if (installed || typeof window === "undefined") return
  installed = true
  light.x = window.innerWidth * 0.15
  light.y = -window.innerHeight * 0.2
  window.addEventListener(
    "pointermove",
    (e) => {
      if (e.pointerType === "touch") return
      light.x = e.clientX
      light.y = e.clientY
      light.live = true
      schedule()
    },
    { passive: true },
  )
  window.addEventListener(
    "deviceorientation",
    (e) => {
      if (e.beta == null || e.gamma == null) return
      // Tilting the device moves the light across the screen (±45° → edges).
      const clamp = (v: number) => Math.max(-45, Math.min(45, v)) / 45
      light.x = window.innerWidth * (0.5 + 0.5 * clamp(e.gamma))
      light.y = window.innerHeight * (0.5 + 0.5 * clamp(e.beta - 45))
      light.live = true
      schedule()
    },
    { passive: true },
  )
}

export function subscribeLight(listener: Listener): () => void {
  install()
  listeners.add(listener)
  listener(light)
  return () => listeners.delete(listener)
}

/** CSS conic angle (0° = up, clockwise) from a box centre toward the light. */
export function lightAngle(rect: { left: number; top: number; width: number; height: number }) {
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  const deg = (Math.atan2(light.x - cx, -(light.y - cy)) * 180) / Math.PI
  return (deg + 360) % 360
}
