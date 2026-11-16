import { test, expect } from './fixtures'

test('active evaluation and parsing filters show the working file across list pages', async ({ page }) => {
  const base = { file_type: 'pdf', parse_status: 'completed', size_bytes: 100, latest_evaluation: null }
  const active = { ...base, id: '1', file_id: '1', display_name: '当前评估.pdf', latest_evaluation: { id: '9', processing_status: 'running', current_node: 'screen_hard_conditions', progress: { current: 2, total: 5 }, total_score: null } }
  const parsing = { ...base, id: '2', file_id: '2', display_name: '当前解析.pdf', parse_status: 'running' }
  const waiting = { ...base, id: '20', file_id: '20', display_name: '排队文件.pdf', latest_evaluation: { id: '20', processing_status: 'pending', queued: true, total_score: null } }
  const filters: string[] = []
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/resume-workspace/jobs') return route.fulfill({ json: { items: [{ id: '1', name: '测试岗位', status: 'active', resume_count: 21, parsed_count: 20 }] } })
    if (url.pathname === '/api/jobs/1/resumes') {
      const status = url.searchParams.get('status'), evaluation = url.searchParams.get('evaluation_status')
      filters.push(`${status || ''}/${evaluation || ''}`)
      return route.fulfill({ json: { items: evaluation === 'running' ? [active] : status === 'running' ? [parsing] : [waiting], total: 1 } })
    }
    throw new Error(url.pathname)
  })
  await page.goto('/resumes')
  await expect(page.getByRole('row').filter({ hasText: '排队文件.pdf' }).getByText('排队中', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看正在评估', exact: true }).click()
  await expect(page.getByText('当前评估.pdf', { exact: true })).toBeVisible()
  await expect(page.getByText('筛选硬条件 · 第 2/5 段', { exact: true })).toBeVisible()
  await expect(page.getByText('排队文件.pdf', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '查看正在解析', exact: true }).click()
  await expect(page.getByText('当前解析.pdf', { exact: true })).toBeVisible()
  await expect(page.getByText('当前评估.pdf', { exact: true })).toHaveCount(0)
  expect(filters).toContain('/running')
  expect(filters).toContain('running/')
  await page.getByRole('button', { name: '全部简历', exact: true }).click()
  await expect(page.getByText('排队文件.pdf', { exact: true })).toBeVisible()
})
