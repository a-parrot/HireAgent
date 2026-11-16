import { test, expect } from './fixtures'

test('history logs show separate parsing snapshots, legacy logs and evaluation events', async ({ page }) => {
  const time = '2030-01-01T00:00:00Z'
  const requestedPages: number[] = []
  const candidateRows = Array.from({ length: 201 }, (_, index) => ({ id: String(index + 1), name: index === 0 ? '测试候选人' : `候选人${index + 1}`, original_filename: 'history.pdf', total_score: 88, processing_status: 'completed', error_message: null }))
  const imports = [1, 2, 3].map(id => ({ id: String(id), task_id: `parse-task-${id}`, file_id: '101', filename: 'history.pdf', status: 'completed', created_at: time, started_at: time, finished_at: time, has_snapshot: id !== 3, node_progress: [{ name: 'parse_pdf', status: 'completed', started_at: time, finished_at: time }], error_message: null }))
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const url = new URL(route.request().url()), path = url.pathname
    const send = (json: unknown) => route.fulfill({ json })
    if (path === '/api/resume-workspace/jobs') return send({ items: [{ id: '1', name: '项目负责人', status: 'active' }] })
    if (path === '/api/history/imports') return send({ items: imports, total: imports.length })
    if (/^\/api\/history\/imports\/\d+$/.test(path)) {
      const id = Number(path.split('/').at(-1)), record = imports[id-1]!
      return send({ ...record, source_sha256: 'a'.repeat(64), markdown: id === 3 ? null : id === 1 ? 'First parsing snapshot' : 'Second parsing snapshot', artifact_error: id === 3 ? '此历史记录仅保留日志，旧版本未保存独立正文快照' : null, artifact: id === 3 ? null : { parser_name: 'pymupdf-text', parser_version: 'test', char_count: 23, text_sha256: 'b'.repeat(64) } })
    }
    if (path === '/api/history/evaluations') return send({ items: [{ id: '20', name: '历史评估', job_name: '项目负责人', status: 'evaluation_done', total: 1, progress: { completed: 1 }, created_at: time, evaluation_completed_at: time }], total: 1 })
    if (path === '/api/candidates') {
      const size = Number(url.searchParams.get('page_size')), current = Number(url.searchParams.get('page'))
      if (size > 200) return route.fulfill({ status: 422, json: { detail: 'page_size must be <= 200' } })
      requestedPages.push(current)
      return send({ items: candidateRows.slice((current - 1) * size, current * size), total: candidateRows.length })
    }
    if (path === '/api/batches/20/events') return send({ items: [{ id: '1', created_at: time, candidate_id: '1', node_name: 'parse_pdf', event_type: 'completed', level: 'info', attempt_count: 1, message: '历史解析节点完成', details: null }], next_cursor: '1' })
    return send({ items: [], total: 0 })
  })
  await page.goto('/history?file_id=101')
  await expect(page.getByRole('menuitem', { name: '记录日志', exact: true })).toBeVisible()
  await expect(page.getByText('文件 101', { exact: true })).toBeVisible()
  const first = page.getByRole('row').filter({ hasText: '#1' })
  await first.getByRole('button', { name: '查看记录', exact: true }).click()
  let drawer = page.getByRole('dialog', { name: '历史解析记录', exact: true })
  await expect(drawer.getByText('First parsing snapshot', { exact: true })).toBeVisible()
  await expect(drawer.getByText('Second parsing snapshot', { exact: true })).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('parse-history-snapshot.png'), fullPage: true, animations: 'disabled' })
  await page.keyboard.press('Escape')
  await expect(drawer).not.toBeVisible()
  await page.getByRole('row').filter({ hasText: '#2' }).getByRole('button', { name: '查看记录', exact: true }).click()
  drawer = page.getByRole('dialog', { name: '历史解析记录', exact: true })
  await expect(drawer.getByText('Second parsing snapshot', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(drawer).not.toBeVisible()
  await page.getByRole('row').filter({ hasText: '#3' }).getByRole('button', { name: '查看记录', exact: true }).click()
  await expect(page.getByText('此历史记录仅保留日志，旧版本未保存独立正文快照', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(drawer).not.toBeVisible()
  await page.getByRole('tab', { name: '评估日志', exact: true }).click()
  await page.getByRole('button', { name: '查看日志', exact: true }).click()
  const evaluation = page.getByRole('dialog', { name: '历史评估日志', exact: true })
  await expect(evaluation.getByText('历史解析节点完成', { exact: true })).toBeVisible()
  await evaluation.getByRole('tab', { name: '候选人结果', exact: true }).click()
  await expect(evaluation.getByText('测试候选人', { exact: true })).toBeVisible()
  await expect(evaluation.getByText('88.0', { exact: true }).first()).toBeVisible()
  await expect(evaluation.getByText('候选人201', { exact: true })).toBeVisible()
  expect(requestedPages).toEqual([1, 2])
  await expect(page.getByRole('button', { name: '排期管理', exact: true })).toHaveCount(0)
  await expect(page).toHaveURL(/\/history\?file_id=101$/)
  await page.keyboard.press('Escape')
  await expect(evaluation).not.toBeVisible()
  await page.screenshot({ path: test.info().outputPath('evaluation-history-logs.png'), fullPage: true, animations: 'disabled' })
})
