// Diferença por linhas (LCS) usada para revisar propostas de edição antes da gravação.
export type DiffLine = {
  kind: "same" | "add" | "del"
  text: string
  oldNo?: number
  newNo?: number
}

const MAX_CELLS = 4_000_000

export function lineDiff(before: string | null, after: string): DiffLine[] {
  const a = before === null ? [] : before.replace(/\r\n/g, "\n").split("\n")
  const b = after.replace(/\r\n/g, "\n").split("\n")
  // Prefixo e sufixo comuns reduzem a matriz em edições localizadas.
  let start = 0
  while (start < a.length && start < b.length && a[start] === b[start]) start++
  let endA = a.length
  let endB = b.length
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA--
    endB--
  }
  const midA = a.slice(start, endA)
  const midB = b.slice(start, endB)
  const out: DiffLine[] = a
    .slice(0, start)
    .map((text, i) => ({ kind: "same", text, oldNo: i + 1, newNo: i + 1 }))
  if (midA.length * midB.length > MAX_CELLS) {
    midA.forEach((text, i) => out.push({ kind: "del", text, oldNo: start + i + 1 }))
    midB.forEach((text, i) => out.push({ kind: "add", text, newNo: start + i + 1 }))
  } else {
    const n = midA.length
    const m = midB.length
    const table = new Uint32Array((n + 1) * (m + 1))
    for (let i = n - 1; i >= 0; i--)
      for (let j = m - 1; j >= 0; j--)
        table[i * (m + 1) + j] =
          midA[i] === midB[j]
            ? table[(i + 1) * (m + 1) + j + 1] + 1
            : Math.max(table[(i + 1) * (m + 1) + j], table[i * (m + 1) + j + 1])
    let i = 0
    let j = 0
    while (i < n || j < m) {
      if (i < n && j < m && midA[i] === midB[j]) {
        out.push({ kind: "same", text: midA[i], oldNo: start + i + 1, newNo: start + j + 1 })
        i++
        j++
      } else if (i < n && (j === m || table[(i + 1) * (m + 1) + j] >= table[i * (m + 1) + j + 1])) {
        out.push({ kind: "del", text: midA[i], oldNo: start + i + 1 })
        i++
      } else {
        out.push({ kind: "add", text: midB[j], newNo: start + j + 1 })
        j++
      }
    }
  }
  a.slice(endA).forEach((text, k) =>
    out.push({ kind: "same", text, oldNo: endA + k + 1, newNo: endB + k + 1 }),
  )
  return out
}

/** Mantém só as linhas alteradas e `context` linhas ao redor; `null` marca um intervalo omitido. */
export function collapse(lines: DiffLine[], context = 3): (DiffLine | null)[] {
  const keep = new Array(lines.length).fill(false)
  lines.forEach((line, i) => {
    if (line.kind !== "same")
      for (let k = Math.max(0, i - context); k <= Math.min(lines.length - 1, i + context); k++)
        keep[k] = true
  })
  const out: (DiffLine | null)[] = []
  lines.forEach((line, i) => {
    if (keep[i]) out.push(line)
    else if (out[out.length - 1] !== null) out.push(null)
  })
  return out
}

export function diffStats(lines: DiffLine[]): { added: number; removed: number } {
  return {
    added: lines.filter((l) => l.kind === "add").length,
    removed: lines.filter((l) => l.kind === "del").length,
  }
}
