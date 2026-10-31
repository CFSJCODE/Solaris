import test from "node:test"
import assert from "node:assert/strict"
import { imagePoint, drawnBox, movedBox, resizedBox } from "../src/components/annotationGeometry.ts"

test("scaled pointer positions map to source pixels and stay inside the image", () => {
  const bounds = { left: 40, top: 20, width: 320, height: 240 }
  assert.deepEqual(imagePoint(200, 140, bounds, 640, 480), { x: 320, y: 240 })
  assert.deepEqual(imagePoint(0, 900, bounds, 640, 480), { x: 0, y: 480 })
})
test("drawing works in every drag direction", () => {
  assert.deepEqual(drawnBox({ x: 120, y: 100 }, { x: 20, y: 40 }), {
    x: 20,
    y: 40,
    width: 100,
    height: 60,
  })
})
test("moving preserves size and prevents boxes leaving the frame", () => {
  assert.deepEqual(movedBox({ x: 10, y: 20, width: 100, height: 80 }, 900, -900, 640, 480), {
    x: 540,
    y: 0,
    width: 100,
    height: 80,
  })
})
test("resizing clamps to borders and prevents inverted boxes", () => {
  const box = { x: 100, y: 100, width: 80, height: 60 }
  assert.deepEqual(resizedBox(box, "se", { x: 999, y: 999 }, 640, 480), {
    x: 100,
    y: 100,
    width: 540,
    height: 380,
  })
  assert.deepEqual(resizedBox(box, "nw", { x: 999, y: 999 }, 640, 480), {
    x: 176,
    y: 156,
    width: 4,
    height: 4,
  })
})
test("tiny detections at the border do not resize outside the image", () => {
  assert.deepEqual(
    resizedBox({ x: 639, y: 479, width: 1, height: 1 }, "se", { x: 900, y: 900 }, 640, 480),
    { x: 639, y: 479, width: 1, height: 1 },
  )
  assert.deepEqual(
    resizedBox({ x: 0, y: 0, width: 1, height: 1 }, "nw", { x: -5, y: -5 }, 640, 480),
    { x: 0, y: 0, width: 1, height: 1 },
  )
})
