import type { WordEntry } from '../types/domain'

export interface EntrySelectionResult {
  entries: WordEntry[]
  invalidTokens: string[]
}

export const parseEntrySelection = (
  expression: string,
  entries: WordEntry[],
): EntrySelectionResult => {
  const normalized = expression.trim().toLowerCase()
  if (!normalized || normalized === 'all' || normalized === '*') {
    return { entries, invalidTokens: [] }
  }

  const tokens = normalized
    .split(/[,，;；\n\s]+/)
    .map((token) => token.trim())
    .filter(Boolean)
  const indexes = new Set<number>()
  const invalidTokens: string[] = []

  tokens.forEach((token) => {
    if (/^\d+$/.test(token)) {
      const index = Number(token)
      if (index >= 1 && index <= entries.length) {
        indexes.add(index - 1)
      } else {
        invalidTokens.push(token)
      }
      return
    }

    const range = token.match(/^(\d+)\s*(?:-|~|—|至)\s*(\d+)$/)
    if (range) {
      const start = Number(range[1])
      const end = Number(range[2])
      if (start < 1 || end < 1 || start > entries.length || end > entries.length) {
        invalidTokens.push(token)
        return
      }
      const from = Math.min(start, end)
      const to = Math.max(start, end)
      for (let index = from; index <= to; index += 1) {
        indexes.add(index - 1)
      }
      return
    }

    invalidTokens.push(token)
  })

  return {
    entries: entries.filter((_, index) => indexes.has(index)),
    invalidTokens,
  }
}
