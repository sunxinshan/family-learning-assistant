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


async function loginAsAdmin(page: Page) {
  await page.goto('/login')
  await page.getByLabel('昵称').fill('admin')
  await page.getByLabel('密码').fill('admin213')
  await page.getByRole('button', { name: '登录', exact: true }).click()
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
  await expect(page.getByLabel('确认面板选择词条序号')).toHaveValue('1-2')
  await expect(page.getByLabel('学科筛选')).toHaveValue('english')
  await page.locator('.task-action-editor .advanced-settings summary').click()
  await expect(page.getByLabel('学习类型')).toBeDisabled()
  await page.getByLabel('任务模式').selectOption('long_term')
  await page.getByLabel('每组数量').fill('1')
  await expect(page.locator('.task-action-editor .word-picker-row.is-selected')).toHaveCount(2)
  await page.getByRole('button', { name: '取消全选' }).click()
  await expect(page.getByText('已选 0 / 2')).toBeVisible()

  // Pending action is reconstructed from the server run record after a reload.
  await page.reload()
  await expect(page.getByRole('button', { name: '确认创建' })).toBeVisible()
  await page.getByRole('button', { name: '确认创建' }).click()
  await expect(page.getByText(/任务「.*」已创建。/)).toBeVisible()
  await page.getByRole('link', { name: '打开任务' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await expect(page.getByRole('link', { name: '开始学习' })).toBeVisible()

  await page.getByRole('button', { name: '编辑' }).click()
  await page.getByLabel('任务名称').fill(`${libraryName} Edited`)
  await page.locator('.modal').getByText('高级设置', { exact: true }).click()
  await page.getByLabel('任务模式').selectOption('long_term')
  await page.getByLabel('每组数量').fill('1')
  await page.getByLabel('朗读内容').selectOption('meaning')
  await page.getByRole('button', { name: '保存修改' }).click()
  await expect(page.getByRole('heading', { name: `${libraryName} Edited` })).toBeVisible()
  await expect(page.getByText('长期任务', { exact: true }).first()).toBeVisible()

  await page.goto('/tasks')
  const taskCard = page.locator('.task-card').filter({ hasText: `${libraryName} Edited` }).first()
  await expect(taskCard).toBeVisible()
  await taskCard.getByRole('link', { name: '开始学习' }).click()
  await expect(page.getByText('线下听写', { exact: true })).toBeVisible()
  await expect(page.getByText('第 1 / 2 组', { exact: true })).toBeVisible()
  await expect(page.getByText('第 1 / 1 个', { exact: true })).toBeVisible()
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
  await loginAsAdmin(page)
  await page.goto('/admin')
  await expect(page.getByText('管理员权限')).toBeVisible()
  await expect(page.locator('tbody tr').filter({ hasText: 'admin' }).first()).toBeVisible()
  await expect(page.locator('tbody tr').filter({ hasText: 'admin1' }).first()).toBeVisible()
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

  // A delayed or stale list refresh must not hide a task that was just created.
  let returnEmptyTaskList = true
  await page.route(/\/api\/v1\/tasks$/, async (route) => {
    if (returnEmptyTaskList && route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      return
    }
    await route.continue()
  })
  await page.goto('/tasks/new')
  await page.getByLabel('任务名称').fill(taskName)
  await expect(page.getByLabel('任务模式')).toBeHidden()
  await page.locator('.advanced-settings summary').click()
  await expect(page.getByLabel('任务模式')).toHaveValue('fixed')
  await expect(page.getByLabel('学科筛选')).toHaveValue('english')
  await expect(page.getByText('已选 0 / 2')).toBeVisible()
  await page.getByRole('button', { name: '全选' }).click()
  await page.getByRole('button', { name: '创建并保存快照' }).click()
  await page.waitForURL(/\/tasks\/[0-9a-f-]{36}$/)
  await expect(page.getByRole('heading', { name: taskName })).toBeVisible()
  await expect(page.getByText('任务不存在', { exact: true })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: taskName })).toBeVisible()
  await expect(page.getByText('任务不存在', { exact: true })).toHaveCount(0)
  returnEmptyTaskList = false
  await page.getByRole('link', { name: '开始学习' }).click()
  await page.getByRole('button', { name: '提交拼写' }).waitFor({ state: 'detached' }).catch(() => undefined)
  const answer = page.getByLabel('输入你听到的词语')
  await expect(answer).toBeVisible()
  // 英语听写答题时不提示音标，答错后才揭示（见 dictation-speech-modes.spec.ts）。
  await expect(page.getByText('英语音标', { exact: true })).toHaveCount(0)
  await expect(page.getByText('中文含义', { exact: true })).toBeVisible()
  await expect(page.getByText('第 1 / 1 组', { exact: true })).toBeVisible()
  await expect(page.getByText('第 1 / 2 个', { exact: true })).toBeVisible()
  await answer.fill('appl')
  await answer.press('Enter')
  await expect(page.getByText('拼写需要修正')).toBeVisible()
  await page.getByRole('button', { name: '下一题' }).click()
  await answer.fill('book')
  await answer.press('Enter')
  await expect(page.getByText('拼写正确')).toBeVisible()
  // 线上听写答对后自动继续，最后一题自动进入结果页。
  await expect(page.getByText('50%正确率')).toBeVisible()

  await page.getByRole('link', { name: '返回任务详情' }).click()
  await expect(page.getByRole('link', { name: /练习错题 1/ })).toBeVisible()
  await page.getByRole('link', { name: /练习错题 1/ }).click()
  await expect(page.getByText(/错题练习.*线上听写/)).toBeVisible()
  await answer.fill('apple')
  await answer.press('Enter')
  await expect(page.getByText('拼写正确')).toBeVisible()
  await expect(page.getByText('本次错题练习结果已保存')).toBeVisible()
  await page.getByRole('link', { name: '返回任务详情' }).click()
  await expect(page.getByText('已连续答对 1 次，再答对 1 次移出')).toBeVisible()

  await page.getByRole('link', { name: /练习错题 1/ }).click()
  await answer.fill('apple')
  await answer.press('Enter')
  await expect(page.getByRole('link', { name: '返回任务详情' })).toBeVisible()
  await page.getByRole('link', { name: '返回任务详情' }).click()
  await expect(page.getByText('目前没有待复习的错题。')).toBeVisible()
})

test('deleting one entry only removes that entry and cancelling import is clean', async ({
  page,
}) => {
  const suffix = uid()
  const nickname = `Safety${suffix}`
  const libraryName = `Safety Library ${suffix}`
  await register(page, nickname)

  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `${libraryName}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from(
      '单词,音标,词性,词义\napple,/ˈæpl/,n.,苹果\nbook,/bʊk/,n.,书\n',
    ),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)

  await page.getByRole('button', { name: '选择词条' }).first().click()
  await expect(page.getByText('已选 1 项')).toBeVisible()
  await page.getByRole('button', { name: '批量删除' }).click()
  await page.getByRole('button', { name: '确认删除 1 项' }).click()
  await expect(page.locator('.vocabulary-table tbody tr')).toHaveCount(1)
  await expect(page.getByText('book', { exact: true })).toBeVisible()

  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: `cancel-${suffix}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('Word\napple\n'),
  })
  await expect(page.getByRole('button', { name: '确认导入' })).toBeVisible()
  await page.getByRole('button', { name: '取消' }).last().click()
  await expect(page.getByText('已取消本次操作，没有写入任何业务数据。')).toBeVisible()
  await expect(page.getByText('操作提示')).toHaveCount(0)
})

test('admin can publish an admin-created personal vocabulary', async ({ page }) => {
  const suffix = uid()
  const libraryName = `Admin Public ${suffix}`
  await loginAsAdmin(page)
  await page.goto('/vocabulary/new')
  await page.locator('input[type=file]').setInputFiles({
    name: `${libraryName}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('单词,音标,词性,词义\npublish,/ˈpʌblɪʃ/,v.,发布\n'),
  })
  await expect(page.getByText('服务端已解析 1 个词条')).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)
  await page.getByRole('button', { name: '设为公共词库' }).click()
  await expect(page.getByText('词库已设为公共词库')).toBeVisible()
  await expect(page.getByText('公共词库', { exact: true }).first()).toBeVisible()
  await page.goto('/vocabulary')
  await page.getByRole('tab', { name: /公共词库/ }).click()
  await expect(page.getByText(libraryName, { exact: true }).first()).toBeVisible()
})


test('chinese library creation keeps chinese subject and enriches pinyin', async ({ page }) => {
  const suffix = uid()
  const libraryName = `Chinese Library ${suffix}`
  await register(page, `Chinese${suffix}`)
  await page.goto('/vocabulary/new')
  await page.getByLabel('学科').selectOption('chinese')
  await page.locator('input[type=file]').setInputFiles({
    name: `${libraryName}.csv`,
    mimeType: 'text/csv',
    buffer: Buffer.from('词语\n苹果\n学习\n'),
  })
  await expect(page.getByText('服务端已解析 2 个词条')).toBeVisible()
  await expect(page.getByLabel('学科')).toHaveValue('chinese')
  await expect(page.getByText('píng guǒ', { exact: true })).toBeVisible()
  await expect(page.getByText('xué xí', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '创建词库' }).click()
  await page.waitForURL(/\/vocabulary\/[0-9a-f-]{36}$/)
  await expect(page.getByText('语文', { exact: true }).first()).toBeVisible()
})
