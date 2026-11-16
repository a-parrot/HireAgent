import { test, expect } from './fixtures'

test('high-score scheduling and single/bulk invalid-record deletion preserve admitted candidates', async ({ page }) => {
  const time = '2030-01-01T00:00:00Z'
  const base = { job_id: '1', job_name: '项目负责人', batch_id: '20', file_id: '1', review_version: 0, waitlist_reason: null, error_message: null, recommend_threshold: 75, review_threshold: 60, completed_at: time }
  let rows: Record<string, any>[] = [
    { ...base, id: '88', name: '已批准低分', original_filename: 'high.pdf', total_score: 60, score_bucket: 'middle', processing_status: 'completed', recommendation: 'recommended', review_status: 'approved', schedule_status: 'waitlisted' },
    { ...base, id: '92', name: '高分仍需复核', original_filename: 'uncertain.pdf', total_score: 92, score_bucket: 'high', processing_status: 'waiting_review', recommendation: 'needs_review', review_status: 'pending', schedule_status: 'unscheduled' },
    { ...base, id: '3', name: '失败无分', original_filename: 'invalid.pdf', total_score: null, score_bucket: 'unscored', processing_status: 'failed', recommendation: null, review_status: 'pending', schedule_status: 'unscheduled' },
    { ...base, id: '4', name: '失败低分', original_filename: 'low.pdf', total_score: 39, score_bucket: 'low', processing_status: 'failed', recommendation: 'needs_review', review_status: 'pending', schedule_status: 'unscheduled' },
  ]
  let scheduled = false
  const removed: string[] = []
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    const send = (json: unknown) => route.fulfill({ json })
    if (path === '/api/resume-workspace/jobs') return send({ items: [{ id: '1', name: '项目负责人', status: 'active' }] })
    if (path === '/api/evaluations') return send({ items: rows, total: rows.length, counts: { all: rows.length, high: 2, middle: 0, low: rows.some(r => r.id === '4') ? 1 : 0, unscored: rows.some(r => r.id === '3') ? 1 : 0 }, thresholds: [{ recommend: 75, review: 60 }] })
    if (path === '/api/evaluations/auto-schedule') {
      expect(req.postDataJSON().candidate_ids).toEqual(['88'])
      expect(req.postDataJSON()).toMatchObject({ starts_at: '2030-01-01T09:00:00+08:00', timezone: 'Asia/Shanghai', interviewer: '测试面试官' })
      scheduled = true
      rows[0]!.schedule_status = 'scheduled'
      return send({ eligible: 1, scheduled: 1, waitlisted: 0, created_slots: 1, new_reservations: 1 })
    }
    if (path === '/api/evaluations/delete') {
      const ids = req.postDataJSON().candidate_ids as string[]
      expect(ids.every(id => id === '3' || id === '4')).toBe(true)
      removed.push(...ids); rows = rows.filter(row => !ids.includes(row.id))
      return send({ deleted: ids, already_deleted: [] })
    }
    return send({ items: [], total: 0 })
  })
  await page.goto('/evaluations')
  const high = page.getByRole('row').filter({ hasText: '已批准低分' })
  await high.locator('.el-checkbox').click()
  await expect(page.getByRole('button', { name: /^删除选中记录/ })).toBeDisabled()
  await page.getByRole('button', { name: '已批准自动排期', exact: true }).click()
  const scheduling = page.getByRole('dialog', { name: '已批准自动排期', exact: true })
  await scheduling.getByPlaceholder('选择面试起始时间').fill('2030-01-01 09:00')
  await scheduling.getByPlaceholder('填写面试官，留空使用默认面试日历').fill('测试面试官')
  await scheduling.getByRole('button', { name: '开始自动排期', exact: true }).click()
  await expect(high.getByText('已排期', { exact: true })).toBeVisible()
  expect(scheduled).toBe(true)
  await expect(page.getByRole('row').filter({ hasText: '高分仍需复核' }).getByText('待人工审核', { exact: true })).toBeVisible()
  const failed = page.getByRole('row').filter({ hasText: '失败无分' })
  await failed.locator('.el-checkbox').click()
  await page.getByRole('button', { name: /^删除选中记录/ }).click()
  await expect(page.getByText(/简历原件、解析历史和审计日志保留/)).toBeVisible()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(failed).toHaveCount(0)
  const low = page.getByRole('row').filter({ hasText: '失败低分' })
  await low.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(low).toHaveCount(0)
  await expect(high).toBeVisible()
  expect(removed).toEqual(['3', '4'])
  await page.locator('main').evaluate(el => { el.scrollTop = 0 })
  await expect(page.locator('.el-message')).toHaveCount(0, { timeout: 10000 })
  await page.screenshot({ path: test.info().outputPath('high-score-schedule-and-cleanup.png'), fullPage: true, animations: 'disabled' })
})


test('one click approves without a reason or confirmation dialog', async ({ page }) => {
  const row = { id: '21', name: '待批准候选人', batch_id: '1', job_id: '1', job_name: '项目负责人', original_filename: 'resume.pdf', total_score: null, review_version: 3, processing_status: 'failed', review_status: 'pending', schedule_status: 'unscheduled', recommendation: 'needs_review' }
  let submissions = 0
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/evaluations') return route.fulfill({ json: { items: [row], total: 1, counts: { all: 1 }, thresholds: [] } })
    if (path === '/api/candidates/21/review') {
      expect(route.request().postDataJSON()).toMatchObject({ operation: 'approve', reason: '', review_version: 3 })
      submissions++
      row.review_status = 'approved'
      return route.fulfill({ json: { resume_status: 'pending' } })
    }
    return route.fulfill({ json: { items: [], total: 0 } })
  })
  await page.goto('/evaluations')
  await page.getByRole('button', { name: '一键批准', exact: true }).click()
  await expect(page.getByText('已准入面试', { exact: true })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(submissions).toBe(1)
})
