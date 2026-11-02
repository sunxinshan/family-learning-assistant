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

test('real HTTP flow: server import, agent confirmation, active restore, offline practice and learning', async ({
  page,
}) => {
  const suffix = uid()
  const nickname = `E2E${suffix}`
  const libraryName = `E2E Library ${suffix}`
  await register(page, nickname)

  await page.evaluate(() => {
    const raw = localStorage.getItem('fla.http.session.v1')
    if (!raw) throw new Error('missing session')
    const session = JSON.parse(raw) as { accessToken: string }
    session.accessToken = 'invalid-access-token'
    localStorage.setItem('fla.http.session.v1', JSON.stringify(session))
  })
  await page.reload()
  await expect(page.getByRole('heading', { name: '学习助手' })).toBeVisible()

  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `${libraryName}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from(
      '单词,音标,词性,词义,例句,例句翻译\n' +
        'apple,/ˈæpl/,n.,苹果,An apple.,一个苹果。\n' +
        'book,/bʊk/,n.,书,A book.,一本书。\n',
    ),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)
  await expect(page.getByText(libraryName, { exact: true }).first()).toBeVisible()

  await page.goto('/')
  const composer = page.getByRole('textbox').last()
  await composer.fill(
    `创建固定任务，选择「${libraryName}」的所有单词，线下听写，自动播放，间隔8秒，朗读3次，中文`,
  )
  await composer.press('Enter')
  await expect(
    page.getByText('已整理任务配置，请检查后确认。确认前不会写入任何任务数据。'),
  ).toBeVisible()
  await expect(page.getByText('已选 2 / 2')).toBeVisible()
  await page.getByRole('button', { name: '取消全选' }).click()
  await expect(page.getByText('已选 0 / 2')).toBeVisible()

  // Pending action is reconstructed from the server run record after a reload.
  await page.reload()
  await expect(page.getByRole('button', { name: '确认创建' })).toBeVisible()
  await page.getByRole('button', { name: '确认创建' }).click()
  await expect(page.getByText(/任务「.*」已创建。/)).toBeVisible()

  await page.goto('/tasks')
  const taskCard = page.locator('.task-card').filter({ hasText: libraryName }).first()
  await expect(taskCard).toBeVisible()
  await taskCard.getByRole('link', { name: /继续学习/ }).click()
  await expect(page.getByText('线下听写', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '下一个词' }).click()
  await page.getByRole('button', { name: '进入核对' }).click()
  await page.getByRole('checkbox').first().check()
  await page.getByRole('button', { name: '提交自查结果' }).click()
  await expect(page.getByText('线下听写自查已提交')).toBeVisible()
  await expect(page.getByText('50%正确率')).toBeVisible()

  await page.goto('/learning')
  await expect(page.getByText('练习次数', { exact: true })).toBeVisible()
  await expect(page.getByText('平均正确率', { exact: true })).toBeVisible()
  await expect(page.getByText('待复习错题', { exact: true }).first()).toBeVisible()

  await page.goto('/admin')
  await expect(page).toHaveURL('http://127.0.0.1:5173/')
})

test('admin sees two admin accounts and read-only learning stats', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: /管理员 · Admin/ }).click()
  await page.waitForURL('http://127.0.0.1:5173/')
  await page.goto('/admin')
  await expect(page.getByText('管理员权限')).toBeVisible()
  await expect(page.locator('tbody tr').filter({ hasText: 'Admin' }).first()).toBeVisible()
  await expect(page.locator('tbody tr').filter({ hasText: 'Manager' }).first()).toBeVisible()
  await page.getByRole('button', { name: '学习概况' }).first().click()
  await expect(page.getByText('管理员只读视图')).toBeVisible()
  await expect(page.getByText('管理员不能修改任务、答题结果或掌握状态')).toBeVisible()
})


test('online dictation submits answers through the real practice API', async ({ page }) => {
  const suffix = uid()
  const nickname = `Online${suffix}`
  const libraryName = `Online Library ${suffix}`
  const taskName = `Online Task ${suffix}`
  await register(page, nickname)

  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `${libraryName}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('Lexeme\napple\nbook\n'),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await expect(page.getByText(/列名映射：模型识别/)).toBeVisible()
  await expect(page.getByText(/自动补充 2\/2 项/)).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)

  await page.goto('/tasks/new')
  await page.getByLabel('任务名称').fill(taskName)
  await page.getByLabel('任务模式').selectOption('fixed')
  await page.getByRole('button', { name: '创建并保存快照' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await page.getByRole('link', { name: /继续学习/ }).click()
  await page.getByRole('button', { name: '提交拼写' }).waitFor({ state: 'detached' }).catch(() => undefined)
  const answer = page.getByLabel('输入你听到的词语')
  await expect(answer).toBeVisible()
  await answer.fill('apple')
  await answer.press('Enter')
  await expect(page.getByText('拼写正确')).toBeVisible()
  await page.getByRole('button', { name: '下一题' }).click()
  await answer.fill('book')
  await answer.press('Enter')
  await expect(page.getByText('拼写正确')).toBeVisible()
  await page.getByRole('button', { name: '查看听写结果' }).click()
  await expect(page.getByText('100%正确率')).toBeVisible()
})
