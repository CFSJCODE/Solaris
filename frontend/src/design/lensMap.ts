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
        const strength = rimSlope(-d / geometry.bezel)
        // Pull samples inward (−∇sdf points to the centre).
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

const cache = new Map<string, string>()

/** PNG data URL of the lens map; memoised by geometry (rounded to 4 px). */
export function lensMapDataUrl(geometry: LensGeometry): string | null {
  if (typeof document === "undefined") return null
  const key = [geometry.width, geometry.height, geometry.radius, geometry.bezel]
    .map((v) => Math.round(v / 4) * 4)
    .join("x")
  const hit = cache.get(key)
  if (hit) return hit
  const { width, height, data } = buildLensPixels(geometry)
  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d")
  if (!ctx) return null
  ctx.putImageData(new ImageData(data, width, height), 0, 0)
  const url = canvas.toDataURL("image/png")
  if (cache.size > 24) cache.clear()
  cache.set(key, url)
  return url
}
