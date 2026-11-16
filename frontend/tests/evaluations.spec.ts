import { test, expect } from './fixtures'

test('evaluation management filters score bands and completes review and scheduling in drawers', async ({ page }) => {
  const time = '2030-01-01T00:00:00Z'
  const base = { batch_id: '20', file_id: '1', job_id: '1', job_name: '项目负责人', rule_version_id: '1', review_version: 0, schedule_status: 'unscheduled', waitlist_reason: null, error_message: null, hard_conditions: [], dimension_scores: [], extracted_facts: [], evidence: [], missing_fields: [], risks: [], review_notes: [], review_history: [], reservation: null, actions: [], completed_at: time, recommend_threshold: 75, review_threshold: 60 }
  const rows: Record<string, any>[] = [
    { ...base, id: '1', name: '高分候选人', original_filename: 'high.pdf', total_score: 75, score_bucket: 'high', processing_status: 'completed', recommendation: 'recommended', review_status: 'approved' },
    { ...base, id: '2', name: '中分候选人', original_filename: 'middle.pdf', total_score: 68, score_bucket: 'middle', processing_status: 'waiting_review', recommendation: 'needs_review', review_status: 'pending' },
    { ...base, id: '3', name: '低分候选人', original_filename: 'low.pdf', total_score: 55, score_bucket: 'low', processing_status: 'completed', recommendation: 'deferred', review_status: 'pending' },
    { ...base, id: '4', name: '高分待核实', original_filename: 'uncertain.pdf', total_score: 92, score_bucket: 'high', processing_status: 'waiting_review', recommendation: 'needs_review', review_status: 'pending' },
  ]
  const slots = Array.from({ length: 4 }, (_, i) => ({ id: String(i + 1), batch_id: '20', starts_at: `2030-01-02T${String(i + 9).padStart(2, '0')}:00:00Z`, ends_at: `2030-01-02T${String(i + 9).padStart(2, '0')}:45:00Z`, timezone: 'UTC', interviewer: '测试面试官' }))
  let reservations: Record<string, any>[] = []
  let reviewed = false
  let scheduled = false
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    const send = (json: unknown, status = 200) => route.fulfill({ json, status })
    if (path === '/api/resume-workspace/jobs') return send({ items: [{ id: '1', name: '项目负责人', status: 'active', resume_count: 4, parsed_count: 4 }] })
    if (path === '/api/evaluations') {
      let filtered = rows.filter(row => !url.searchParams.get('bucket') || row.score_bucket === url.searchParams.get('bucket'))
      if (url.searchParams.get('keyword')) filtered = filtered.filter(r => r.name.includes(url.searchParams.get('keyword')!) || r.original_filename.includes(url.searchParams.get('keyword')!))
      if (url.searchParams.has('min_score')) filtered = filtered.filter(r => r.total_score >= Number(url.searchParams.get('min_score')))
      if (url.searchParams.has('max_score')) filtered = filtered.filter(r => r.total_score <= Number(url.searchParams.get('max_score')))
      return send({ items: filtered, total: filtered.length, counts: { all: 4, high: 2, middle: 1, low: 1, unscored: 0 }, thresholds: [{ recommend: 75, review: 60 }] })
    }
    if (path === '/api/interviews') return send({ items: rows.filter(r => r.id === '2').map(candidate => ({ candidate, job_name: candidate.job_name, editable: true, reservation: scheduled ? { id: '1' } : null, slot: null })), total: 1, counts: { all: 1, pending: scheduled ? 0 : 1, scheduled: scheduled ? 1 : 0 } })
    if (path === '/api/candidates/2') return send(rows[1])
    if (path === '/api/candidates/2/review') {
      expect(request.postDataJSON()).toMatchObject({ operation: 'approve', review_version: 0, operator_name: '测试审核人' })
      reviewed = true
      Object.assign(rows[1]!, { review_status: 'approved', review_version: 1, processing_status: 'completed' })
      return send({ id: '10', resume_status: 'pending' })
    }
    if (path === '/api/batches/20') return send({ id: '20', name: '项目负责人简历评估', status: 'evaluation_done', total: 4 })
    if (path === '/api/batches/20/slots') return send(slots)
    if (path === '/api/candidates') return send({ items: rows, total: rows.length })
    if (path === '/api/batches/20/schedule') {
      if (request.method() === 'POST') {
        scheduled = true
        const eligible = rows.filter(r => r.review_status === 'approved')
        reservations = eligible.map((r, i) => ({ id: String(i+1), candidate_id: r.id, slot_id: slots[i]!.id, batch_id: '20', preview_version: 0 }))
        eligible.forEach(r => r.schedule_status = 'scheduled')
      }
      return send({ reservations, waitlist: [] })
    }
    return send({ items: [], total: 0 })
  })
  await page.goto('/evaluations')
  await expect(page.getByRole('menuitem', { name: '评估管理', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /高分简历/ })).toContainText('2')
  await page.getByRole('button', { name: /高分简历/ }).click()
  await expect(page.getByRole('row').filter({ hasText: '高分待核实' }).getByText('待人工审核')).toBeVisible()
  await expect(page.getByRole('row').filter({ hasText: '中分候选人' })).toHaveCount(0)
  await page.getByRole('button', { name: /临界分数/ }).click()
  const middle = page.getByRole('row').filter({ hasText: '中分候选人' })
  await expect(middle).toBeVisible()
  await page.getByRole('button', { name: /低分简历/ }).click()
  await expect(page.getByRole('row').filter({ hasText: '低分候选人' })).toBeVisible()
  await page.getByRole('button', { name: /全部结果/ }).click()
  await page.getByPlaceholder('最低分', { exact: true }).fill('68')
  await page.getByPlaceholder('最高分', { exact: true }).fill('68')
  await page.getByRole('button', { name: '筛选', exact: true }).click()
  await expect(page.getByRole('row').filter({ hasText: '高分候选人' })).toHaveCount(0)
  await middle.getByRole('button', { name: '人工审核', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '简历详情与人工审核', exact: true })
  await drawer.getByRole('button', { name: '人工审核', exact: true }).click()
  const review = page.getByRole('dialog', { name: '人工审核决定', exact: true })
  await review.getByRole('combobox').click()
  await page.getByRole('option', { name: '已核对简历与评分依据', exact: true }).click()
  await expect(review.getByPlaceholder('招聘人员姓名')).toHaveValue('测试审核人')
  await review.getByRole('button', { name: '保存决定', exact: true }).click()
  await expect(review).not.toBeVisible()
  expect(reviewed).toBe(true)
  await drawer.getByRole('button', { name: '管理面试排期', exact: true }).click()
  const scheduling = page.getByRole('dialog', { name: '面试排期管理', exact: true })
  await expect(scheduling.getByRole('button', { name: '安排面试', exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(scheduling).not.toBeVisible()
  await expect(middle.getByText('已准入面试', { exact: true })).toBeVisible()
})
