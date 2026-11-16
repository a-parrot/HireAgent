import { test as base, expect } from '@playwright/test'

export const adminIdentity = { id: '1', username: 'tester', display_name: '测试审核人', role: 'admin', role_id: '1', role_name: '管理员', status: 'active', must_change_password: false, permissions: ['jobs.read', 'jobs.write', 'resumes.read', 'resumes.write', 'evaluations.read', 'evaluations.run', 'evaluations.review', 'evaluations.delete', 'schedules.read', 'schedules.write', 'actions.execute', 'history.read', 'users.manage'] }
export const test = base.extend({
  page: async ({ page }, use) => {
    const original = page.route.bind(page)
    await original('**/api/auth/me', route => route.fulfill({ json: adminIdentity }))
    // Preserve each legacy test's business API mocks without bypassing production guards.
    page.route = (url, handler, options) => original(url, (route, request) => new URL(request.url()).pathname === '/api/auth/me' ? route.fulfill({ json: adminIdentity }) : handler(route, request), options)
    await use(page)
  },
})
export { expect }
