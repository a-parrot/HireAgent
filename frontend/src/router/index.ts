import { loadAuth, clearAuth, can, safeNext } from '@/stores/auth'
import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/forbidden', component: () => import('@/views/auth/ForbiddenView.vue'), meta: { title: '无权限' } },
    { path: '/login', component: () => import('@/views/auth/LoginView.vue'), meta: { title: '登录' } },
    { path: '/change-password', component: () => import('@/views/auth/PasswordView.vue'), meta: { title: '修改密码' } },
    {
      path: '/',
      component: MainLayout,
      redirect: '/jobs',
      children: [
        { path: 'users', component: () => import('@/views/auth/UsersView.vue'), meta: { title: '用户管理' } },
        { path: 'history', name: 'history', component: () => import('@/views/workflows/HistoryView.vue'), meta: { title: '记录日志' } },
        { path: 'evaluations', name: 'evaluation-management', component: () => import('@/views/reviews/EvaluationManagementView.vue'), meta: { title: '评估管理' } },
        { path: 'resumes', name: 'resume-workspace', component: () => import('@/views/resumes/ResumeWorkspaceView.vue'), meta: { title: '简历评估' } },
        {
          path: 'jobs',
          name: 'job-list',
          component: () => import('@/views/jobs/JobListView.vue'),
          meta: { title: '岗位管理' },
        },
        {
          path: 'jobs/:id',
          name: 'job-detail',
          component: () => import('@/views/jobs/JobDetailView.vue'),
          meta: { title: '岗位详情' },
        },
        { path: 'batches/:pathMatch(.*)*', redirect: '/resumes' },
        { path: 'batches', redirect: '/resumes' },
        {
          path: 'candidates/:id',
          name: 'candidate-detail',
          component: () => import('@/views/reviews/CandidateDetailView.vue'),
          meta: { title: '候选人详情' },
        },
        {
          path: 'schedules',
          name: 'schedule-list',
          component: () => import('@/views/schedules/InterviewWorkspaceView.vue'),
          meta: { title: '面试排期' },
        },
        {
          path: 'schedules/:batchId',
          name: 'schedule-detail',
          component: () => import('@/views/schedules/ScheduleDetailView.vue'),
          meta: { title: '排期详情' },
        },
        {
          path: 'events/:batchId',
          name: 'batch-events',
          component: () => import('@/views/workflows/BatchEventsView.vue'),
          meta: { title: '执行日志' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/jobs' },
  ],
})

router.beforeEach(async to => {
  if (to.path === '/login') return true
  try {
    const user = await loadAuth(true)
    if (!user) return { path: '/login', query: { next: safeNext(to.fullPath) } }
    if (user.must_change_password && to.path !== '/change-password') return '/change-password'
    const permission = to.path.startsWith('/users') ? 'users.manage' : to.path.startsWith('/jobs') ? 'jobs.read' : to.path.startsWith('/resumes') ? 'resumes.read' : to.path.startsWith('/schedules') ? 'schedules.read' : to.path.startsWith('/history') || to.path.startsWith('/events') ? 'history.read' : 'evaluations.read'
    if (to.path !== '/change-password' && to.path !== '/forbidden' && !can(permission)) return '/forbidden'
    return true
  } catch { clearAuth(); return { path: '/login', query: { error: '连接失败，请重试' } } }
})
window.addEventListener('auth-expired', () => { clearAuth(); if (router.currentRoute.value.path !== '/login') void router.replace({ path: '/login', query: { next: safeNext(router.currentRoute.value.fullPath) } }) })

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} - HireAgent` : 'HireAgent 招聘评估系统'
})

export default router
