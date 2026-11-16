import { test, expect } from './fixtures'

test('phase filters guide human review and only admitted candidates get scheduling actions', async ({ page }) => {
  const base = { job_id: '1', job_name: '海外项目负责人', batch_id: '1', file_id: '1', processing_status: 'completed', review_status: 'pending', schedule_status: 'unscheduled', recommend_threshold: 75, review_threshold: 60, created_at: '2030-01-01T00:00:00Z', hard_conditions: [], dimension_scores: [], evidence: [], extracted_facts: [], missing_fields: [], risks: [], review_notes: [], actions: [], review_history: [], total_score: 60, recommendation: 'needs_review', retry_count: 0 }
  const rows = [
    { ...base, id: '1', name: '等待人工确认', original_filename: 'review.pdf', processing_status: 'waiting_review' },
    { ...base, id: '2', name: '已准入候选人', original_filename: 'interview.pdf', total_score: 90, recommendation: 'recommended', review_status: 'approved' },
  ]
  const phases: string[] = []
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/resume-workspace/jobs') return route.fulfill({ json: { items: [{ id: '1', name: base.job_name, status: 'active' }] } })
    if (url.pathname === '/api/evaluations') {
      const phase = url.searchParams.get('workflow') || ''
      phases.push(phase)
      const filtered = phase === 'waiting_review' ? rows.slice(0, 1) : phase === 'awaiting_schedule' ? rows.slice(1) : rows
      return route.fulfill({ json: { items: filtered, total: filtered.length, counts: { all: 2, high: 1, middle: 1 }, thresholds: [{ recommend: 75, review: 60 }] } })
    }
    if (url.pathname === '/api/candidates/1') return route.fulfill({ json: rows[0] })
    if (url.pathname === '/api/interviews') return route.fulfill({ json: { items: [], total: 0, counts: { all: 0, pending: 0, scheduled: 0 } } })
    throw new Error(`Unexpected request: ${url.pathname}`)
  })
  await page.goto('/evaluations?workflow=waiting_review')
  const flow = page.getByRole('navigation', { name: '招聘操作流程', exact: true })
  await expect(flow.getByRole('link', { name: /审核结果/ })).toHaveAttribute('aria-current', 'step')
  await expect(page.getByRole('tab', { name: '待人工审核', exact: true })).toHaveAttribute('aria-selected', 'true')
  const pending = page.getByRole('row').filter({ hasText: '等待人工确认' })
  await expect(pending.getByRole('button', { name: '人工审核', exact: true })).toBeVisible()
  await expect(pending.getByRole('button', { name: '排期管理', exact: true })).toHaveCount(0)
  await pending.getByRole('button', { name: '人工审核', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '简历详情与人工审核', exact: true })
  await expect(drawer.getByRole('region', { name: '审核概览' })).toContainText('等待人工确认')
  await expect(drawer.getByRole('button', { name: '管理面试排期', exact: true })).toHaveCount(0)
  await expect(drawer.getByText('当前节点', { exact: true })).not.toBeVisible()
  await drawer.getByRole('button', { name: /查看处理信息与技术记录/ }).click()
  await expect(drawer.getByText('当前节点', { exact: true })).toBeVisible()
  await drawer.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('tab', { name: '待安排面试', exact: true }).click()
  await expect(page.getByRole('row').filter({ hasText: '已准入候选人' }).getByRole('button', { name: '排期管理', exact: true })).toBeVisible()
  expect(phases).toContain('waiting_review')
  expect(phases).toContain('awaiting_schedule')
  await page.locator('main').evaluate(el => { el.scrollTop = 0 })
  await page.screenshot({ path: test.info().outputPath('human-workflow-desktop.png'), animations: 'disabled' })
  await page.setViewportSize({ width: 768, height: 900 })
  await expect(page.getByRole('button', { name: '展开侧栏', exact: true })).toBeVisible()
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 768)
  await page.screenshot({ path: test.info().outputPath('human-workflow-tablet.png'), animations: 'disabled' })
  await flow.getByRole('link', { name: /安排面试/ }).click()
  await expect(page.getByText(/暂无待安排的候选人/)).toBeVisible()
})
