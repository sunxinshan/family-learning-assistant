import { expect, test, type Page } from '@playwright/test'

const uid = () => `${Date.now()}${Math.floor(Math.random() * 1000)}`

async function register(page: Page, nickname: string) {
  await page.goto('/login')
  await page.getByRole('button', { name: '没有账户？创建账户' }).click()
  await page.getByLabel('昵称').fill(nickname)
  await page.getByLabel('密码').fill('e2e-password-123')
  await page.getByRole('button', { name: '创建并登录' }).click()
  await page.waitForURL('http://127.0.0.1:5173/')
}

/**
 * 用假的 speechSynthesis 记录下了哪些朗读请求。
 * 同时提供中英两个声库，用来验证英文不会被中文声库接管。
 */
async function stubSpeech(page: Page) {
  await page.addInitScript(() => {
    const voices = [
      { name: 'Ting-Ting', lang: 'zh-CN', localService: true, default: true },
      { name: 'Samantha', lang: 'en-US', localService: true, default: false },
    ]
    // 无声卡环境下 getVoices() 返回空，真实 SpeechSynthesisVoice 无法构造；
    // 让 utterance.voice 接受形似的普通对象，才能断言最终选中了哪个声库。
    Object.defineProperty(SpeechSynthesisUtterance.prototype, 'voice', {
      configurable: true,
      get(this: { __voice?: SpeechSynthesisVoice }) {
        return this.__voice ?? null
      },
      set(this: { __voice?: SpeechSynthesisVoice }, value: SpeechSynthesisVoice) {
        this.__voice = value
      },
    })
    const spoken: { text: string; lang: string; voice: string | null }[] = []
    const synth = {
      speaking: false,
      pending: false,
      paused: false,
      getVoices: () => voices,
      cancel: () => undefined,
      speak: (utterance: SpeechSynthesisUtterance) => {
        spoken.push({
          text: utterance.text,
          lang: utterance.lang,
          voice: utterance.voice ? utterance.voice.name : null,
        })
        window.setTimeout(() => {
          utterance.onstart?.(null as never)
          window.setTimeout(() => utterance.onend?.(null as never), 10)
        }, 0)
      },
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: synth })
    Object.defineProperty(window, '__spoken', { configurable: true, value: spoken })
  })
}

const readSpoken = (page: Page) =>
  page.evaluate(
    () =>
      (window as unknown as { __spoken: { text: string; lang: string; voice: string | null }[] })
        .__spoken,
  )

async function openEnglishDictation(
  page: Page,
  suffix: string,
  options: { playbackMode?: 'auto' | 'manual'; intervalSeconds?: number } = {},
) {
  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `Dictation Library ${suffix}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('单词,音标,词性,词义\napple,/ˈæpl/,n.,苹果\nbook,/bʊk/,n.,书\n'),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)

  await page.goto('/tasks/new')
  await page.getByLabel('任务名称').fill(`Dictation Task ${suffix}`)
  await page.locator('.advanced-settings summary').click()
  await page.getByRole('button', { name: '全选' }).click()
  await expect(page.getByLabel('朗读内容')).toHaveValue('phonetic')
  await expect(page.getByLabel('朗读内容').locator('option:checked')).toHaveText('英语单词')
  if (options.playbackMode === 'auto') {
    await page.getByLabel('播放方式').selectOption('auto')
    await expect(page.getByLabel('自动播放间隔')).toHaveValue('8')
    await page.getByLabel('自动播放间隔').fill(String(options.intervalSeconds ?? 8))
  }
  await page.getByRole('button', { name: '创建并保存快照' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await page.getByRole('link', { name: '开始学习' }).click()
  await expect(page.getByLabel('输入你听到的词语')).toBeVisible()
}



async function openChineseDictation(page: Page, suffix: string) {
  const libraryName = `Chinese Dictation ${suffix}`
  await page.goto('/vocabulary/new')
  await page.getByLabel('学科').selectOption('chinese')
  await page.locator('input[type=file]').setInputFiles({
    name: `${libraryName}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('词语\n苹果\n'),
  })
  await expect(page.getByText('服务端已解析 1 个词条')).toBeVisible()
  await expect(page.getByText('píng guǒ', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)
  await page.goto('/tasks/new')
  await page.getByLabel('学科筛选').selectOption('chinese')
  const source = page.getByLabel('内容来源')
  const option = source.locator('option').filter({ hasText: libraryName }).first()
  const libraryId = await option.getAttribute('value')
  expect(libraryId).toBeTruthy()
  await source.selectOption(libraryId!)
  await expect(page.getByLabel('学科筛选')).toHaveValue('chinese')
  await page.getByLabel('任务名称').fill(`Chinese Dictation Task ${suffix}`)
  await page.getByRole('button', { name: '全选' }).click()
  await page.locator('.advanced-settings summary').click()
  await expect(page.getByLabel('朗读内容')).toBeDisabled()
  await expect(page.getByLabel('朗读内容')).toContainText('词语发音（直接读出）')
  await page.getByRole('button', { name: '创建并保存快照' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await page.getByRole('link', { name: '开始学习' }).click()
  await expect(page.getByLabel('输入你听到的词语')).toBeVisible()
}

test('English dictation reads the word itself on entering, not the IPA string', async ({
  page,
}) => {
  const suffix = uid()
  await stubSpeech(page)
  await register(page, `Audio${suffix}`)
  await openEnglishDictation(page, suffix)

  // 手动模式也不再需要先点播放：进入词语就开始朗读（默认朗读 2 次）。
  await page.waitForFunction(
    () =>
      (window as unknown as { __spoken: unknown[] }).__spoken.length >= 2,
  )

  const spoken = await readSpoken(page)
  expect(spoken.length).toBeGreaterThanOrEqual(2)
  for (const item of spoken) {
    expect(item.text).toBe('apple')
    expect(item.lang).toBe('en-US')
    expect(item.voice).toBe('Samantha')
  }
  expect(spoken.map((item) => item.text)).not.toContain('/ˈæpl/')

  // 重播按钮（移动端为圆形播放键）仍然可以手动再念一遍。
  await page.locator('.audio-play-button').click()
  await expect
    .poll(async () => (await readSpoken(page)).length)
    .toBeGreaterThan(spoken.length)
})

test('auto playback moves to the next word on the interval and can be paused', async ({
  page,
}) => {
  const suffix = uid()
  await stubSpeech(page)
  await register(page, `Auto${suffix}`)
  await openEnglishDictation(page, suffix, { playbackMode: 'auto', intervalSeconds: 2 })

  const progress = page.locator('.practice-progress span').first()
  await expect(progress).toHaveText('1 / 2')

  // 暂停后不再自动流转，也不会重播当前词。
  await page.getByRole('button', { name: '暂停自动播放' }).click()
  await expect(page.getByText('自动播放已暂停', { exact: true })).toBeVisible()
  await page.waitForTimeout(2500)
  await expect(progress).toHaveText('1 / 2')

  await page.getByRole('button', { name: '继续自动播放' }).click()
  // 间隔到点进入下一个词，并且自动朗读下一个词，而不是重播 apple。
  await expect(progress).toHaveText('2 / 2')
  await expect
    .poll(async () => (await readSpoken(page)).map((item) => item.text))
    .toContain('book')
})

test('a correct online answer advances without clicking 下一题', async ({ page }) => {
  const suffix = uid()
  await register(page, `Advance${suffix}`)
  await openEnglishDictation(page, suffix)

  const progress = page.locator('.practice-progress span').first()
  const answer = page.getByLabel('输入你听到的词语')
  await expect(progress).toHaveText('1 / 2')

  await answer.fill('apple')
  await answer.press('Enter')
  await expect(page.getByText('拼写正确')).toBeVisible()
  await expect(progress).toHaveText('2 / 2')
  await expect(answer).toHaveValue('')

  // 自动继续后输入框仍然可用，直接答下一题即可。
  await answer.fill('book')
  await answer.press('Enter')
  await expect(page.getByText('拼写正确')).toBeVisible()
  await expect(page.getByText('100%正确率')).toBeVisible()
})


test('Chinese dictation speaks the hanzi word directly instead of reading pinyin', async ({
  page,
}) => {
  const suffix = uid()
  await stubSpeech(page)
  await register(page, `ChineseAudio${suffix}`)
  await openChineseDictation(page, suffix)
  await page.waitForFunction(
    () =>
      (window as unknown as { __spoken: unknown[] }).__spoken.length >= 2,
  )
  const spoken = await readSpoken(page)
  expect(spoken.length).toBeGreaterThanOrEqual(2)
  for (const item of spoken) {
    expect(item.text).toBe('苹果')
    expect(item.lang.startsWith('zh')).toBe(true)
    expect(item.voice).toBe('Ting-Ting')
  }
  expect(spoken.map((item) => item.text)).not.toContain('píng guǒ')
  await expect(page.getByText('píng guǒ', { exact: true })).toBeVisible()
  // 语文听写页只给拼音，不显示词语本身（词库里的「中文含义」也是词语，勾出来等于给答案）。
  const card = page.locator('.dictation-practice-card')
  await expect(card.getByText('苹果', { exact: true })).toHaveCount(0)
  await expect(card.getByText('中文含义')).toHaveCount(0)
  await expect(card.getByText('语文拼音')).toBeVisible()
})
