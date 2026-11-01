// WebGL2 renderer for the L0 scene and the WebGL glass slabs.
//
// Renders on demand only: a frame is drawn when the light moves, the viewport
// or a panel changes, or a spring is in flight. Nothing runs while idle.
// Colours are read from the CSS tokens, so the palette stays the single source.

import { FRAGMENT_SHADER, MAX_PANELS, VERTEX_SHADER } from "./glassShader"

export interface GlassPanel {
  x: number
  y: number
  width: number
  height: number
  radius: number
  /** Spring deformation (sx − 1, sy − 1). */
  wobble: [number, number]
}

export interface GlassUniforms {
  bg: RGB
  ember: RGB
  gold: RGB
  glow: RGB
  tint: RGB
  mica: [number, number]
  tintMix: number
  tone: number
}

type RGB = [number, number, number]

const UNIFORMS = [
  "uRes",
  "uDpr",
  "uBg",
  "uEmber",
  "uGold",
  "uGlow",
  "uTint",
  "uMica",
  "uTintMix",
  "uTone",
  "uLight",
  "uPanelCount",
  "uPanel",
  "uRadius",
  "uWobble",
] as const

type UniformName = (typeof UNIFORMS)[number]

/** Max device-pixel ratio: the scene is soft, 1.5× is visually lossless. */
export const MAX_DPR = 1.5

function compile(gl: WebGL2RenderingContext, type: number, source: string) {
  const shader = gl.createShader(type)!
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader)
    gl.deleteShader(shader)
    throw new Error(`GLSL: ${log}`)
  }
  return shader
}

export class GlassRenderer {
  private gl: WebGL2RenderingContext
  private loc = {} as Record<UniformName, WebGLUniformLocation | null>
  private width = 0
  private height = 0
  private dpr = 1

  constructor(private canvas: HTMLCanvasElement) {
    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: "low-power",
      preserveDrawingBuffer: false,
    })
    if (!gl) throw new Error("WebGL2 indisponível")
    this.gl = gl
    const program = gl.createProgram()!
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX_SHADER))
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER))
    gl.bindAttribLocation(program, 0, "aPos")
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`GLSL link: ${gl.getProgramInfoLog(program)}`)
    }
    gl.useProgram(program)
    for (const name of UNIFORMS) {
      const arr = name === "uPanel" || name === "uRadius" || name === "uWobble"
      this.loc[name] = gl.getUniformLocation(program, arr ? `${name}[0]` : name)
    }
    // One full-screen triangle.
    const vao = gl.createVertexArray()
    gl.bindVertexArray(vao)
    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    gl.enableVertexAttribArray(0)
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)
  }

  get lost() {
    return this.gl.isContextLost()
  }

  resize(width: number, height: number, devicePixelRatio: number) {
    this.dpr = Math.min(MAX_DPR, Math.max(1, devicePixelRatio))
    this.width = width
    this.height = height
    this.canvas.width = Math.max(1, Math.round(width * this.dpr))
    this.canvas.height = Math.max(1, Math.round(height * this.dpr))
    this.gl.viewport(0, 0, this.canvas.width, this.canvas.height)
  }

  render(u: GlassUniforms, light: [number, number, number], panels: GlassPanel[]) {
    const { gl, loc } = this
    gl.uniform2f(loc.uRes, this.width, this.height)
    gl.uniform1f(loc.uDpr, this.dpr)
    gl.uniform3fv(loc.uBg, u.bg)
    gl.uniform3fv(loc.uEmber, u.ember)
    gl.uniform3fv(loc.uGold, u.gold)
    gl.uniform3fv(loc.uGlow, u.glow)
    gl.uniform3fv(loc.uTint, u.tint)
    gl.uniform2f(loc.uMica, u.mica[0], u.mica[1])
    gl.uniform1f(loc.uTintMix, u.tintMix)
    gl.uniform1f(loc.uTone, u.tone)
    gl.uniform3fv(loc.uLight, light)

    const n = Math.min(MAX_PANELS, panels.length)
    const rects = new Float32Array(MAX_PANELS * 4)
    const radii = new Float32Array(MAX_PANELS)
    const wobble = new Float32Array(MAX_PANELS * 2)
    for (let i = 0; i < n; i++) {
      const p = panels[i]
      rects.set([p.x, p.y, p.width, p.height], i * 4)
      radii[i] = p.radius
      wobble.set(p.wobble, i * 2)
    }
    gl.uniform1i(loc.uPanelCount, n)
    gl.uniform4fv(loc.uPanel, rects)
    gl.uniform1fv(loc.uRadius, radii)
    gl.uniform2fv(loc.uWobble, wobble)
    gl.drawArrays(gl.TRIANGLES, 0, 3)
  }
}

/** Parse a computed CSS colour (`rgb(…)`, `rgba(…)` or `#rrggbb`) to linear-ish 0..1 sRGB. */
export function parseCssColor(value: string): RGB | null {
  const v = value.trim()
  const hex = /^#([0-9a-f]{6})$/i.exec(v)
  if (hex) {
    const n = parseInt(hex[1], 16)
    return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
  }
  const rgb = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(v)
  if (rgb) return [+rgb[1] / 255, +rgb[2] / 255, +rgb[3] / 255]
  return null
}

/**
 * Read the shader inputs from the CSS tokens. Custom properties holding
 * `var()` chains are resolved by assigning them to a probe's `color`.
 */
export function readGlassUniforms(root: HTMLElement = document.documentElement): GlassUniforms {
  const probe = document.createElement("span")
  probe.style.display = "none"
  root.appendChild(probe)
  const color = (token: string, fallback: RGB): RGB => {
    probe.style.color = `var(${token})`
    return parseCssColor(getComputedStyle(probe).color) ?? fallback
  }
  const css = getComputedStyle(root)
  const num = (token: string, fallback: number) => {
    const raw = css.getPropertyValue(token).trim()
    const n = parseFloat(raw)
    return Number.isFinite(n) ? (raw.endsWith("%") ? n / 100 : n) : fallback
  }
  const black: RGB = [0, 0, 0]
  const u: GlassUniforms = {
    bg: color("--sol-bg", black),
    ember: color("--sol-ember", black),
    gold: color("--sol-gold", black),
    glow: color("--sol-specular", black),
    tint: color("--sol-glass-base", black),
    mica: [num("--sol-mica-ember", 0.11), num("--sol-mica-gold", 0.06)],
    tintMix: num("--sol-glass-mix-webgl", 0.4),
    tone: num("--sol-glass-tone-webgl", 0.85),
  }
  probe.remove()
  return u
}
