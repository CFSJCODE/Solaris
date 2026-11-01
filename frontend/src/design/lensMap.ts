// Displacement map for the Liquid Glass lens (SVG feDisplacementMap).
//
// For a rounded rectangle we evaluate its signed distance field (SDF)
//
//   q   = |p - c| - (h - r)
//   sdf = |max(q, 0)| + min(max(q.x, q.y), 0) - r        (< 0 inside)
//
// Inside an edge band of width `bezel`, the glass is modelled as a convex
// "squircle" profile  h(u) = (1 - (1 - u)^4)^(1/4),  u = depth / bezel ∈ [0, 1].
// Snell refraction through a slope dh/du bends rays toward the centre, so the
// sampled background is pulled inward along −∇sdf with a magnitude that grows
// with the slope (strong at the rim, zero on the flat top). That produces the
// lens magnification at the edges while the centre stays undistorted and
// therefore readable.
//
// Encoding (feDisplacementMap, xChannel=R, yChannel=G):
//   P'(x, y) = P(x + scale * (R/255 - 0.5), y + scale * (G/255 - 0.5))
// so R = 128 + 127 * dx, G = 128 + 127 * dy with (dx, dy) ∈ [-1, 1]².

export interface LensGeometry {
  width: number
  height: number
  radius: number
  /** Width of the refracting rim, in px. */
  bezel: number
}

export function roundedRectSdf(
  x: number,
  y: number,
  { width, height, radius }: Pick<LensGeometry, "width" | "height" | "radius">,
): number {
  const hx = width / 2
  const hy = height / 2
  const r = Math.min(radius, hx, hy)
  const qx = Math.abs(x - hx) - (hx - r)
  const qy = Math.abs(y - hy) - (hy - r)
  const outside = Math.hypot(Math.max(qx, 0), Math.max(qy, 0))
  return outside + Math.min(Math.max(qx, qy), 0) - r
}

/** Slope of the squircle rim profile at normalised depth u (0 = edge, 1 = flat). */
export function rimSlope(u: number): number {
  if (u <= 0) return 1
  if (u >= 1) return 0
  const a = 1 - Math.pow(1 - u, 4)
  // d/du (1 - (1-u)^4)^(1/4) = (1-u)^3 * a^(-3/4); normalised to 1 at the rim.
  const slope = Math.pow(1 - u, 3) * Math.pow(a, -0.75)
  return Math.min(1, slope / 4)
}

/** Squircle height profile h(u) = (1 − (1 − u)^4)^(1/4), u ∈ [0, 1]. */
export function squircleHeight(u: number): number {
  if (u <= 0) return 0
  if (u >= 1) return 1
  return Math.pow(1 - Math.pow(1 - u, 4), 0.25)
}

export const REFRACTIVE_INDEX = 1.5
const THICKNESS = 0.6
const LUT_SIZE = 128

/**
 * Snell refraction look-up table over the rim depth u ∈ [0, 1].
 *
 * A vertical ray hits the glass surface whose normal is tilted by
 * θ = atan(dh/dx); inside the glass it travels at θt = asin(sin θ / n).
 * The angular deviation δ = θ − θt, carried through the slab thickness
 * (t + h), shifts the sampled background by  (t + h) · tan δ.
 * Values are normalised so the strongest displacement is 1.
 */
export function snellLut(n = REFRACTIVE_INDEX, size = LUT_SIZE): Float32Array {
  const lut = new Float32Array(size)
  const du = 1 / (size - 1)
  let max = 0
  for (let i = 0; i < size; i++) {
    const u = i * du
    const u0 = Math.max(0, u - du / 2)
    const u1 = Math.min(1, u + du / 2)
    // Slope in "rim widths": the bezel is the horizontal extent of the curve.
    const slope = (squircleHeight(u1) - squircleHeight(u0)) / (u1 - u0 || 1)
    const theta = Math.atan(slope)
    const thetaT = Math.asin(Math.sin(theta) / n)
    const shift = (THICKNESS + squircleHeight(u)) * Math.tan(theta - thetaT)
    lut[i] = shift
    max = Math.max(max, shift)
  }
  for (let i = 0; i < size; i++) lut[i] = max ? lut[i] / max : 0
  return lut
}

const LUT = snellLut()

function lutAt(u: number): number {
  const x = Math.min(1, Math.max(0, u)) * (LUT.length - 1)
  const i = Math.floor(x)
  const f = x - i
  return i + 1 < LUT.length ? LUT[i] * (1 - f) + LUT[i + 1] * f : LUT[i]
}

/**
 * Build RGBA pixels for the displacement map. `scale` < 1 renders a smaller
 * map that the SVG filter stretches back, which keeps CPU cost proportional
 * to the visible rim instead of the whole surface.
 */
export function buildLensPixels(
  geometry: LensGeometry,
  scale = 0.5,
): {
  width: number
  height: number
  data: Uint8ClampedArray<ArrayBuffer>
} {
  const w = Math.max(2, Math.round(geometry.width * scale))
  const h = Math.max(2, Math.round(geometry.height * scale))
  const data = new Uint8ClampedArray(new ArrayBuffer(w * h * 4))
  const e = 0.75 // central-difference step, in source px
  for (let j = 0; j < h; j++) {
    for (let i = 0; i < w; i++) {
      const x = (i + 0.5) / scale
      const y = (j + 0.5) / scale
      const d = roundedRectSdf(x, y, geometry)
      let dx = 0
      let dy = 0
      if (d < 0 && -d < geometry.bezel) {
        const gx = roundedRectSdf(x + e, y, geometry) - roundedRectSdf(x - e, y, geometry)
        const gy = roundedRectSdf(x, y + e, geometry) - roundedRectSdf(x, y - e, geometry)
        const len = Math.hypot(gx, gy) || 1
        const strength = lutAt(-d / geometry.bezel)
        // Convex lens: sample toward the centre (−∇sdf), magnifying the rim.
        dx = (-gx / len) * strength
        dy = (-gy / len) * strength
      }
      const k = (j * w + i) * 4
      data[k] = Math.round(128 + 127 * dx)
      data[k + 1] = Math.round(128 + 127 * dy)
      data[k + 2] = 128
      data[k + 3] = 255
    }
  }
  return { width: w, height: h, data }
}

/**
 * Specular mask along the contour (alpha only; the colour comes from the
 * existing `--sol-specular` token through CSS `mask-image`).
 *
 * For each rim pixel the outward normal N = ∇sdf is compared with the light
 * direction L (top-left, matching `--sol-light-angle`):
 *   key   = max(0, N·L)^1.5     bright arc facing the light
 *   back  = max(0, −N·L)^2      dimmer internal reflection on the far side
 * attenuated by depth into the glass (a crisp ~1.5 px line plus a soft
 * 6 px glow), which gives the edge a sense of thickness.
 *
 * With `light = null` the mask is uniform along the contour (key = 1) and the
 * direction comes from the live light instead (conic gradient, materials.css).
 */
export function buildSpecularPixels(
  geometry: LensGeometry,
  light: { x: number; y: number } | null = { x: -0.45, y: -0.89 },
): { width: number; height: number; data: Uint8ClampedArray<ArrayBuffer> } {
  const w = Math.max(2, Math.round(geometry.width))
  const h = Math.max(2, Math.round(geometry.height))
  const data = new Uint8ClampedArray(new ArrayBuffer(w * h * 4))
  const lLen = light ? Math.hypot(light.x, light.y) || 1 : 1
  const lx = light ? light.x / lLen : 0
  const ly = light ? light.y / lLen : 0
  const e = 0.5
  for (let j = 0; j < h; j++) {
    for (let i = 0; i < w; i++) {
      const x = i + 0.5
      const y = j + 0.5
      const d = roundedRectSdf(x, y, geometry)
      if (d > 0.5 || d < -7) continue
      const gx = roundedRectSdf(x + e, y, geometry) - roundedRectSdf(x - e, y, geometry)
      const gy = roundedRectSdf(x, y + e, geometry) - roundedRectSdf(x, y - e, geometry)
      const len = Math.hypot(gx, gy) || 1
      const ndl = (gx / len) * lx + (gy / len) * ly
      // light = null: omnidirectional mask; direction is applied in CSS by a
      // conic gradient that rotates with the live light (lightField.ts).
      const key = light ? Math.pow(Math.max(0, ndl), 1.5) : 1
      const back = light ? 0.45 * Math.pow(Math.max(0, -ndl), 2) : 0
      const depth = -d
      const line = Math.max(0, 1 - Math.abs(depth - 0.75) / 1.25) // ~1.5 px crisp rim
      const glow = depth < 7 ? 0.28 * (1 - depth / 7) ** 2 : 0
      const a = Math.min(1, (key + back) * (line + glow) + 0.12 * line)
      const k = (j * w + i) * 4
      data[k] = 255
      data[k + 1] = 255
      data[k + 2] = 255
      data[k + 3] = Math.round(a * 255)
    }
  }
  return { width: w, height: h, data }
}

const cache = new Map<string, string>()

function toDataUrl(
  key: string,
  build: () => { width: number; height: number; data: Uint8ClampedArray<ArrayBuffer> },
): string | null {
  if (typeof document === "undefined") return null
  const hit = cache.get(key)
  if (hit) {
    // LRU: refresh recency.
    cache.delete(key)
    cache.set(key, hit)
    return hit
  }
  const { width, height, data } = build()
  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d")
  if (!ctx) return null
  ctx.putImageData(new ImageData(data, width, height), 0, 0)
  const url = canvas.toDataURL("image/png")
  if (cache.size >= 48) cache.delete(cache.keys().next().value as string)
  cache.set(key, url)
  return url
}

const geometryKey = (g: LensGeometry) =>
  [g.width, g.height, g.radius, g.bezel].map((v) => Math.round(v)).join("x")

/** PNG data URL of the lens map; LRU-memoised by geometry. */
export function lensMapDataUrl(geometry: LensGeometry): string | null {
  const scale = geometry.width * geometry.height > 32000 ? 0.5 : 1
  return toDataUrl(`lens:${geometryKey(geometry)}`, () => buildLensPixels(geometry, scale))
}

/** PNG data URL of the (omnidirectional) specular contour mask; LRU-memoised by geometry. */
export function specularMapDataUrl(geometry: LensGeometry): string | null {
  return toDataUrl(`spec:${geometryKey(geometry)}`, () => buildSpecularPixels(geometry, null))
}

/** Full-surface lens: the dome spans half the short side (not a fixed rim). */
export function domeBezel(width: number, height: number): number {
  return Math.max(12, Math.min(width, height) / 2)
}
