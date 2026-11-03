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

/** 静音朗读，避免 headless 环境没有语音包时抛错。 */
async function stubSpeech(page: Page) {
  await page.addInitScript(() => {
    const synth = {
      speaking: false,
      pending: false,
      paused: false,
      getVoices: () => [{ name: 'Samantha', lang: 'en-US', localService: true, default: true }],
      cancel: () => undefined,
      speak: (utterance: SpeechSynthesisUtterance) => {
        window.setTimeout(() => {
          utterance.onstart?.(null as never)
          window.setTimeout(() => utterance.onend?.(null as never), 5)
        }, 0)
      },
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: synth })
  })
}

async function openStreakTask(page: Page, suffix: string) {
  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `Streak Library ${suffix}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('单词,音标,词性,词义\napple,/ˈæpl/,n.,苹果\nbook,/bʊk/,n.,书\n'),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)

  await page.goto('/tasks/new')
  await page.getByLabel('任务名称').fill(`Streak Task ${suffix}`)
  await page.locator('.advanced-settings summary').click()
  await page.getByRole('button', { name: '全选' }).click()
  await page.getByRole('checkbox', { name: /强制重做/ }).check()
  await page.getByRole('button', { name: '创建并保存快照' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await page.getByRole('link', { name: '开始学习' }).click()
  await expect(page.getByLabel('输入你听到的词语')).toBeVisible()
}

test('a wrong word stays in the group until it is spelled twice in a row', async ({ page }) => {
  const suffix = uid()
  await stubSpeech(page)
  await register(page, `Streak${suffix}`)
  await openStreakTask(page, suffix)

  const input = page.getByLabel('输入你听到的词语')
  const progress = page.locator('.practice-progress span').first()
  await expect(progress).toHaveText('1 / 2')

  // 1. 拼错：停在本词，出现在本组继续练的提示。
  await input.fill('aple')
  await input.press('Enter')
  await expect(page.getByText('拼写需要修正')).toBeVisible()
  await expect(page.getByText('本词连续拼对 0/2 次，再拼对 2 次才能进入下一个词')).toBeVisible()
  await expect(progress).toHaveText('1 / 2')

  // 2. 第一次拼对：还不放行。
  await page.getByRole('button', { name: '再拼一次' }).click()
  await expect(input).toBeEnabled()
  await input.fill('apple')
  await input.press('Enter')
  await expect(page.getByText('拼写正确 · 还要再拼一次')).toBeVisible()
  await expect(progress).toHaveText('1 / 2')

  // 3. 连续第二次拼对：才进入下一个词。
  await page.getByRole('button', { name: '再拼一次' }).click()
  await expect(input).toBeEnabled()
  await input.fill('apple')
  await input.press('Enter')
  await expect(progress).toHaveText('2 / 2')

  // 4. 第二个词同样要连对两次。
  await expect(input).toBeEnabled()
  await input.fill('book')
  await input.press('Enter')
  await expect(page.getByText('拼写正确 · 还要再拼一次')).toBeVisible()
  await page.getByRole('button', { name: '再拼一次' }).click()
  await expect(input).toBeEnabled()
  await input.fill('book')
  await input.press('Enter')

  await expect(page.getByText('听写结果已保存')).toBeVisible()
  await expect(page.locator('.result-metrics strong').first()).toHaveText('2/2')
})
