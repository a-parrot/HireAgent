import { test, expect } from '@playwright/test'
import { adminIdentity } from './fixtures'

test('login guard, read-only controls, forbidden route and logout work without stored credentials', async ({ page }) => {
  let signedIn = false
  const viewer = { ...adminIdentity, role: 'viewer', role_name: '只读用户', permissions: adminIdentity.permissions.filter(p => p.endsWith('.read')) }
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/me') return route.fulfill({ status: signedIn ? 200 : 401, json: signedIn ? viewer : { detail: '请先登录' } })
    if (path === '/api/auth/login') { signedIn = true; return route.fulfill({ json: viewer }) }
    if (path === '/api/auth/logout') { signedIn = false; return route.fulfill({ json: { detail: '已退出登录' } }) }
    if (path === '/api/jobs') return route.fulfill({ json: { items: [], total: 0 } })
    throw new Error(`Unexpected call: ${path}`)
  })
  await page.goto('/jobs')
  await expect(page).toHaveURL(/\/login\?next=/)
  await page.getByRole('textbox', { name: '用户名', exact: true }).fill('viewer')
  await page.getByLabel('密码', { exact: true }).fill('Test-password-123!')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/jobs$/)
  await expect(page.getByRole('button', { name: '新建岗位', exact: true })).not.toBeVisible()
  await expect(page.getByRole('menuitem', { name: '用户管理', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([])
  await page.goto('/users')
  await expect(page.getByText('没有访问权限', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '返回岗位管理', exact: true }).click()
  await page.getByRole('button', { name: /测试审核人 · 只读用户/ }).hover()
  await page.getByText('退出登录', { exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.screenshot({ path: test.info().outputPath('login-page.png'), animations: 'disabled' })
})

test('first login requires changing password before business access', async ({ page }) => {
  let changed = false
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/me') return route.fulfill({ json: { ...adminIdentity, must_change_password: true } })
    if (path === '/api/auth/change-password') { changed = true; return route.fulfill({ json: { detail: '请重新登录' } }) }
    throw new Error(`Business request must not happen: ${path}`)
  })
  await page.goto('/jobs')
  await expect(page).toHaveURL(/\/change-password$/)
  await page.getByLabel('原密码', { exact: true }).fill('Old-password-123!')
  await page.getByLabel('新密码', { exact: true }).fill('New-password-456!')
  await page.getByLabel('确认新密码', { exact: true }).fill('New-password-456!')
  await page.getByRole('button', { name: '修改并重新登录', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  expect(changed).toBe(true)
})

test('administrator creates a user through user management', async ({ page }) => {
  const rows = [adminIdentity]
  let created = false
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/me') return route.fulfill({ json: adminIdentity })
    if (path === '/api/auth/roles') return route.fulfill({ json: { items: [{ id: '2', name: '招聘人员' }] } })
    if (path === '/api/auth/users') {
      if (route.request().method() === 'POST') { created = true; expect(route.request().postDataJSON()).toMatchObject({ username: 'newuser', role_id: 2 }); rows.push({ ...adminIdentity, username: 'newuser', id: '2' }); return route.fulfill({ status: 201, json: rows[1] }) }
      return route.fulfill({ json: { items: rows } })
    }
    throw new Error(path)
  })
  await page.goto('/users')
  await page.getByRole('button', { name: '新建用户', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '新建用户', exact: true })
  await dialog.getByLabel('用户名', { exact: true }).fill('newuser')
  await dialog.getByLabel('显示姓名', { exact: true }).fill('新招聘人员')
  await dialog.getByLabel('设置密码', { exact: true }).fill('Initial-password-123!')
  await dialog.getByRole('button', { name: '保存用户', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(created).toBe(true)
  await expect(page.getByRole('cell', { name: 'newuser', exact: true })).toBeVisible()
})
