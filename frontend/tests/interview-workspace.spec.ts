import { test, expect } from './fixtures'

test('candidate booking defaults to 45 minutes, previews batch intervals, and submits once', async ({ page }) => {
  let booked = false
  let submitted: any
  const rows = [1, 2].map(id => ({ candidate: { id: String(id), batch_id: '1', name: `候选人${id}`, original_filename: `${id}.pdf`, total_score: 80 }, job_name: '项目经理', reservation: null, slot: null, editable: true }))
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const request = route.request(), url = new URL(request.url())
    if (url.pathname === '/api/interviews' && request.method() === 'GET') {
      return route.fulfill({ json: { items: booked ? [] : rows, total: booked ? 0 : 2, counts: { all: 2, pending: booked ? 0 : 2, scheduled: booked ? 2 : 0 } } })
    }
    if (url.pathname === '/api/interviews' && request.method() === 'POST') {
      submitted = request.postDataJSON(); booked = true
      return route.fulfill({ status: 201, json: { scheduled: 2 } })
    }
    return route.fulfill({ json: { items: [], total: 0 } })
  })
  await page.goto('/schedules')
  await expect(page.getByRole('heading', { name: '面试排期' })).toBeVisible()
  await page.locator('.el-table__header-wrapper .el-checkbox').click()
  await page.getByRole('button', { name: '批量排期' }).click()
  const dialog = page.getByRole('dialog', { name: '批量安排面试', exact: true })
  const start = dialog.getByPlaceholder('选择开始时间')
  await start.fill('2032-01-01 09:00')
  await start.press('Enter')
  await expect(dialog.getByPlaceholder('默认开始后 45 分钟')).toHaveValue('2032-01-01 09:45')
  await dialog.getByPlaceholder('默认开始后 45 分钟').fill('2032-01-01 10:00')
  await dialog.getByPlaceholder('默认开始后 45 分钟').press('Enter')
  await dialog.getByRole('spinbutton').fill('15')
  await dialog.getByRole('spinbutton').press('Tab')
  await expect(dialog.locator('.preview-row')).toHaveCount(2)
  await expect(dialog.locator('.preview-row').nth(1)).toContainText('10:15')
  await page.screenshot({ path: 'test-results/interview-workspace.png', fullPage: true })
  await dialog.getByRole('button', { name: '确认安排 2 人' }).click()
  await expect(page.getByText('已安排 2 人面试')).toBeVisible()
  expect(submitted).toMatchObject({ candidate_ids: ['1', '2'], starts_at: '2032-01-01T09:00:00+08:00', ends_at: '2032-01-01T10:00:00+08:00', gap_minutes: 15 })
  await expect(dialog).not.toBeVisible()
})
