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

async function stubSpeech(page: Page) {
  await page.addInitScript(() => {
    const spoken: { text: string; lang: string }[] = []
    const synth = {
      speaking: false,
      pending: false,
      paused: false,
      getVoices: () => [{ name: 'Samantha', lang: 'en-US', localService: true, default: true }],
      cancel: () => undefined,
      speak: (utterance: SpeechSynthesisUtterance) => {
        spoken.push({ text: utterance.text, lang: utterance.lang })
        window.setTimeout(() => {
          utterance.onstart?.(null as never)
          window.setTimeout(() => utterance.onend?.(null as never), 5)
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
    () => (window as unknown as { __spoken: { text: string; lang: string }[] }).__spoken,
  )

async function createEnglishLibrary(page: Page, suffix: string) {
  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `Speech Library ${suffix}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('单词,音标,词性,词义\napple,/ˈæpl/,n.,苹果\nbook,/bʊk/,n.,书\n'),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)
}

async function openEnglishDictation(page: Page, suffix: string, speech: boolean) {
  await createEnglishLibrary(page, suffix)
  await page.goto('/tasks/new')
  await page.getByLabel('任务名称').fill(`Speech Task ${suffix}`)
  await page.getByRole('button', { name: '全选' }).click()
  if (!speech) {
    await page.getByLabel(/开启朗读/).uncheck()
    // 不朗读时，播放方式、朗读内容都不可配置。
    await expect(page.getByLabel('播放方式')).toBeDisabled()
    await expect(page.getByLabel('朗读内容')).toBeDisabled()
  }
  await page.getByRole('button', { name: '创建并保存快照' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await expect(page.getByText(speech ? /开启 · 每次 2 次/ : /关闭 · 答错时可听/)).toBeVisible()
  await page.getByRole('link', { name: '开始学习' }).click()
}

test('English dictation hides the IPA until the answer is wrong', async ({ page }) => {
  const suffix = uid()
  await register(page, `Ipa${suffix}`)
  await openEnglishDictation(page, suffix, true)

  const answer = page.getByLabel('输入你听到的词语')
  const hintCard = page.locator('.dictation-hint-card')
  await expect(answer).toBeVisible()
  // 输入框不再显示 "Type the word…" 占位文案。
  await expect(answer).not.toHaveAttribute('placeholder', /Type the word/)
  // 答题时不显示音标。
  await expect(hintCard.getByText('/ˈæpl/')).toHaveCount(0)

  await answer.fill('apple')
  await answer.press('Enter')
  await expect(page.getByText('拼写正确')).toBeVisible()
  // 答对时也不显示音标，只保留中文含义。
  await expect(page.getByText('/ˈæpl/')).toHaveCount(0)
  await expect(page.locator('.answer-feedback').getByText('苹果')).toBeVisible()

  const progress = page.locator('.practice-progress span').first()
  await expect(progress).toHaveText('2 / 2')
  await answer.fill('buk')
  await answer.press('Enter')
  await expect(page.getByText('拼写需要修正')).toBeVisible()
  // 答错后才揭示音标，并给出朗读入口。
  await expect(page.locator('.answer-feedback').getByText('/bʊk/')).toBeVisible()
  await expect(page.getByRole('button', { name: '朗读' })).toBeVisible()
})

test('dictation without speech has no player and only speaks on a wrong answer', async ({
  page,
}) => {
  const suffix = uid()
  await stubSpeech(page)
  await register(page, `Mute${suffix}`)
  await openEnglishDictation(page, suffix, false)

  // 关闭朗读：不出现播放器，也不自动发音。
  await expect(page.locator('.dictation-audio-area')).toHaveCount(0)
  await expect(page.getByText('进入词语后自动朗读')).toHaveCount(0)
  await expect(page.getByText('/ˈæpl/')).toHaveCount(0)
  const answer = page.getByLabel('输入这个词的拼写')
  await expect(answer).toBeVisible()
  expect(await readSpoken(page)).toHaveLength(0)

  await answer.fill('aple')
  await answer.press('Enter')
  await expect(page.getByText('拼写需要修正')).toBeVisible()
  await expect(page.locator('.answer-feedback').getByText('/ˈæpl/')).toBeVisible()
  const speakButton = page.getByRole('button', { name: '朗读' })
  await expect(speakButton).toBeVisible()

  await speakButton.click()
  await expect.poll(async () => (await readSpoken(page)).length).toBeGreaterThan(0)
})
