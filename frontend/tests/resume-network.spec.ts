import { test, expect } from './fixtures'

test('slow polling stays single-flight; network failure preserves stale data and retry recovers', async ({ page }) => {
  await page.clock.install()
  let holdNext = false
  let failHeld = false
  let release: (() => void) | undefined
  let inFlight = 0
  let maxInFlight = 0
  let status = 'running'
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/resume-workspace/jobs') return route.fulfill({ json: { items: [{ id: '1', name: '网络恢复测试岗位', status: 'active', resume_count: 1, parsed_count: 1 }] } })
    if (path === '/api/jobs/1/resumes') {
      inFlight++; maxInFlight = Math.max(maxInFlight, inFlight)
      try {
        if (holdNext) {
          holdNext = false
          await new Promise<void>(resolve => { release = resolve })
          if (failHeld) { failHeld = false; await route.abort('failed'); return }
        }
        await route.fulfill({ json: { items: [{ id: '1', file_id: '1', display_name: '连接测试.pdf', file_type: 'pdf', sha256: 'a'.repeat(64), size_bytes: 1234, page_count: null, parse_status: 'completed', added_at: '2026-11-15T00:00:00Z', latest_evaluation: { id: '9', processing_status: status, total_score: status === 'completed' ? 88 : null, recommendation: status === 'completed' ? 'recommended' : null, queued: true } }], total: 1 } }).catch(() => { /* The timed-out request may already be closed. */ })
      } finally { inFlight-- }
      return
    }
    return route.fulfill({ json: { items: [], total: 0 } })
  })
  await page.goto('/resumes')
  await expect(page.getByText('连接测试.pdf', { exact: true })).toBeVisible()
  holdNext = true
  await page.getByRole('button', { name: '刷新简历', exact: true }).click()
  await expect.poll(() => !!release).toBe(true)
  await page.clock.fastForward(15000)
  expect(maxInFlight).toBe(1)
  failHeld = true
  release!()
  await expect(page.getByRole('alert').filter({ hasText: '无法连接后端服务' })).toBeVisible()
  await expect(page.getByText('连接测试.pdf', { exact: true })).toBeVisible()
  await expect(page.getByText(/当前显示上次成功加载的数据/)).toBeVisible()
  expect(maxInFlight).toBe(1)
  await expect.poll(() => inFlight).toBe(0)
  status = 'completed'
  await page.getByRole('button', { name: '重试连接', exact: true }).click()
  await expect(page.getByText('已完成', { exact: true })).toBeVisible()
  await expect(page.getByText('88.0 · 推荐', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert').filter({ hasText: '列表刷新失败' })).toHaveCount(0)
  const timeoutMessage = await page.evaluate(async () => {
    const { http } = await import('/src/api/http.ts')
    try {
      await http.get('/test-only-timeout', { adapter: async () => { throw Object.assign(new Error('test timeout'), { code: 'ECONNABORTED', request: {} }) } })
    } catch (error) { return (error as Error).message }
  })
  expect(timeoutMessage).toContain('请求超时')
  expect(timeoutMessage).not.toContain('无法连接后端服务')
})
