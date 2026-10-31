export interface Point {
  x: number
  y: number
}
export interface AnnotationBox {
  x: number
  y: number
  width: number
  height: number
}
export type Corner = "nw" | "ne" | "sw" | "se"

const clamp = (value: number, maximum: number) => Math.max(0, Math.min(maximum, value))

export function imagePoint(
  clientX: number,
  clientY: number,
  bounds: { left: number; top: number; width: number; height: number },
  width: number,
  height: number,
): Point {
  return {
    x: clamp(((clientX - bounds.left) / bounds.width) * width, width),
    y: clamp(((clientY - bounds.top) / bounds.height) * height, height),
  }
}

export function drawnBox(a: Point, b: Point): AnnotationBox {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    width: Math.abs(a.x - b.x),
    height: Math.abs(a.y - b.y),
  }
}

export function movedBox(
  box: AnnotationBox,
  dx: number,
  dy: number,
  width: number,
  height: number,
): AnnotationBox {
  return {
    ...box,
    x: clamp(box.x + dx, width - box.width),
    y: clamp(box.y + dy, height - box.height),
  }
}

export function resizedBox(
  box: AnnotationBox,
  corner: Corner,
  point: Point,
  width: number,
  height: number,
): AnnotationBox {
  const left = corner.includes("w")
    ? Math.min(clamp(point.x, width), Math.max(0, box.x + box.width - 4))
    : box.x
  const top = corner.includes("n")
    ? Math.min(clamp(point.y, height), Math.max(0, box.y + box.height - 4))
    : box.y
  const right = corner.includes("e")
    ? Math.max(clamp(point.x, width), Math.min(width, box.x + 4))
    : box.x + box.width
  const bottom = corner.includes("s")
    ? Math.max(clamp(point.y, height), Math.min(height, box.y + 4))
    : box.y + box.height
  return { x: left, y: top, width: right - left, height: bottom - top }
}
