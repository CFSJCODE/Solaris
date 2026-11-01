import test from "node:test"
import assert from "node:assert/strict"
import { lineDiff, collapse, diffStats } from "../src/components/lineDiff.ts"

test("detects changed, added and removed lines in order", () => {
  const diff = lineDiff("a\nb\nc\nd", "a\nB\nc\nd\ne")
  assert.deepEqual(
    diff.map((l) => `${l.kind}:${l.text}`),
    ["same:a", "del:b", "add:B", "same:c", "same:d", "add:e"],
  )
  assert.deepEqual(diffStats(diff), { added: 2, removed: 1 })
})

test("new files are all additions and CRLF is ignored", () => {
  assert.ok(lineDiff(null, "x\ny").every((l) => l.kind === "add"))
  assert.ok(lineDiff("x\r\ny", "x\ny").every((l) => l.kind === "same"))
})

test("collapse keeps context around changes", () => {
  const before = Array.from({ length: 20 }, (_, i) => `l${i}`).join("\n")
  const after = before.replace("l10", "X")
  const view = collapse(lineDiff(before, after), 2)
  assert.equal(view[0], null)
  assert.equal(view.filter(Boolean).length, 6)
})
