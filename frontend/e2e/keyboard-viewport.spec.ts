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

/** 建一个 2 词的英语词库 + 听写任务，并进入练习页。 */
async function openEnglishDictation(page: Page, suffix: string) {
  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `Keyboard Library ${suffix}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('单词,音标,词性,词义\napple,/ˈæpl/,n.,苹果\nbook,/bʊk/,n.,书\n'),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)

  await page.goto('/tasks/new')
  await page.getByLabel('任务名称').fill(`Keyboard Task ${suffix}`)
  await page.locator('.advanced-settings summary').click()
  await page.getByRole('button', { name: '全选' }).click()
  await page.getByRole('button', { name: '创建并保存快照' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await page.getByRole('link', { name: '开始学习' }).click()
  await expect(page.getByLabel('输入你听到的词语')).toBeVisible()
  const taskId = page.url().match(/\/practice\/dictation\/([0-9a-f-]{36})/)?.[1]
  expect(taskId).toBeTruthy()
  return taskId!
}

/**
 * 用「把视口压矮」模拟手机软键盘占住屏幕下方：visualViewport 变小，
 * 页面应当切到 is-keyboard 紧凑布局，并把按钮留在视口内。
 */
async function shrinkToKeyboard(page: Page) {
  await page.setViewportSize({ width: 390, height: 360 })
  await expect(page.locator('.practice-shell')).toHaveClass(/is-keyboard/)
}

async function expectActionsAboveFold(page: Page) {
  const viewport = page.viewportSize()!
  const submit = page.getByRole('button', { name: /提交拼写|下一题/ })
  await expect(submit).toBeVisible()
  const box = await submit.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1)

  // 答题要用的信息（输入框、中文含义）也必须在键盘上方
  const input = page.getByLabel('输入你听到的词语')
  const inputBox = await input.boundingBox()
  expect(inputBox).not.toBeNull()
  expect(inputBox!.y + inputBox!.height).toBeLessThanOrEqual(box!.y + 1)
  await expect(page.locator('.dictation-hint-values strong').first()).toBeVisible()

  // 文字说明被压缩掉，把空间让给答题区
  await expect(page.locator('.practice-question-meta > span:not(.badge)')).toBeHidden()
  await expect(page.locator('.practice-secondary-note')).toBeHidden()
}

test.describe('手机键盘弹起时的练习页布局', () => {
  test.skip(({ isMobile }) => !isMobile, '只在移动端项目验证软键盘布局')

  test('线上听写：输入法弹起后输入框和提交按钮都在键盘上方', async ({ page }) => {
    const suffix = uid()
    await register(page, `Keyboard${suffix}`)
    await openEnglishDictation(page, suffix)

    await shrinkToKeyboard(page)
    await expectActionsAboveFold(page)

    // 键盘收起后恢复原来的整页布局
    await page.setViewportSize({ width: 390, height: 664 })
    await expect(page.locator('.practice-shell')).not.toHaveClass(/is-keyboard/)
    await expect(page.locator('.practice-question-meta > span:not(.badge)')).toBeVisible()
  })

  test('答错提示出现后页面不出现下拉条', async ({ page }) => {
    const suffix = uid()
    await register(page, `KeyboardFeedback${suffix}`)
    await openEnglishDictation(page, suffix)

    await shrinkToKeyboard(page)
    const answer = page.getByLabel('输入你听到的词语')
    await answer.fill('aple')
    await answer.press('Enter')
    await expect(page.getByText('拼写需要修正')).toBeVisible()

    // 反馈比答题时更高，超出一屏就会滚出一条下拉条
    const overflow = await page.evaluate(() => {
      const main = document.querySelector('.practice-main') as HTMLElement
      return main.scrollHeight - main.clientHeight
    })
    expect(overflow).toBeLessThanOrEqual(1)

    await expect(page.getByText('apple', { exact: true })).toBeVisible()
    const next = page.getByRole('button', { name: '下一题' })
    const box = await next.boundingBox()
    expect(box!.y + box!.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1)
  })

  test('手机竖屏：答错提示出现后整页不出现下拉条', async ({ page }) => {
    const suffix = uid()
    await register(page, `NoScroll${suffix}`)
    await openEnglishDictation(page, suffix)

    const overflow = () =>
      page.evaluate(() => {
        const main = document.querySelector('.practice-main') as HTMLElement
        return {
          doc: document.documentElement.scrollHeight - window.innerHeight,
          main: main.scrollHeight - main.clientHeight,
        }
      })

    expect((await overflow()).doc).toBeLessThanOrEqual(1)

    const answer = page.getByLabel('输入你听到的词语')
    await answer.fill('aple')
    await answer.press('Enter')
    await expect(page.getByText('拼写需要修正')).toBeVisible()

    // 反馈比答题时更高，以前会把整页撑出 400px 的滚动条。
    const after = await overflow()
    expect(after.doc).toBeLessThanOrEqual(1)
    expect(after.main).toBeLessThanOrEqual(1)
    await expect(page.getByRole('button', { name: '下一题' })).toBeInViewport()
  })

  test('错题复习页：同样的键盘避让', async ({ page }) => {
    const suffix = uid()
    await register(page, `KeyboardWrong${suffix}`)
    const taskId = await openEnglishDictation(page, suffix)

    // 先拼错一个词，制造一条错题
    const answer = page.getByLabel('输入你听到的词语')
    await answer.fill('aple')
    await answer.press('Enter')
    await expect(page.getByText('拼写需要修正')).toBeVisible()
    await page.goto(`/practice/dictation/${taskId}/wrong`)
    await expect(page.getByLabel('输入你听到的词语')).toBeVisible()

    await shrinkToKeyboard(page)
    await expectActionsAboveFold(page)
  })
})
