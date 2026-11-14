import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'

test('existing jobs load by default; create, edit rules, publish and delete through forms', async ({ page }) => {
  // Browser-only transport fixture. It never changes the user's database.
  const initialRules = JSON.parse(readFileSync('../backend/app/conf/initial_job.json', 'utf-8'))
  const time = '2026-11-14T00:00:00Z'
  type Row = Record<string, any>
  let rows: Row[] = [{ id: '1', code: 'existing-job', name: initialRules.job_name, responsibilities: '已有岗位职责', requirements: '已有任职要求', draft_rules: initialRules, status: 'active', draft_version: 1, created_at: time, updated_at: time }]
  const versions: Record<string, Row[]> = { '1': [{ id: '1', job_id: '1', version_no: 1, rule_snapshot: structuredClone(initialRules), published_by: '测试人员', published_at: time }] }
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    const send = (json: unknown, status = 200) => route.fulfill({ status, json })
    if (path === '/api/jobs' && method === 'GET') {
      const found = rows.filter(r => !url.searchParams.get('keyword') || r.name.includes(url.searchParams.get('keyword')))
      return send({ items: found.map(r => ({ ...r, latest_published_version: versions[r.id]?.[0]?.version_no ?? null })), total: found.length })
    }
    if (path === '/api/jobs' && method === 'POST') {
      const job = { ...request.postDataJSON(), id: '2', code: 'test-created-job', status: 'active', draft_version: 1, created_at: time, updated_at: time }
      rows.push(job); versions['2'] = []
      return send(job, 201)
    }
    const match = path.match(/^\/api\/jobs\/(\d+)(?:\/(publish|disable|enable))?$/)
    if (!match) return send({ detail: 'Unexpected test route' }, 404)
    const job = rows.find(r => r.id === match[1])
    if (!job) return send({ detail: '岗位不存在' }, 404)
    if (method === 'GET') return send({ ...job, versions: versions[job.id] })
    if (method === 'PATCH') {
      const body = request.postDataJSON()
      if (body.draft_version !== job.draft_version) return send({ detail: '版本过期' }, 409)
      Object.assign(job, body, { draft_version: job.draft_version + 1 })
      return send(job)
    }
    if (method === 'POST' && match[2] === 'publish') {
      const body = request.postDataJSON()
      const version = { id: String(10 + versions[job.id]!.length), job_id: job.id, version_no: versions[job.id]!.length + 1, rule_snapshot: structuredClone(job.draft_rules), published_by: body.operator_name, published_at: time }
      versions[job.id]!.unshift(version); job.draft_version++
      return send(version)
    }
    if (method === 'DELETE') { rows = rows.filter(r => r.id !== job.id); return route.fulfill({ status: 204 }) }
    if (match[2]) { job.status = match[2] === 'enable' ? 'active' : 'disabled'; return send(job) }
    return send({ detail: 'Unexpected request' }, 400)
  })

  await page.goto('/jobs')
  await expect(page.getByText(initialRules.job_name, { exact: true })).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('jobs-reference-style.png'), fullPage: true })
  await page.getByRole('button', { name: '收起侧栏', exact: true }).click()
  await expect(page.getByRole('complementary', { name: '主导航' })).toHaveCSS('width', '64px')
  await page.getByRole('button', { name: '展开侧栏', exact: true }).click()
  await expect(page.getByRole('menuitem', { name: '岗位管理', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '新建岗位', exact: true }).first().click()
  const dialog = page.getByRole('dialog', { name: '新建岗位与评分规则' })
  await dialog.getByPlaceholder('例如：高级后端工程师').fill('手动配置岗位')
  await dialog.getByRole('button', { name: '创建并发布', exact: true }).click()
  await expect(dialog.getByText('发布前还需完善以下内容', { exact: true })).toBeVisible()
  expect(rows).toHaveLength(1) // incomplete rules do not create a duplicate job
  await dialog.getByRole('button', { name: '＋ 添加条件', exact: true }).click()
  await dialog.getByRole('textbox', { name: '硬条件内容' }).fill('具备相关项目经验')
  await dialog.getByRole('button', { name: '＋ 添加评分维度', exact: true }).click()
  await dialog.getByRole('textbox', { name: '维度 1 名称', exact: true }).fill('项目交付经验')
  await dialog.getByRole('textbox', { name: '维度 1 得分标准', exact: true }).fill('参与项目得 1–50 分，主导完整交付得 51–100 分')
  await dialog.getByRole('spinbutton', { name: '推荐面试最低分', exact: true }).fill('80')
  await dialog.getByRole('spinbutton', { name: '人工复核最低分', exact: true }).fill('50')
  await dialog.getByPlaceholder('创建并发布时填写；仅保存草稿无需填写').fill('测试招聘人员')
  await dialog.locator('.el-dialog__body').evaluate(element => element.scrollTop = 0)
  await page.screenshot({ path: test.info().outputPath('job-rule-form.png'), fullPage: true })
  await dialog.getByRole('button', { name: '创建并发布', exact: true }).click()
  await expect(page).toHaveURL(/\/jobs\/2$/)
  expect(rows[1]!.draft_rules.recommend_threshold).toBe(80)
  expect(rows[1]!.draft_rules.dimensions[0].criteria).toContain('主导完整交付')
  await page.getByRole('button', { name: '编辑岗位与规则', exact: true }).click()
  await page.getByRole('textbox', { name: '岗位名称', exact: true }).fill('修改后的岗位')
  await page.getByRole('textbox', { name: '维度 1 名称', exact: true }).fill('修改后的评分名称')
  await page.getByRole('button', { name: '＋ 添加评分维度', exact: true }).click()
  await page.locator('.dimension-card').last().getByRole('button', { name: '删除维度', exact: true }).click()
  await page.getByRole('button', { name: '保存并发布', exact: true }).click()
  const publish = page.getByRole('dialog', { name: '发布规则版本' })
  await publish.getByPlaceholder('招聘人员姓名').fill('测试招聘人员')
  await publish.getByRole('button', { name: '确认发布', exact: true }).click()
  await expect(page.getByRole('button', { name: '编辑岗位与规则', exact: true })).toBeVisible()
  expect(versions['2']).toHaveLength(2)
  expect(versions['2']![1]!.rule_snapshot.dimensions[0].name).toBe('项目交付经验')
  expect(rows[1]!.draft_rules.dimensions[0].name).toBe('修改后的评分名称')

  await page.getByRole('menuitem', { name: '岗位管理', exact: true }).click()
  const row = page.getByRole('row').filter({ hasText: '修改后的岗位' })
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page.getByText('修改后的岗位', { exact: true })).toHaveCount(0)
  await expect(page.getByText(initialRules.job_name, { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText(initialRules.job_name, { exact: true })).toBeVisible()
})
