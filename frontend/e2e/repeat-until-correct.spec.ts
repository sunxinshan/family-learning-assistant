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

async function openRepeatTask(page: Page, suffix: string) {
  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `Repeat Library ${suffix}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('单词,音标,词性,词义\napple,/ˈæpl/,n.,苹果\nbook,/bʊk/,n.,书\n'),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)

  await page.goto('/tasks/new')
  await page.getByLabel('任务名称').fill(`Repeat Task ${suffix}`)
  await page.locator('.advanced-settings summary').click()
  await page.getByRole('button', { name: '全选' }).click()
  await page.getByRole('checkbox', { name: /强制重做/ }).check()
  await page.getByRole('button', { name: '创建并保存快照' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await page.getByRole('link', { name: '开始学习' }).click()
  await expect(page.getByLabel('输入你听到的词语')).toBeVisible()
}

const roundLabel = (page: Page) => page.locator('.practice-group-strip strong').nth(2)

test('a wrong word is replayed after the whole group has been answered once', async ({ page }) => {
  const suffix = uid()
  await stubSpeech(page)
  await register(page, `Repeat${suffix}`)
  await openRepeatTask(page, suffix)

  const input = page.getByLabel('输入你听到的词语')
  // 第一轮第一个词：苹果。
  await expect(page.getByText('苹果', { exact: true })).toBeVisible()
  await expect(roundLabel(page)).toHaveText('第 1 轮')

  // 答对后自动进入下一个词，不在同一个词上反复。
  await input.fill('apple')
  await input.press('Enter')
  await expect(page.getByText('拼写正确')).toBeVisible()
  await expect(page.getByText('书', { exact: true })).toBeVisible({ timeout: 5000 })

  // 第二个词答错：照样可以进入下一题，本轮结束后再重练。
  await input.fill('buk')
  await input.press('Enter')
  await expect(page.getByText('拼写需要修正')).toBeVisible()
  await expect(
    page.getByText('这个词会留在本组，这一轮走完后重练，连对两次才过关'),
  ).toBeVisible()
  await expect(page.getByText('第 1 轮结束，本组还有 1 个错词要重练')).toBeVisible()

  await page.getByRole('button', { name: '下一题' }).click()
  // 第二轮只练这一组里答错的词。
  await expect(roundLabel(page)).toHaveText('第 2 轮')
  await expect(page.getByText('书', { exact: true })).toBeVisible()
  await expect(page.locator('.practice-progress span').first()).toHaveText('1 / 1')

  // 第二轮拼对一次还不算过关，还要再来一轮。
  await input.fill('book')
  await input.press('Enter')
  await expect(page.getByText('这个词这轮拼对了，下一轮再对一次才过关')).toBeVisible()
  await expect(roundLabel(page)).toHaveText('第 3 轮', { timeout: 5000 })

  // 连续第二轮拼对：本组过关，整组练完给出结果。
  await input.fill('book')
  await input.press('Enter')
  await expect(page.getByText('拼写正确')).toBeVisible()
  await expect(page.getByText('听写结果已保存')).toBeVisible({ timeout: 6000 })
  await expect(page.locator('.result-metrics strong').first()).toHaveText('2/2')
})

test('a group without mistakes passes after a single round', async ({ page }) => {
  const suffix = uid()
  await stubSpeech(page)
  await register(page, `Perfect${suffix}`)
  await openRepeatTask(page, suffix)

  const input = page.getByLabel('输入你听到的词语')
  await input.fill('apple')
  await input.press('Enter')
  await expect(page.getByText('书', { exact: true })).toBeVisible({ timeout: 5000 })
  await input.fill('book')
  await input.press('Enter')

  // 没错过的词不用重练，一轮结束就出结果。
  await expect(page.getByText('听写结果已保存')).toBeVisible({ timeout: 6000 })
  await expect(page.locator('.result-metrics strong').first()).toHaveText('2/2')
})
