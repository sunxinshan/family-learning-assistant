import { readSheet } from 'read-excel-file/browser'
import writeExcelFile from 'write-excel-file/browser'
import type { WordEntry } from '../types/domain'

export interface VocabularyParseResult {
  entries: WordEntry[]
  errors: string[]
  headers: string[]
}

const WORD_HEADERS = ['word', '单词', '词形', '词汇']
const PHONETIC_HEADERS = ['phonetic', '音标', '发音']
const PART_OF_SPEECH_HEADERS = ['partofspeech', 'part_of_speech', '词性']
const MEANING_HEADERS = ['meaning', 'meanings', '词义', '释义', '中文释义']
const EXAMPLE_HEADERS = ['example', '例句', '英文例句']
const EXAMPLE_TRANSLATION_HEADERS = [
  'exampletranslation',
  'example_translation',
  '例句翻译',
  '翻译',
]

const normalizeHeader = (value: unknown): string =>
  String(value ?? '')
    .replace(/^\uFEFF/, '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_')

const cellText = (value: unknown): string =>
  value === null || value === undefined ? '' : String(value).trim()

const findColumn = (headers: string[], candidates: string[]): number =>
  headers.findIndex((header) => candidates.includes(header))

export const parseCsvRows = (text: string): string[][] => {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    const next = text[index + 1]
    if (char === '"') {
      if (quoted && next === '"') {
        cell += '"'
        index += 1
      } else {
        quoted = !quoted
      }
      continue
    }
    if (char === ',' && !quoted) {
      row.push(cell)
      cell = ''
      continue
    }
    if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && next === '\n') index += 1
      row.push(cell)
      if (row.some((value) => value.trim())) rows.push(row)
      row = []
      cell = ''
      continue
    }
    cell += char
  }
  row.push(cell)
  if (row.some((value) => value.trim())) rows.push(row)
  return rows
}

const rowsToEntries = (rows: unknown[][]): VocabularyParseResult => {
  if (!rows.length) {
    return { entries: [], errors: ['文件内容为空'], headers: [] }
  }
  const rawHeaders = rows[0].map(normalizeHeader)
  const headers = rows[0].map((header) => cellText(header))
  const wordIndex = findColumn(rawHeaders, WORD_HEADERS)
  const meaningIndex = findColumn(rawHeaders, MEANING_HEADERS)
  if (wordIndex === -1) {
    return {
      entries: [],
      errors: ['未找到“单词 / word”列，请使用模板中的列名'],
      headers,
    }
  }
  if (meaningIndex === -1) {
    return {
      entries: [],
      errors: ['未找到“词义 / meaning”列，请使用模板中的列名'],
      headers,
    }
  }

  const phoneticIndex = findColumn(rawHeaders, PHONETIC_HEADERS)
  const partOfSpeechIndex = findColumn(rawHeaders, PART_OF_SPEECH_HEADERS)
  const exampleIndex = findColumn(rawHeaders, EXAMPLE_HEADERS)
  const translationIndex = findColumn(rawHeaders, EXAMPLE_TRANSLATION_HEADERS)
  const entries: WordEntry[] = []
  const errors: string[] = []
  const seen = new Set<string>()

  rows.slice(1).forEach((row, rowIndex) => {
    const word = cellText(row[wordIndex])
    if (!word) {
      if (row.some((value) => cellText(value))) {
        errors.push(`第 ${rowIndex + 2} 行缺少单词，已跳过`)
      }
      return
    }
    const key = word.toLowerCase()
    if (seen.has(key)) {
      errors.push(`第 ${rowIndex + 2} 行“${word}”重复，已跳过`)
      return
    }
    const meanings = cellText(row[meaningIndex])
      .split(/[;；\n]/)
      .map((item) => item.trim())
      .filter(Boolean)
    if (!meanings.length) {
      errors.push(`第 ${rowIndex + 2} 行“${word}”缺少词义，已跳过`)
      return
    }
    seen.add(key)
    entries.push({
      id: `word-${crypto.randomUUID()}`,
      word,
      phonetic: phoneticIndex >= 0 ? cellText(row[phoneticIndex]) : '',
      partOfSpeech: partOfSpeechIndex >= 0 ? cellText(row[partOfSpeechIndex]) : '',
      meanings,
      example: exampleIndex >= 0 ? cellText(row[exampleIndex]) : '',
      exampleTranslation:
        translationIndex >= 0 ? cellText(row[translationIndex]) : '',
    })
  })

  if (!entries.length && !errors.length) {
    errors.push('没有可导入的词条')
  }
  return { entries, errors, headers }
}

export const parseVocabularyFile = async (file: File): Promise<VocabularyParseResult> => {
  const extension = file.name.split('.').pop()?.toLowerCase()
  try {
    if (extension === 'csv' || file.type.includes('csv')) {
      return rowsToEntries(parseCsvRows(await file.text()))
    }
    if (extension === 'xlsx') {
      return rowsToEntries(await readSheet(file))
    }
    return {
      entries: [],
      errors: ['仅支持 .xlsx 或 .csv 文件；旧版 .xls 请另存为 .xlsx'],
      headers: [],
    }
  } catch {
    return {
      entries: [],
      errors: ['文件解析失败，请确认文件未损坏且第一行为表头'],
      headers: [],
    }
  }
}

export const downloadVocabularyTemplate = async (): Promise<void> => {
  const header = (value: string) => ({
    value,
    fontWeight: 'bold' as const,
    backgroundColor: '#F2F2F2',
    textColor: '#171717',
  })
  await writeExcelFile([
    [
      header('单词'),
      header('音标'),
      header('词性'),
      header('词义'),
      header('例句'),
      header('例句翻译'),
    ],
    [
      'serendipity',
      '/ˌserənˈdɪpəti/',
      'n.',
      '机缘巧合；意外发现美好事物的能力',
      'Finding this café was pure serendipity.',
      '发现这家咖啡馆纯属机缘巧合。',
    ],
    [
      'resilient',
      '/rɪˈzɪliənt/',
      'adj.',
      '有韧性的；能迅速恢复的',
      'Children are often remarkably resilient.',
      '孩子往往有惊人的恢复力。',
    ],
  ]).toFile('家庭学习助手-词库导入模板.xlsx')
}
