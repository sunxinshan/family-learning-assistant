/**
 * 浏览器语音合成封装。
 *
 * 直接 new SpeechSynthesisUtterance + 只设 lang 有两个坑：
 * 1. 中文系统里默认 voice 可能是中文声库，英文单词会被用中文音素读出来；
 * 2. getVoices() 首次可能返回空数组，导致声库选择落空。
 * 这里统一做声库挑选、按语种兜底，并把「重复朗读」串行化，避免队列互相打断。
 */

export type SpeechLang = 'en' | 'zh'

const LANG_PREFIX: Record<SpeechLang, string> = { en: 'en', zh: 'zh' }
const PREFERRED_TAG: Record<SpeechLang, string> = { en: 'en-US', zh: 'zh-CN' }

let cachedVoices: SpeechSynthesisVoice[] | null = null
let generation = 0

export const isSpeechSupported = (): boolean =>
  typeof window !== 'undefined' &&
  'speechSynthesis' in window &&
  'SpeechSynthesisUtterance' in window

const normalizeTag = (value: string) => value.replace('_', '-').toLowerCase()

const scoreVoice = (voice: SpeechSynthesisVoice, lang: SpeechLang): number => {
  const tag = normalizeTag(voice.lang)
  let score = 0
  if (tag === normalizeTag(PREFERRED_TAG[lang])) score += 4
  if (voice.localService) score += 2
  if (/natural|neural|premium|enhanced|siri/i.test(voice.name)) score += 3
  if (/compact|eloquence|espeak/i.test(voice.name)) score -= 3
  return score
}

const pickVoice = (voices: SpeechSynthesisVoice[], lang: SpeechLang) => {
  const prefix = LANG_PREFIX[lang]
  const matches = voices.filter((voice) => normalizeTag(voice.lang).startsWith(prefix))
  if (!matches.length) return null
  return [...matches].sort((a, b) => scoreVoice(b, lang) - scoreVoice(a, lang))[0] ?? null
}

const loadVoices = (): Promise<SpeechSynthesisVoice[]> => {
  if (!isSpeechSupported()) return Promise.resolve([])
  if (cachedVoices?.length) return Promise.resolve(cachedVoices)
  const synth = window.speechSynthesis
  const immediate = synth.getVoices()
  if (immediate.length) {
    cachedVoices = immediate
    return Promise.resolve(immediate)
  }
  return new Promise((resolve) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      synth.removeEventListener('voiceschanged', finish)
      const voices = synth.getVoices()
      if (voices.length) cachedVoices = voices
      resolve(voices)
    }
    synth.addEventListener('voiceschanged', finish)
    window.setTimeout(finish, 800)
  })
}

export const cancelSpeech = (): void => {
  generation += 1
  if (isSpeechSupported()) window.speechSynthesis.cancel()
}

export interface SpeakOptions {
  lang?: SpeechLang
  rate?: number
  repeat?: number
  onStart?: () => void
  onFinish?: () => void
}

const speakOnce = (
  synth: SpeechSynthesis,
  text: string,
  lang: SpeechLang,
  rate: number,
  voice: SpeechSynthesisVoice | null,
) =>
  new Promise<void>((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = PREFERRED_TAG[lang]
    if (voice) {
      try {
        utterance.voice = voice
      } catch {
        // 声库对象可能失效或来自其他执行环境，降级为只按 lang 朗读。
      }
    }
    utterance.rate = rate
    utterance.pitch = 1
    let done = false
    const finish = () => {
      if (done) return
      done = true
      window.clearTimeout(timer)
      resolve()
    }
    // 某些浏览器在标签页切到后台时不会触发 onend，兜底避免 promise 永久挂起。
    const timer = window.setTimeout(finish, Math.max(4000, text.length * 400))
    utterance.onend = finish
    utterance.onerror = finish
    synth.speak(utterance)
  })

/**
 * 朗读一段文本。重复次数串行执行，期间任意一次新的调用都会打断上一次。
 * 返回 false 表示浏览器不支持或文本为空。
 */
export const speakText = async (text: string, options: SpeakOptions = {}): Promise<boolean> => {
  const content = text.trim()
  if (!content || !isSpeechSupported()) return false
  const lang = options.lang ?? 'en'
  const rate = options.rate ?? 1
  const repeat = Math.max(1, Math.floor(options.repeat ?? 1))
  const synth = window.speechSynthesis
  const runId = (generation += 1)
  synth.cancel()
  try {
    const voice = pickVoice(cachedVoices ?? (await loadVoices()), lang)
    if (runId !== generation) return true
    options.onStart?.()
    for (let index = 0; index < repeat; index += 1) {
      if (runId !== generation) return true
      await speakOnce(synth, content, lang, rate, voice)
    }
  } catch {
    options.onFinish?.()
    return false
  }
  if (runId === generation) options.onFinish?.()
  return true
}
