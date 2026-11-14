import { test, expect } from '@playwright/test'
import { createHash } from 'node:crypto'

test('resume workspace: jobs, details, SHA uploads, duplicate feedback, inline evaluation and deletion', async ({ page }) => {
  const time = '2026-11-14T00:00:00Z'
  const jobs = [{ id: '1', name: '海外项目负责人', status: 'active' }, { id: '2', name: 'Python 工程师', status: 'active' }]
  type Row = Record<string, any>
  const rows: Record<string, Row[]> = { '1': [{ id: '11', file_id: '101', display_name: '已有简历.pdf', file_type: 'pdf', sha256: 'a'.repeat(64), size_bytes: 2048, page_count: 1, parse_status: 'completed', parse_error: null, added_at: time }], '2': [] }
  let sequence = 11
  let uploads = 0
  let evaluated: string[] = []
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const req = route.request(), url = new URL(req.url()), method = req.method(), path = url.pathname
    const send = (json: unknown, status = 200) => route.fulfill({ json, status })
    if (path === '/api/resume-workspace/jobs') return send({ items: jobs.map(j => ({ ...j, resume_count: rows[j.id]!.length, parsed_count: rows[j.id]!.length })) })
    const match = path.match(/^\/api\/jobs\/(\d+)\/resumes(?:\/(\d+))?$/)
    if (match) {
      const jid = match[1]!, rid = match[2]
      if (rid) {
        const row = rows[jid]!.find(r => r.id === rid)
        if (!row) return send({ detail: '已移除' }, 404)
        if (method === 'DELETE') { rows[jid] = rows[jid]!.filter(r => r.id !== rid); return route.fulfill({ status: 204 }) }
        return send({ ...row, sha256_verified: true, pages: [{ page_no: 1, text: 'Test resume: managed overseas projects for twelve years.' }], import_task: { status: 'completed', current_node: null, node_progress: [{ name: 'prepare_import', status: 'completed' }, { name: 'parse_pdf', status: 'completed' }], error_message: null }, evaluations: [] })
      }
      if (method === 'GET') {
        const filtered = rows[jid]!.filter(r => !url.searchParams.get('keyword') || r.display_name.includes(url.searchParams.get('keyword')))
        return send({ items: filtered, total: filtered.length })
      }
      if (method === 'POST') {
        const body = req.postDataBuffer()!.toString('utf8')
        const names = [...body.matchAll(/filename="([^"]+)"/g)].map(m => m[1]!)
        expect(body).toContain('name="sha256s"')
        const expectedHash = createHash('sha256').update(Buffer.from('%PDF-test-upload')).digest('hex')
        expect(body).toContain(expectedHash)
        uploads++
        const items = names.map((name, i) => {
          if (uploads === 2 && i === 1) return { filename: name, result: 'duplicate', message: '该岗位已有相同内容的简历' }
          rows[jid]!.push({ id: String(++sequence), file_id: String(100 + sequence), display_name: name, file_type: 'pdf', sha256: expectedHash, size_bytes: 16, page_count: 1, parse_status: 'completed', parse_error: null, added_at: time })
          return { filename: name, result: 'accepted', message: 'SHA-256 校验通过' }
        })
        return send({ items, accepted: items.filter(i => i.result === 'accepted').length, duplicates: items.filter(i => i.result === 'duplicate').length, rejected: 0 }, 201)
      }
    }
    if (path === '/api/jobs/1') return send({ ...jobs[0], versions: [{ id: '7', version_no: 1, published_by: '招聘人员' }] })
    if (path === '/api/jobs/1/evaluate') {
      evaluated = req.postDataJSON().resume_ids
      expect(req.postDataJSON().request_id).toMatch(/^evaluation_/)
      for (const row of rows['1']!) if (evaluated.includes(row.id)) row.latest_evaluation = { id: '501', processing_status: 'running', total_score: null, recommendation: null, queued: true }
      return send({ status: 'running', accepted: evaluated.length, already_started: false }, 202)
    }
    if (path === '/api/batches/77') return send({ id: '77', name: '测试评估', status: 'pending', job_id: '1', rule_version_id: '7', rule_snapshot: {}, progress: { pending: 1, running: 0, waiting_review: 0, completed: 0, failed: 0 }, total: 1 })
    if (path === '/api/candidates') return send({ items: [], total: 0 })
    return send({ items: [], total: 0 })
  })
  await page.goto('/batches')
  await expect(page).toHaveURL(/\/resumes$/)
  await expect(page.getByRole('menuitem', { name: '评估批次', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '查看评估批次', exact: true })).toHaveCount(0)
  await expect(page.getByText('已有简历.pdf', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /Python 工程师/ })).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('resume-workspace.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('button', { name: '详情', exact: true }).first().click()
  const detail = page.getByRole('dialog', { name: '简历详情', exact: true })
  await expect(detail.getByText('原件 SHA-256 校验通过', { exact: true })).toBeVisible()
  await expect(detail.getByText(/Test resume: managed/)).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: /Python 工程师/ }).click()
  await expect(page.getByText('该岗位还没有简历，支持单份或多份导入', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /海外项目负责人.*份简历/ }).click()

  async function importFiles(names: string[]) {
    await page.getByRole('button', { name: '导入简历', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '导入岗位简历', exact: true })
    await dialog.locator('input[type="file"]').setInputFiles(names.map(name => ({ name, mimeType: 'application/pdf', buffer: Buffer.from('%PDF-test-upload') })))
    await dialog.getByRole('button', { name: /^导入.*份简历$/ }).click()
    await expect(dialog.getByText('SHA-256 校验通过', { exact: true }).first()).toBeVisible()
    if (names.length > 1) await expect(dialog.getByText('重复', { exact: true })).toBeVisible()
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(dialog).not.toBeVisible()
  }
  await importFiles(['单份上传.pdf'])
  await expect(page.getByRole('row').filter({ hasText: '单份上传.pdf' })).toBeVisible()
  await importFiles(['批量上传.pdf', '重复简历.pdf'])
  expect(uploads).toBe(2)
  await page.getByRole('row').filter({ hasText: '单份上传.pdf' }).getByRole('button', { name: '移除', exact: true }).click()
  await page.getByRole('button', { name: '确认移除', exact: true }).click()
  await expect(page.getByRole('row').filter({ hasText: '单份上传.pdf' })).toHaveCount(0)
  await page.getByRole('row').filter({ hasText: '已有简历.pdf' }).locator('.el-checkbox').click()
  await page.getByRole('button', { name: /^开始评估/ }).click()
  const evaluation = page.getByRole('dialog', { name: '开始简历评估' })
  await evaluation.getByRole('button', { name: '确认开始', exact: true }).click()
  await expect(page).toHaveURL(/\/resumes$/)
  await expect(page.getByRole('row').filter({ hasText: '已有简历.pdf' }).getByText('评估中', { exact: true })).toBeVisible()
  await expect(page.getByRole('row').filter({ hasText: '已有简历.pdf' }).getByRole('button', { name: '评估结果', exact: true })).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('unified-resume-evaluation.png'), fullPage: true, animations: 'disabled' })
  expect(evaluated).toEqual(['11'])
})
