<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import JobFormDialog from '@/components/jobs/JobFormDialog.vue'
import { deleteJob, disableJob, enableJob, listJobs } from '@/api/jobs'
import { ApiError } from '@/api/http'
import { formatTime } from '@/utils/format'
import type { Job } from '@/api/types'
const router = useRouter()
const formDialogRef = ref<InstanceType<typeof JobFormDialog>>()
const loading = ref(false)
const failure = ref('')
const items = ref<Job[]>([])
const total = ref(0)
const query = reactive({ page: 1, pageSize: 10, keyword: '', status: '' })
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  failure.value = ''
  try {
    const data = await listJobs(query.page, query.pageSize, { keyword: query.keyword.trim() || undefined, status: query.status || undefined })
    if (id !== requestId) return
    items.value = data.items; total.value = data.total
    if (!data.items.length && query.page > 1) { query.page--; await load() }
  } catch (err) { if (id === requestId) failure.value = err instanceof Error ? err.message : '岗位加载失败，请重试' }
  finally { if (id === requestId) loading.value = false }
}
onMounted(load)
function search() { query.page = 1; load() }
function openJob(id: string, edit = false) { router.push({ path: `/jobs/${id}`, query: edit ? { edit: '1' } : {} }) }
function dimensionSummary(job: Job) {
  const dims = job.draft_rules?.dimensions
  if (!Array.isArray(dims) || !dims.length) return '尚未配置评分维度'
  return `${dims.length} 个维度 · 满分 ${dims.reduce((sum, d) => sum + Number(d.max_score || 0), 0)} 分`
}
async function changeStatus(job: Job) {
  const enabled = job.status === 'active'
  try { await ElMessageBox.confirm(enabled ? `停用「${job.name}」后，不再创建新批次，已有评估仍保留。` : `重新启用「${job.name}」？`, enabled ? '停用岗位' : '启用岗位', { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }) } catch { return }
  try { await (enabled ? disableJob(job.id) : enableJob(job.id)); ElMessage.success(enabled ? '岗位已停用' : '岗位已启用'); await load() } catch (err) { if (err instanceof ApiError) ElMessage.error(err.message) }
}
async function remove(job: Job) {
  try { await ElMessageBox.confirm(`删除「${job.name}」后，将从岗位列表移除且无法再创建新批次。已有规则版本和历史评估仍保留。`, '删除岗位', { confirmButtonText: '确认删除', cancelButtonText: '保留岗位', type: 'warning', confirmButtonClass: 'el-button--danger' }) } catch { return }
  try { await deleteJob(job.id); ElMessage.success('岗位已删除，历史评估已保留'); await load() } catch (err) { if (err instanceof ApiError) ElMessage.error(err.message) }
}
function onSaved(jobId: string) { openJob(jobId) }
</script>
<template>
  <div class="jobs-page">
    <section class="jobs-heading"><div><h1>岗位与评估标准</h1><p>为每个岗位定义要求、得分标准和筛选阈值，让每次评估都有据可依。</p></div><el-button type="primary" size="large" :icon="Plus" @click="formDialogRef?.open()">新建岗位</el-button></section>
    <el-card shadow="never" class="jobs-card">
      <div class="toolbar"><el-input v-model="query.keyword" placeholder="搜索岗位名称" clearable :prefix-icon="Search" style="width: 280px" @keyup.enter="search" @clear="search" /><el-select v-model="query.status" placeholder="全部状态" clearable style="width: 140px" @change="search"><el-option label="启用中" value="active" /><el-option label="已停用" value="disabled" /></el-select><el-button @click="search">搜索</el-button><div class="spacer" /><span class="muted">共 {{ total }} 个岗位</span><el-button :icon="Refresh" aria-label="刷新岗位" circle @click="load" /></div>
      <el-alert v-if="failure" :title="failure" type="error" :closable="false" show-icon style="margin-bottom: 16px"><el-button text @click="load">重新加载</el-button></el-alert>
      <el-table :data="items" v-loading="loading" row-key="id" style="width: 100%">
        <template #empty><el-empty :image-size="90" :description="failure ? '暂时无法读取岗位' : query.keyword || query.status ? '没有匹配的岗位，试试调整筛选条件' : '还没有岗位，创建第一个岗位和评分规则吧'"><el-button v-if="!failure && !query.keyword && !query.status" type="primary" @click="formDialogRef?.open()">新建岗位</el-button></el-empty></template>
        <el-table-column label="岗位" min-width="240"><template #default="{ row }"><div class="job-name"><el-link type="primary" :underline="false" @click="openJob(row.id)">{{ row.name }}</el-link><p>{{ row.responsibilities || '尚未填写岗位职责' }}</p></div></template></el-table-column>
        <el-table-column label="评分配置" min-width="170"><template #default="{ row }"><span>{{ dimensionSummary(row) }}</span><p class="score-caption">{{ row.draft_rules ? `推荐 ≥ ${row.draft_rules.recommend_threshold ?? '—'} 分 / 复核 ≥ ${row.draft_rules.review_threshold ?? '—'} 分` : '编辑岗位以设置标准' }}</p></template></el-table-column>
        <el-table-column label="已发布规则" width="130"><template #default="{ row }"><el-tag :type="row.latest_published_version ? 'success' : 'warning'" effect="plain">{{ row.latest_published_version ? `v${row.latest_published_version}` : '尚未发布' }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '启用中' : '已停用' }}</el-tag></template></el-table-column>
        <el-table-column label="最近更新" width="175"><template #default="{ row }">{{ formatTime(row.updated_at) }}</template></el-table-column>
        <el-table-column label="操作" width="230" fixed="right"><template #default="{ row }"><el-button text type="primary" @click="openJob(row.id, true)">编辑</el-button><el-button text @click="changeStatus(row)">{{ row.status === 'active' ? '停用' : '启用' }}</el-button><el-button text type="danger" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.pageSize" :total="total" layout="total, sizes, prev, pager, next" style="margin-top: 22px; justify-content: flex-end" @current-change="load" @size-change="search" />
    </el-card>
    <JobFormDialog ref="formDialogRef" @saved="onSaved" />
  </div>
</template>
<style scoped>
.jobs-page { max-width: 1400px; margin: 0 auto; }.jobs-heading { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 12px 0 26px; }.eyebrow { font-size: 11px; letter-spacing: 2px; color: var(--ha-text-muted); }h1 { margin: 9px 0; font-size: 22px; font-weight: 600; color: var(--ha-text); }.jobs-heading p { margin: 0; font-size: 13px; line-height: 1.8; color: var(--ha-text-muted); }.jobs-card { border-radius: var(--ha-radius); }.job-name { padding: 10px 0; }.job-name .el-link { font-weight: 600; font-size: 15px; }.job-name p { color: var(--ha-text-muted); font-size: 12px; margin: 7px 0 0; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }.score-caption { font-size: 12px; color: var(--ha-text-muted); margin: 7px 0 0; }@media (max-width: 650px) { .jobs-heading { flex-direction: column; align-items: flex-start; }h1 { font-size: 22px; } }
</style>
