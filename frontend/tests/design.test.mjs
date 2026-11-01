import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { SPRINGS, springOvershoot, springSettleTime, springToLinear } from "../src/design/spring.ts"
import { buildLensPixels, rimSlope, roundedRectSdf } from "../src/design/lensMap.ts"
import { resolveTier } from "../src/design/materialTier.ts"

const css = (p) => readFileSync(new URL(p, import.meta.url), "utf8")
const solaris = css("../src/styles/solaris.css")
const liquid = ["tokens", "materials", "components"].map((f) =>
  css(`../src/styles/liquid/${f}.css`),
)

// ── 1. Color tokens are immutable ─────────────────────────────────────────
const ORIGINAL_PALETTE = {
  "--sol-ember": "#ea6113",
  "--sol-flare": "#f88f22",
  "--sol-gold": "#fbb931",
  "--sol-glow": "#ffe3b3",
  "--sol-ink-950": "#0b0d12",
  "--sol-ink-900": "#11141b",
  "--sol-ink-850": "#171b25",
  "--sol-ink-800": "#202632",
  "--sol-success": "#37be91",
  "--sol-warning": "#f5bd54",
  "--sol-error": "#ff7776",
  "--sol-info": "#7eafff",
}

test("original palette values are unchanged in solaris.css", () => {
  for (const [token, hex] of Object.entries(ORIGINAL_PALETTE)) {
    assert.match(solaris, new RegExp(`${token}:\\s*${hex};`), token)
  }
})

test("liquid layers never redefine color tokens nor introduce literal colors", () => {
  const colorTokens = [
    ...solaris.matchAll(/(--sol-[a-z0-9-]+):\s*(#|rgba?\(|linear-gradient)/g),
  ].map((m) => m[1])
  for (const file of liquid) {
    for (const token of colorTokens) {
      assert.doesNotMatch(file, new RegExp(`\\s${token}\\s*:`), `${token} redefined`)
    }
    const code = file.replace(/\/\*[\s\S]*?\*\//g, "")
    // Only literal allowed: the pre-existing active-conversation tint (gold 10 %).
    const literals = (code.match(/#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)/gi) ?? []).filter(
      (l) => l.replace(/\s/g, "") !== "rgba(251,185,49,0.1)",
    )
    assert.deepEqual(literals, [])
  }
})

// ── 5. Motion tokens follow the spring model ──────────────────────────────
test("CSS spring easings are the sampled spring solutions", () => {
  for (const [name, params] of Object.entries(SPRINGS)) {
    const { easing, durationMs } = springToLinear(params, 24)
    const flat = liquid[0].replace(/\s+/g, "").replace(/,\)/g, ")")
    assert.ok(flat.includes(`--sol-ease-spring-${name}:${easing.replace(/\s+/g, "")};`), name)
    assert.ok(liquid[0].includes(`--sol-spring-${name}-dur: ${durationMs}ms;`), name)
  }
})

test("springs settle inside the directive's windows without oscillating", () => {
  const window = { snappy: [100, 180], smooth: [180, 300], gentle: [240, 400] }
  for (const [name, params] of Object.entries(SPRINGS)) {
    const ms = springSettleTime(params) * 1000
    assert.ok(ms >= window[name][0] && ms <= window[name][1], `${name} ${ms}ms`)
    assert.ok(springOvershoot(params) < 0.01, `${name} overshoot`)
  }
})

// ── 2. Material: lens geometry ────────────────────────────────────────────
test("rounded-rect SDF is negative inside and zero on the boundary", () => {
  const g = { width: 200, height: 80, radius: 20 }
  assert.ok(roundedRectSdf(100, 40, g) < 0)
  assert.ok(Math.abs(roundedRectSdf(0, 40, g)) < 1e-9)
  assert.ok(roundedRectSdf(1, 1, g) > 0) // outside the rounded corner
})

test("rim slope is maximal at the edge and flat in the centre", () => {
  assert.equal(rimSlope(0), 1)
  assert.equal(rimSlope(1), 0)
  assert.ok(rimSlope(0.1) > rimSlope(0.4))
})

test("lens map leaves the centre undisplaced and pulls the rim inward", () => {
  const { width, height, data } = buildLensPixels(
    { width: 200, height: 80, radius: 24, bezel: 18 },
    1,
  )
  const px = (x, y) => data.subarray((y * width + x) * 4, (y * width + x) * 4 + 2)
  assert.deepEqual([...px(100, 40)], [128, 128]) // centre: neutral
  const [rLeft] = px(2, 40)
  const [rRight] = px(width - 3, 40)
  assert.ok(rLeft > 160, "left rim samples toward +x")
  assert.ok(rRight < 96, "right rim samples toward −x")
  const [, gTop] = px(100, 2)
  assert.ok(gTop > 160, "top rim samples toward +y")
  assert.equal(height, 80)
})

// ── 6. Accessibility: tier resolution ─────────────────────────────────────
const env = {
  forcedColors: false,
  reducedTransparency: false,
  moreContrast: false,
  supportsBackdrop: true,
  supportsBackdropUrl: true,
  hardwareConcurrency: 12,
  deviceMemoryGb: 8,
  saveData: false,
}

test("material tier follows capability and accessibility signals", () => {
  assert.equal(resolveTier("auto", env), "liquid")
  assert.equal(resolveTier("auto", { ...env, supportsBackdropUrl: false }), "glass")
  assert.equal(resolveTier("auto", { ...env, moreContrast: true }), "solid")
  assert.equal(resolveTier("auto", { ...env, hardwareConcurrency: 2 }), "glass")
  assert.equal(resolveTier("liquid", { ...env, reducedTransparency: true }), "solid")
  assert.equal(resolveTier("liquid", { ...env, forcedColors: true }), "solid")
  assert.equal(resolveTier("solid", env), "solid")
  assert.equal(resolveTier("liquid", { ...env, supportsBackdrop: false }), "solid")
})

// ── 8. Contrast (WCAG 2.2) on the worst-case composited glass ────────────
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
const lin = (c) => {
  c /= 255
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
const ratio = (a, b) => {
  const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}
const mix = (a, b, t) => a.map((v, i) => v * t + b[i] * (1 - t))

const tokenPercent = (name, theme = 0) =>
  Number([...liquid[0].matchAll(new RegExp(`${name}:\\s*(\\d+)%`, "g"))][theme][1]) / 100

test("text on refractive glass keeps AA contrast over the brightest backdrop", () => {
  // Worst case: dark glass over the lightest palette color (glow), no blur averaging.
  const glass = mix(hex("#11141b"), hex("#ffe3b3"), tokenPercent("--sol-glass-mix-refract"))
  assert.ok(ratio(hex("#f9f8f6"), glass) >= 4.5, "primary text")
  assert.ok(ratio(hex("#c1c4cb"), glass) >= 4.5, "secondary text")
  // Light theme: paper glass over the darkest ink.
  const light = mix(hex("#fffcf8"), hex("#0b0d12"), tokenPercent("--sol-glass-mix-refract", 1))
  assert.ok(ratio(hex("#20170f"), light) >= 4.5)
  assert.ok(ratio(hex("#625e59"), light) >= 4.5)
})

test("topbar reaches AA for normal text once content scrolls beneath it", () => {
  const scrolled = mix(hex("#11141b"), hex("#ffe3b3"), tokenPercent("--sol-glass-mix-scrolled"))
  assert.ok(ratio(hex("#f9f8f6"), scrolled) >= 4.5)
})

test("dark text on accent fills meets AA (Nova conversa, enviar, primário)", () => {
  for (const c of ["#ea6113", "#f88f22", "#fbb931", "#ffe3b3"]) {
    assert.ok(ratio(hex("#0b0d12"), hex(c)) >= 4.5, c)
  }
})
