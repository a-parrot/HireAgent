import { test, expect } from './fixtures'

test('hard-condition rejection shows its reason; scoring shows item names, fixed points and quotes', async ({ page }) => {
  const quote = '负责海外模块化项目交付及团队管理。'
  const base = { id: '1', batch_id: '1', job_id: '1', file_id: '1', name: '测试候选人', original_filename: 'synthetic.pdf', processing_status: 'completed', review_status: 'pending', schedule_status: 'unscheduled', retry_count: 0, review_history: [], actions: [], extracted_facts: [], missing_fields: [], risks: [], review_notes: [], evidence: [{ evidence_id: 'e1', file_id: '1', block_id: 'document', page_no: null, quote }], rule_snapshot: { evaluation_flow: 'hard_conditions_first_v1', hard_conditions: { operator: 'all', items: [{ id: 'management', description: '具备项目或团队管理经历' }] }, dimensions: [{ id: 'modular', name: '模块化建筑项目经验', max_score: 30 }] } }
  const rejected = { ...base, total_score: null, recommendation: 'deferred', hard_conditions: [{ condition_id: 'management', condition_name: '具备项目或团队管理经历', result: 'unsatisfied', reason: '原文明示仅独立执行，未承担管理职责', evidence_ids: ['e1'], blocking: true }], dimension_scores: [] }
  const scored = { ...base, id: '2', total_score: 30, recommendation: 'deferred', hard_conditions: [{ condition_id: 'management', result: 'satisfied', reason: '原文明示管理职责', evidence_ids: ['e1'] }], dimension_scores: [{ dimension_id: 'modular', dimension_name: '模块化建筑项目经验', max_score: 30, score: 30, reason: '原文明示模块化项目经验', evidence_ids: ['e1'] }] }
  await page.route(url => url.pathname.startsWith('/api/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/files/1/content') return route.fulfill({ json: { markdown: quote } })
    if (path === '/api/candidates/1') return route.fulfill({ json: rejected })
    if (path === '/api/candidates/2') return route.fulfill({ json: scored })
    throw new Error(`Unexpected request: ${path}`)
  })
  await page.goto('/candidates/1')
  await expect(page.getByText('硬条件未通过，不推荐；未进入评分', { exact: true })).toBeVisible()
  await expect(page.getByText('硬条件未通过，已跳过评分', { exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '具备项目或团队管理经历', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /证据 1/ }).first().click()
  await expect(page.getByRole('dialog', { name: '证据片段与上下文' }).locator('mark')).toHaveText(quote)
  await page.keyboard.press('Escape')
  await page.screenshot({ path: test.info().outputPath('hard-condition-rejected.png'), fullPage: true, animations: 'disabled' })
  await page.goto('/candidates/2')
  await expect(page.getByText('模块化建筑项目经验', { exact: true })).toBeVisible()
  await expect(page.getByText('30.0 / 30 分', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /证据 1/ }).last().click()
  await expect(page.getByRole('dialog', { name: '证据片段与上下文' }).locator('mark')).toHaveText(quote)
  await page.screenshot({ path: test.info().outputPath('fixed-score-quotes.png'), fullPage: true, animations: 'disabled' })
})
