import { expect, test, type Page } from '@playwright/test'

async function loginAsAdmin(page: Page) {
  await page.goto('/login')
  await page.getByLabel('昵称').fill('admin')
  await page.getByLabel('密码').fill('admin213')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.waitForURL('http://127.0.0.1:5173/')
}

test('admin 可以在管理后台查看 checkpoint 列表与内容', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Checkpoint' }).click()

  const rows = page.locator('.checkpoint-table tbody tr')
  await expect(rows.first()).toBeVisible()
  await expect(page.locator('.checkpoint-pager')).toContainText('共')

  await rows.first().getByRole('button', { name: '查看内容' }).click()

  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('.checkpoint-section-title').first()).toContainText(
    'channel_values',
  )
  await expect(dialog.locator('.checkpoint-json').first()).toContainText('{')
  await expect(dialog.getByRole('button', { name: '关闭' }).first()).toBeVisible()
})
