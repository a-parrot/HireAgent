<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'

const route = useRoute()
const steps = [
  { path: '/jobs', title: '配置岗位', description: '设置硬条件与评分规则' },
  { path: '/resumes', title: '导入评估', description: '上传简历，自动筛选与计分' },
  { path: '/evaluations', title: '审核结果', description: '核对原文，处理待审核简历' },
  { path: '/schedules', title: '安排面试', description: '管理时间、面试官与预约' },
]
const current = computed(() => route.path.startsWith('/candidates') ? '/evaluations' : steps.find(step => route.path.startsWith(step.path))?.path)
const jobId = computed(() => typeof route.query.job_id === 'string' ? route.query.job_id : undefined)
</script>

<template>
  <nav v-if="current" class="recruitment-flow" aria-label="招聘操作流程">
    <RouterLink v-for="(step, index) in steps" :key="step.path" :to="{ path: step.path, query: step.path === '/resumes' || step.path === '/evaluations' ? { job_id: jobId } : {} }" class="flow-step" :class="{ current: step.path === current }" :aria-current="step.path === current ? 'step' : undefined">
      <span class="step-number">{{ index + 1 }}</span>
      <span class="step-copy"><strong>{{ step.title }}</strong><small>{{ step.description }}</small></span>
      <span v-if="index < steps.length - 1" class="step-arrow" aria-hidden="true">›</span>
    </RouterLink>
  </nav>
</template>

<style scoped>
.recruitment-flow { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); padding: 10px 12px; margin-bottom: 14px; background: white; border: 1px solid var(--ha-border); border-radius: 8px; }
.flow-step { position: relative; display: flex; align-items: center; gap: 10px; padding: 6px 14px; text-decoration: none; color: var(--ha-text-secondary); border-radius: 6px; }
.flow-step:hover { background: #f5f7fa; }
.flow-step:focus-visible { outline: 2px solid var(--ha-primary); outline-offset: 2px; }
.step-number { width: 28px; height: 28px; border: 1px solid var(--ha-border); border-radius: 50%; display: grid; place-items: center; flex-shrink: 0; font-weight: 600; font-size: 13px; }
.step-copy { min-width: 0; }.step-copy strong { display: block; font-size: 14px; }.step-copy small { display: block; color: var(--ha-text-muted); font-size: 12px; line-height: 1.5; margin-top: 3px; }
.current .step-number { background: var(--ha-primary); border-color: var(--ha-primary); color: white; }.current strong { color: var(--ha-primary); }
.step-arrow { margin-left: auto; padding-left: 6px; color: #b4bdcb; font-size: 24px; }
@media(max-width: 900px) { .step-copy small { display: none; }.flow-step { padding: 4px 8px; gap: 6px; } }
@media(max-width: 520px) { .recruitment-flow { padding: 8px; gap: 6px; grid-template-columns: repeat(2,minmax(0,1fr)); }.step-arrow { display: none; } }
</style>
