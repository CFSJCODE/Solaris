// GLSL ES 3.00 for the SOLARIS Liquid Glass renderer (WebGL2).
//
// One full-screen pass draws:
//   1. the L0 scene (canvas): exactly the Mica background of materials.css
//      (--sol-bg with the ember and gold radial glows), no added texture;
//   2. up to MAX_PANELS glass slabs over that scene, each with
//      - a height field over the WHOLE surface (squircle dome, not only a rim),
//      - Snell refraction per colour channel (subtle dispersion),
//      - Schlick Fresnel, Blinn-Phong specular from a light at the pointer,
//      - spring-driven squash/stretch of the slab (uWobble).
// All colours arrive as uniforms read from the CSS colour tokens: the shader
// contains no colour of its own.

export const MAX_PANELS = 4

/** Upper bound of the specular added over the flat plateau (where text sits). */
export const PLATEAU_SPECULAR_MAX = 0.04 * 0.55 + 0.15 * 0.85

export const VERTEX_SHADER = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`

export const FRAGMENT_SHADER = `#version 300 es
precision highp float;
out vec4 outColor;

#define MAX_PANELS ${MAX_PANELS}

uniform vec2 uRes;          // canvas size in CSS px
uniform float uDpr;
uniform vec3 uBg;           // --sol-bg
uniform vec3 uEmber;        // --sol-ember
uniform vec3 uGold;         // --sol-gold
uniform vec3 uGlow;         // --sol-glow (specular)
uniform vec3 uTint;         // --sol-glass-base (ink-900 / paper)
uniform vec2 uMica;         // --sol-mica-ember, --sol-mica-gold (0..1)
uniform float uTintMix;     // tint over the refracted scene
uniform float uTone;        // multiplicative tone (contrast by composition)
uniform vec3 uLight;        // light position (px, px, height px)

uniform int uPanelCount;
uniform vec4 uPanel[MAX_PANELS];   // x, y, w, h (CSS px, top-left origin)
uniform float uRadius[MAX_PANELS];
uniform vec2 uWobble[MAX_PANELS];  // squash/stretch (sx, sy) − 1

const float IOR = 1.5;
const float DISPERSION = 0.012;
const float THICKNESS = 56.0;      // px of glass under the dome

float sdRoundRect(vec2 p, vec2 halfSize, float r) {
  vec2 q = abs(p) - (halfSize - r);
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

vec3 scene(vec2 p) {
  // Same as .sol-mica: radial-gradient(120% 80% at 0 0, ember mica%, transparent 60%)
  // and radial-gradient(90% 70% at 100% 100%, gold mica%, transparent 55%) over --sol-bg.
  vec2 uv = p / uRes;
  float e = 1.0 - clamp(length(uv / vec2(1.2, 0.8)) / 0.6, 0.0, 1.0);
  float g = 1.0 - clamp(length((uv - 1.0) / vec2(0.9, 0.7)) / 0.55, 0.0, 1.0);
  vec3 c = mix(uBg, uGold, uMica.y * g);
  return mix(c, uEmber, uMica.x * e);
}

float squircle(float u) { return pow(1.0 - pow(1.0 - clamp(u, 0.0, 1.0), 4.0), 0.25); }

// Height of the slab at p (0 outside, up to 1 on the plateau).
float heightAt(vec2 p, vec2 c, vec2 hs, float r, float dome) {
  float d = sdRoundRect(p - c, hs, r);
  return d < 0.0 ? squircle(-d / dome) : 0.0;
}

void main() {
  vec2 p = vec2(gl_FragCoord.x, uRes.y * uDpr - gl_FragCoord.y) / uDpr;
  vec3 col = scene(p);

  for (int i = 0; i < MAX_PANELS; i++) {
    if (i >= uPanelCount) break;
    vec4 rect = uPanel[i];
    vec2 wob = uWobble[i];
    vec2 c = rect.xy + rect.zw * 0.5;
    vec2 hs = rect.zw * 0.5 * (1.0 + wob);
    float r = min(uRadius[i], min(hs.x, hs.y));
    float d = sdRoundRect(p - c, hs, r);
    if (d > 1.5) continue;

    // Dome across the whole slab: half the short side, not a fixed bezel.
    float dome = max(24.0, min(hs.x, hs.y));
    float h = heightAt(p, c, hs, r, dome);
    float e = 1.0;
    float hx = heightAt(p + vec2(e, 0), c, hs, r, dome) - heightAt(p - vec2(e, 0), c, hs, r, dome);
    float hy = heightAt(p + vec2(0, e), c, hs, r, dome) - heightAt(p - vec2(0, e), c, hs, r, dome);
    // Height field H = h · dome/2 (px); normal = normalize(−∂H/∂x, −∂H/∂y, 1),
    // with the central difference spanning 2e px.
    vec3 n = normalize(vec3(-hx * dome * 0.5, -hy * dome * 0.5, 2.0 * e));

    // Snell refraction of a view ray through the dome, per channel.
    vec3 I = vec3(0.0, 0.0, -1.0);
    float travel = THICKNESS * (0.35 + h);
    vec3 tR = refract(I, n, 1.0 / (IOR - DISPERSION));
    vec3 tG = refract(I, n, 1.0 / IOR);
    vec3 tB = refract(I, n, 1.0 / (IOR + DISPERSION));
    vec3 refr = vec3(
      scene(p + tR.xy / max(-tR.z, 0.2) * travel).r,
      scene(p + tG.xy / max(-tG.z, 0.2) * travel).g,
      scene(p + tB.xy / max(-tB.z, 0.2) * travel).b);

    // Contrast by composition: tone the refracted scene, then tint.
    vec3 glass = mix(refr * uTone, uTint, uTintMix);

    // Fresnel (Schlick) + Blinn-Phong from the light above the pointer.
    float cosT = clamp(n.z, 0.0, 1.0);
    float fres = 0.04 + 0.96 * pow(1.0 - cosT, 5.0);
    vec3 L = normalize(uLight - vec3(p, 0.0));
    vec3 H = normalize(L + vec3(0.0, 0.0, 1.0));
    // The plateau keeps only a faint reflection of the light so text stays
    // legible; the full highlight lives on the curved shoulders of the dome.
    float curv = smoothstep(0.02, 0.35, 1.0 - n.z);
    float spec = pow(max(dot(n, H), 0.0), 120.0) * (0.15 + 0.85 * curv);
    float sheen = pow(max(dot(n, H), 0.0), 8.0) * 0.05 * curv;
    glass += uGlow * (fres * 0.55 + spec * 0.85 + sheen);

    float aa = clamp(0.5 - d, 0.0, 1.0);
    col = mix(col, glass, aa);
  }
  outColor = vec4(col, 1.0);
}
`
