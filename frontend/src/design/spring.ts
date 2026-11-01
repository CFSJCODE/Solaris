// Spring physics for the SOLARIS motion system.
//
// A damped harmonic oscillator  x'' = -k(x - 1) - c x'  (unit mass) is solved
// analytically and sampled into a CSS `linear()` easing so the browser's
// compositor can run the spring on `transform`/`opacity` without JS per frame.
//
//   ω0 = sqrt(k)            natural frequency
//   ζ  = c / (2 sqrt(k))    damping ratio (ζ < 1 under-damped, ζ = 1 critical)
//
// The platform defaults use ζ ≥ 0.85, which keeps overshoot under ~0.6 % and
// avoids repeated oscillation, as the design directive requires.

export interface SpringParams {
  stiffness: number
  damping: number
}

/** Position (0 → 1) of a unit spring released from rest at time t (seconds). */
export function springPosition({ stiffness, damping }: SpringParams, t: number): number {
  const w0 = Math.sqrt(stiffness)
  const zeta = damping / (2 * w0)
  if (zeta < 1) {
    const wd = w0 * Math.sqrt(1 - zeta * zeta)
    const envelope = Math.exp(-zeta * w0 * t)
    return 1 - envelope * (Math.cos(wd * t) + ((zeta * w0) / wd) * Math.sin(wd * t))
  }
  if (zeta === 1) {
    return 1 - Math.exp(-w0 * t) * (1 + w0 * t)
  }
  const s1 = -w0 * (zeta - Math.sqrt(zeta * zeta - 1))
  const s2 = -w0 * (zeta + Math.sqrt(zeta * zeta - 1))
  const a = s2 / (s2 - s1)
  const b = -s1 / (s2 - s1)
  return 1 - a * Math.exp(s1 * t) - b * Math.exp(s2 * t)
}

/** Time (seconds) after which the spring stays within `epsilon` of rest. */
export function springSettleTime(params: SpringParams, epsilon = 0.002): number {
  const dt = 1 / 240
  let lastOutside = 0
  for (let t = 0; t < 10; t += dt) {
    if (Math.abs(1 - springPosition(params, t)) > epsilon) lastOutside = t
  }
  return lastOutside + dt
}

/** Peak overshoot above the target, as a fraction (0.01 = 1 %). */
export function springOvershoot(params: SpringParams): number {
  const settle = springSettleTime(params)
  let peak = 1
  for (let t = 0; t <= settle; t += 1 / 480) peak = Math.max(peak, springPosition(params, t))
  return peak - 1
}

/**
 * Sample the spring into a CSS `linear()` easing string. The duration that
 * must accompany the easing is returned as well, so both stay coherent.
 */
export function springToLinear(
  params: SpringParams,
  samples = 32,
): { easing: string; durationMs: number } {
  const settle = springSettleTime(params)
  const points: string[] = []
  for (let i = 0; i <= samples; i++) {
    const t = (i / samples) * settle
    const value = i === samples ? 1 : springPosition(params, t)
    points.push(String(Math.round(value * 10000) / 10000))
  }
  return { easing: `linear(${points.join(", ")})`, durationMs: Math.round(settle * 1000) }
}

/** Named springs used by the motion tokens. */
export const SPRINGS = {
  /** Press / release feedback: fast, nearly critically damped. */
  snappy: { stiffness: 1800, damping: 76 }, // ζ≈0.90, settles ≈140 ms
  /** State changes, indicator morphing. */
  smooth: { stiffness: 900, damping: 52 }, // ζ≈0.87, settles ≈270 ms
  /** Panels and overlays opening. */
  gentle: { stiffness: 520, damping: 39 }, // ζ≈0.86, settles ≈350 ms
} satisfies Record<string, SpringParams>
