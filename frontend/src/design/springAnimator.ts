// Runtime spring integrator for interactive deformation.
//
// The CSS `linear()` springs (spring.ts) cover transitions whose start and end
// are known. Gestures are different: the target changes mid-flight (press,
// release, press again) and the velocity must be preserved across changes,
// which only a stateful integrator can do.
//
//   a = −k (x − target) − c v          (unit mass)
//
// integrated with semi-implicit Euler in fixed 1/240 s sub-steps, which is
// stable for the stiffness range used here and independent of frame rate.

import type { SpringParams } from "./spring"

export class SpringValue {
  value: number
  velocity = 0
  target: number
  private params: SpringParams

  constructor(initial: number, params: SpringParams) {
    this.params = params
    this.value = initial
    this.target = initial
  }

  /** Advance by `dt` seconds. Returns true while still moving. */
  step(dt: number): boolean {
    const h = 1 / 240
    let remaining = Math.min(dt, 0.064) // avoid huge jumps after a hidden tab
    while (remaining > 1e-6) {
      const s = Math.min(h, remaining)
      const accel =
        -this.params.stiffness * (this.value - this.target) - this.params.damping * this.velocity
      this.velocity += accel * s
      this.value += this.velocity * s
      remaining -= s
    }
    const settled = Math.abs(this.value - this.target) < 1e-3 && Math.abs(this.velocity) < 1e-2
    if (settled) {
      this.value = this.target
      this.velocity = 0
    }
    return !settled
  }

  /** Jump to the target without animation (reduced motion). */
  snap() {
    this.value = this.target
    this.velocity = 0
  }
}

/**
 * Elastic spring for deformation: ζ ≈ 0.62, one visible rebound (~8 %) and
 * then rest — "liquid" without repeated oscillation.
 */
export const ELASTIC: SpringParams = { stiffness: 620, damping: 31 }

type Tick = (dt: number) => boolean

/** Shared rAF loop: runs only while at least one animation is active. */
const active = new Set<Tick>()
let frame = 0
let last = 0

function loop(now: number) {
  const dt = last ? (now - last) / 1000 : 1 / 60
  last = now
  for (const tick of [...active]) if (!tick(dt)) active.delete(tick)
  if (active.size) frame = requestAnimationFrame(loop)
  else {
    frame = 0
    last = 0
  }
}

export function animate(tick: Tick) {
  active.add(tick)
  if (!frame && typeof requestAnimationFrame !== "undefined") frame = requestAnimationFrame(loop)
}
