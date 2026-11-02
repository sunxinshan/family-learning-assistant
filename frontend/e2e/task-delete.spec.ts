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

/** 建一个两词的英语词库，再基于它建一个听写任务，结束时停留在任务详情页。 */
async function createDictationTask(page: Page, suffix: string, taskName: string) {
  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `Delete Library ${suffix}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('Lexeme\napple\nbook\n'),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)

  await page.goto('/tasks/new')
  await page.getByLabel('任务名称').fill(taskName)
  await page.locator('.advanced-settings summary').click()
  await page.getByRole('button', { name: '全选' }).click()
  await page.getByRole('button', { name: '创建并保存快照' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await expect(page.getByRole('heading', { name: taskName })).toBeVisible()
}

const cardOf = (page: Page, taskName: string) =>
  page.locator('.task-card').filter({ hasText: taskName })

async function deleteFromList(page: Page, taskName: string) {
  const card = cardOf(page, taskName)
  await expect(card).toBeVisible()
  await card.getByRole('button', { name: '删除任务' }).click()

  // 第一步：说明删除对象与影响。
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('heading', { name: '删除学习任务' })).toBeVisible()
  await expect(page.getByRole('dialog')).toContainText(taskName)
  await page.getByRole('button', { name: '继续删除' }).click()

  // 第二步：明确二次确认后才真正删除。
  await expect(page.getByRole('heading', { name: '再次确认删除' })).toBeVisible()
  await page.getByRole('button', { name: '永久删除' }).click()

  await expect(page.getByText('任务及关联练习记录已删除')).toBeVisible()
  await expect(card).toHaveCount(0)
}

test('a task in progress can be deleted straight from the list', async ({ page }) => {
  const suffix = uid()
  const taskName = `Delete Task ${suffix}`
  await register(page, `Delete${suffix}`)
  await createDictationTask(page, suffix, taskName)

  await page.getByRole('link', { name: '返回任务列表' }).click()
  await expect(cardOf(page, taskName)).toContainText('进行中')
  await deleteFromList(page, taskName)

  // 刷新后仍然不存在，说明服务端确实删掉了，不只是本地过滤。
  await page.reload()
  await expect(cardOf(page, taskName)).toHaveCount(0)
  await page.goto('/tasks')
  await expect(page.getByText('没有匹配的任务')).toBeVisible()
})

test('a completed task can also be deleted', async ({ page }) => {
  const suffix = uid()
  const taskName = `Done Task ${suffix}`
  await register(page, `Done${suffix}`)
  await createDictationTask(page, suffix, taskName)

  // 先做完两题，把任务变成已完成。
  await page.getByRole('link', { name: '开始学习' }).click()
  const answer = page.getByLabel('输入你听到的词语')
  await expect(answer).toBeVisible()
  await answer.fill('apple')
  await answer.press('Enter')
  await expect(answer).toHaveValue('', { timeout: 15000 })
  await answer.fill('book')
  await answer.press('Enter')
  // 最后一题答完直接进结果页，输入框已经不在了。
  await expect(page.getByText('100%正确率')).toBeVisible()

  // 任务状态以服务端为准：答完最后一个词后回到列表就是已完成。
  await page.goto('/tasks')
  const card = cardOf(page, taskName)
  await expect(card).toContainText('已完成')
  await deleteFromList(page, taskName)

  await page.reload()
  await expect(cardOf(page, taskName)).toHaveCount(0)
})
