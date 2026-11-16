import { test, expect } from './fixtures'

test('workflow failures are separate from human decisions and cached review recovery is explicit', async ({ page }) => {
  const base = { batch_id: '10', job_id: '1', job_name: '项目负责人', file_id: '1', recommend_threshold: 75, review_threshold: 60, review_status: 'pending', schedule_status: 'unscheduled', waitlist_reason: null, processing_status: 'failed', completed_at: '2030-01-01T00:00:00Z' }
  const rows = [
    { ...base, id: '15', name: '交接异常', original_filename: 'cached.pdf', total_score: 61, score_bucket: 'middle', recommendation: 'needs_review', error_node: 'human_review', error_message: 'checkpoint failed' },
    { ...base, id: '14', name: '模型结构异常', original_filename: 'model.pdf', total_score: null, score_bucket: 'unscored', recommendation: null, error_node: 'analyze_resume', error_message: '模型输出无法解析为约定结构' },
  ]
  let recovered = false
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const path = new URL(route.request().url()).pathname
    const send = (json: unknown) => route.fulfill({ json })
    if (path === '/api/resume-workspace/jobs') return send({ items: [{ id: '1', name: '项目负责人', status: 'active' }] })
    if (path === '/api/evaluations') return send({ items: rows, total: 2, counts: { all: 2, middle: 1, unscored: 1 }, thresholds: [{ recommend: 75, review: 60 }] })
    if (path === '/api/candidates/15/restore-review') {
      recovered = true
      Object.assign(rows[0]!, { processing_status: 'waiting_review', error_node: null, error_message: null })
      return send({ candidate_id: '15', status: 'running' })
    }
    throw new Error(`Unexpected API call: ${path}`)
  })
  await page.goto('/evaluations')
  await expect(page.getByRole('columnheader', { name: '处理进度', exact: true })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '下一步操作', exact: true })).toBeVisible()
  const paused = page.getByRole('row').filter({ hasText: '交接异常' })
  await expect(paused.getByText('评估失败', { exact: true })).toBeVisible()
  await expect(paused.getByText('待恢复审核', { exact: true })).toBeVisible()
  const model = page.getByRole('row').filter({ hasText: '模型结构异常' })
  await expect(model.getByText('尚未进入审核', { exact: true })).toBeVisible()
  await expect(model.getByRole('button', { name: '恢复待审核', exact: true })).toHaveCount(0)
  await paused.getByRole('button', { name: '恢复待审核', exact: true }).click()
  await expect(paused.getByText('待人工审核', { exact: true })).toBeVisible()
  await expect(paused.getByText('评分完成', { exact: true })).toBeVisible()
  expect(recovered).toBe(true)
  await page.screenshot({ path: test.info().outputPath('review-recovery-status.png'), fullPage: true, animations: 'disabled' })
})
