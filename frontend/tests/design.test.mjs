import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { SPRINGS, springOvershoot, springSettleTime, springToLinear } from "../src/design/spring.ts"
import { buildLensPixels, rimSlope, roundedRectSdf } from "../src/design/lensMap.ts"
import { resolveTier } from "../src/design/materialTier.ts"
import { ELASTIC, SpringValue } from "../src/design/springAnimator.ts"
import { lightAngle } from "../src/design/lightField.ts"
import {
  FRAGMENT_SHADER,
  PLATEAU_SPECULAR_MAX,
  SCENE_WEIGHTS,
} from "../src/design/webgl/glassShader.ts"

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
  // The backdrop is first darkened by brightness(--sol-glass-tone), then tinted.
  const tone = Number(liquid[0].match(/--sol-glass-tone:\s*([\d.]+);/)[1])
  const backdrop = hex("#ffe3b3").map((v) => v * tone)
  const glass = mix(hex("#11141b"), backdrop, tokenPercent("--sol-glass-mix-refract"))
  assert.ok(ratio(hex("#f9f8f6"), glass) >= 4.5, "primary text")
  assert.ok(ratio(hex("#c1c4cb"), glass) >= 4.5, "secondary text")
  // Light theme: paper glass over the darkest ink.
  const light = mix(hex("#fffcf8"), hex("#0b0d12"), tokenPercent("--sol-glass-mix-refract", 1))
  assert.ok(ratio(hex("#20170f"), light) >= 4.5)
  assert.ok(ratio(hex("#625e59"), light) >= 4.5)
})

test("topbar reaches AA for normal text once content scrolls beneath it", () => {
  const tone = Number(liquid[0].match(/--sol-glass-tone:\s*([\d.]+);/)[1])
  const backdrop = hex("#ffe3b3").map((v) => v * tone)
  const scrolled = mix(hex("#11141b"), backdrop, tokenPercent("--sol-glass-mix-scrolled"))
  assert.ok(ratio(hex("#c1c4cb"), scrolled) >= 4.5)
  assert.ok(ratio(hex("#f9f8f6"), scrolled) >= 4.5)
})

test("dark text on accent fills meets AA (Nova conversa, enviar, primário)", () => {
  for (const c of ["#ea6113", "#f88f22", "#fbb931", "#ffe3b3"]) {
    assert.ok(ratio(hex("#0b0d12"), hex(c)) >= 4.5, c)
  }
})

// ── 9. Runtime spring, dynamic light and WebGL glass ─────────────────────
const runSpring = (dt, seconds) => {
  const s = new SpringValue(1, ELASTIC)
  s.target = 0
  let min = 1
  const trace = []
  for (let i = 0, n = Math.round(seconds / dt); i < n; i++) {
    s.step(dt)
    min = Math.min(min, s.value)
    trace.push(s.value)
  }
  return { s, min, trace }
}

test("elastic spring rebounds once, settles and is frame-rate independent", () => {
  const { s, min } = runSpring(1 / 60, 1.2)
  assert.equal(s.value, 0, "settled at the target")
  assert.ok(min < -0.02 && min > -0.12, `single visible overshoot (${min})`)
  const a = runSpring(1 / 30, 0.2).s.value
  const b = runSpring(1 / 150, 0.2).s.value
  assert.ok(Math.abs(a - b) < 0.01, `30 fps vs 150 fps (${a} vs ${b})`)
})

test("spring keeps its velocity when the target changes mid-flight", () => {
  const s = new SpringValue(0, ELASTIC)
  s.target = 1
  for (let i = 0; i < 4; i++) s.step(1 / 60)
  const v = s.velocity
  s.target = 0
  assert.equal(s.velocity, v)
  assert.ok(s.step(1 / 60))
})

test("specular angle points from the surface toward the light", () => {
  // The light rests at (0, 0) outside the browser.
  assert.equal(Math.round(lightAngle({ left: -10, top: 90, width: 20, height: 20 })), 0) // below
  assert.equal(Math.round(lightAngle({ left: -110, top: -10, width: 20, height: 20 })), 90) // left
  assert.equal(Math.round(lightAngle({ left: 90, top: -10, width: 20, height: 20 })), 270) // right
})

test("WebGL shader takes every colour from uniforms (no colours of its own)", () => {
  for (const u of ["uBg", "uEmber", "uFlare", "uGold", "uGlow", "uTint"]) {
    assert.match(FRAGMENT_SHADER, new RegExp(`uniform vec3 ${u};`))
  }
  // Only direction/position vectors may be literal vec3s.
  const literals = [...FRAGMENT_SHADER.matchAll(/vec3\(([^()]*)\)/g)].map((m) => m[1].trim())
  for (const l of literals) {
    assert.ok(/^0\.0, 0\.0, -?1\.0$|^p, 0\.0$|^-hx/.test(l), `literal vec3(${l})`)
  }
})

test("text on WebGL glass keeps AA contrast over the brightest scene", () => {
  const percent = (name, theme) =>
    Number([...liquid[0].matchAll(new RegExp(`${name}:\\s*([\\d.]+)%?;`, "g"))][theme][1])
  for (const [theme, base, texts, gainTheme] of [
    [0, "#0b0d12", ["#f9f8f6", "#c1c4cb"], 0],
    [1, "#fffcf8", ["#20170f", "#625e59"], 1],
  ]) {
    const gain = theme ? percent("--sol-scene-gain", 1) : percent("--sol-scene-gain", 0)
    // Upper bound: every light field at its peak at the same pixel.
    let scene = hex(base)
    scene = mix(hex("#ea6113"), scene, SCENE_WEIGHTS.ember * gain)
    scene = mix(hex("#fbb931"), scene, SCENE_WEIGHTS.gold * gain)
    scene = mix(hex("#f88f22"), scene, SCENE_WEIGHTS.flare * gain)
    const specular = theme ? hex(base) : hex("#ffe3b3")
    scene = mix(specular, scene, SCENE_WEIGHTS.silk * gain)
    const tone = percent("--sol-glass-tone-webgl", theme)
    const tint = theme ? hex("#fffcf8") : hex("#11141b")
    let glass = mix(
      tint,
      scene.map((v) => v * tone),
      percent("--sol-glass-mix-webgl", theme) / 100,
    )
    glass = glass.map((v, i) => Math.min(255, v + specular[i] * PLATEAU_SPECULAR_MAX))
    for (const t of texts) {
      assert.ok(ratio(hex(t), glass) >= 4.5, `theme ${theme}: ${t} → ${ratio(hex(t), glass)}`)
    }
  }
})
