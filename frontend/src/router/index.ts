import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      redirect: '/jobs',
      children: [
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
          component: () => import('@/views/schedules/ScheduleListView.vue'),
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

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} - HireAgent` : 'HireAgent 招聘评估系统'
})

export default router
