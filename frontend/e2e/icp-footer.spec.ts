import { expect, test } from '@playwright/test'

const ICP_TEXT = '苏ICP备2026067314号-1'
const ICP_HREF = 'https://beian.miit.gov.cn/'
const uid = () => `${Date.now()}${Math.floor(Math.random() * 1000)}`

test('登录页底部展示备案号并链接到工信部备案系统', async ({ page }) => {
  await page.goto('/login')
  const footer = page.locator('.site-footer')
  await expect(footer).toBeVisible()

  const link = footer.getByRole('link', { name: ICP_TEXT })
  await expect(link).toHaveAttribute('href', ICP_HREF)
  await expect(link).toHaveAttribute('target', '_blank')
  await expect(link).toHaveAttribute('rel', /noopener/)

  // 页脚必须落在首屏内，不能被挤出可视区
  const box = await footer.boundingBox()
  const viewport = page.viewportSize()!
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1)

  await page.screenshot({ path: `/tmp/icp-login-${test.info().project.name}.png` })
})

test('登录后的首页底部也展示备案号，且不产生额外滚动', async ({ page }) => {
  const suffix = uid()
  await page.goto('/login')
  await page.getByRole('button', { name: '没有账户？创建账户' }).click()
  await page.getByLabel('昵称').fill(`Icp${suffix}`)
  await page.getByLabel('密码').fill('e2e-password-123')
  await page.getByRole('button', { name: '创建并登录' }).click()
  await page.waitForURL('http://127.0.0.1:5173/')

  const footer = page.locator('.site-footer')
  const link = footer.getByRole('link', { name: ICP_TEXT })
  await expect(link).toBeVisible()
  await expect(link).toHaveAttribute('href', ICP_HREF)

  const box = await footer.boundingBox()
  const viewport = page.viewportSize()!
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1)

  // 聊天页原本正好一屏，加页脚后不应撑出滚动条
  const overflow = await page.evaluate(
    () => document.documentElement.scrollHeight - window.innerHeight,
  )
  expect(overflow).toBeLessThanOrEqual(1)

  await page.screenshot({ path: `/tmp/icp-home-${test.info().project.name}.png` })
})
