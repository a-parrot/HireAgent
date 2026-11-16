<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh, Search } from '@element-plus/icons-vue'
import { getImportHistory, listImportHistory, listEvaluationHistory } from '@/api/history'
import type { ImportHistory, ImportHistoryDetail, EvaluationHistory } from '@/api/history'
import { workspaceJobs } from '@/api/resumes'
import type { WorkspaceJob } from '@/api/resumes'
import { listBatchCandidates } from '@/api/batches'
import type { Candidate } from '@/api/types'
import { ApiError } from '@/api/http'
import { formatTime, formatScore, batchStatusLabels, processingStatusLabels } from '@/utils/format'
import BatchEventsView from './BatchEventsView.vue'

const route = useRoute()
const tab = ref('imports')
const jobs = ref<WorkspaceJob[]>([])
const query = reactive({ job_id: '', keyword: '', status: '', file_id: typeof route.query.file_id === 'string' ? route.query.file_id : '', page: 1, page_size: 20 })
const rows = ref<(ImportHistory | EvaluationHistory)[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const jobsError = ref('')
const parseVisible = ref(false)
const parseLoading = ref(false)
const parseError = ref('')
const parseDetail = ref<ImportHistoryDetail | null>(null)
const evaluationVisible = ref(false)
const evaluationDetail = ref<EvaluationHistory | null>(null)
const candidates = ref<Candidate[]>([])
const candidatesError = ref('')
const candidatesLoading = ref(false)
const evaluationTab = ref('events')
const parseLabels: Record<string, string> = { pending: '待解析', running: '解析中', completed: '解析成功', failed: '解析失败' }
const nodeStatusLabels: Record<string, string> = { pending: '待执行', running: '执行中', completed: '完成', failed: '失败' }
const nodeLabels: Record<string, string> = { prepare_import: '校验原件 SHA-256', parse_pdf: '本地提取 PDF 全文', save_import_result: '保存解析正文' }
const statusOptions = computed(() => tab.value === 'imports' ? parseLabels : { ...batchStatusLabels, failed: '包含失败记录' })
let controller: AbortController | undefined
let disposed = false
let detailSequence = 0
async function load() {
  controller?.abort()
  const current = new AbortController(); controller = current; loading.value = true
  try {
    const params = { ...query, job_id: query.job_id || undefined, file_id: tab.value === 'imports' ? query.file_id || undefined : undefined, keyword: query.keyword || undefined, status: query.status || undefined }
    const result = tab.value === 'imports' ? await listImportHistory(params, current.signal) : await listEvaluationHistory(params, current.signal)
    if (current.signal.aborted || disposed) return
    rows.value = result.items; total.value = result.total; error.value = ''
  } catch (err) { if (!current.signal.aborted && !disposed) error.value = err instanceof ApiError ? err.message : '历史记录读取失败' }
  finally { if (controller === current) { loading.value = false; controller = undefined } }
}
function search() { query.page = 1; void load() }
function switchTab() { query.status = ''; query.page = 1; rows.value = []; total.value = 0; error.value = ''; void load() }
function reset() { Object.assign(query, { job_id: '', keyword: '', status: '', file_id: '', page: 1 }); void load() }
async function openParse(row: ImportHistory) {
  const seq = ++detailSequence
  parseDetail.value = null; parseError.value = ''; parseVisible.value = true; parseLoading.value = true
  try { const detail = await getImportHistory(row.id); if (seq === detailSequence && !disposed) parseDetail.value = detail }
  catch (err) { if (seq === detailSequence && !disposed) parseError.value = err instanceof ApiError ? err.message : '解析记录读取失败' }
  finally { if (seq === detailSequence) parseLoading.value = false }
}
async function openEvaluation(row: EvaluationHistory) {
  evaluationDetail.value = row; evaluationTab.value = 'events'; evaluationVisible.value = true; candidates.value = []; candidatesError.value = ''; candidatesLoading.value = true
  try { const result = await listBatchCandidates(row.id); if (evaluationDetail.value?.id === row.id && !disposed) candidates.value = result }
  catch (err) { if (evaluationDetail.value?.id === row.id && !disposed) candidatesError.value = err instanceof ApiError ? err.message : '结果读取失败' }
  finally { if (evaluationDetail.value?.id === row.id) candidatesLoading.value = false }
}
async function loadJobs() {
  try { jobs.value = (await workspaceJobs()).items; jobsError.value = '' }
  catch (err) { jobsError.value = err instanceof ApiError ? err.message : '岗位读取失败' }
}
onMounted(() => { void loadJobs(); void load() })
onBeforeUnmount(() => { disposed = true; controller?.abort(); detailSequence++ })
</script>

<template>
  <div>
    <div class="history-heading"><div><h1>记录日志</h1><p>独立查看历史解析正文、任务节点和评估执行记录。</p></div><el-button :icon="Refresh" @click="load">刷新记录</el-button></div>
    <el-card shadow="never">
      <el-tabs v-model="tab" @tab-change="switchTab"><el-tab-pane label="解析记录" name="imports" /><el-tab-pane label="评估日志" name="evaluations" /></el-tabs>
      <el-alert v-if="jobsError" type="warning" :title="jobsError" :closable="false"><el-button text @click="loadJobs">重试加载岗位</el-button></el-alert>
      <div class="filters"><el-select v-model="query.job_id" filterable clearable placeholder="全部岗位" style="width: 250px" @change="search"><el-option v-for="job in jobs" :key="job.id" :label="job.name" :value="job.id" /></el-select><el-input v-model="query.keyword" :prefix-icon="Search" :placeholder="tab === 'imports' ? '搜索文件名或解析任务编号' : '搜索岗位或评估名称'" clearable style="width: 270px" @keyup.enter="search" @clear="search" /><el-select v-model="query.status" clearable placeholder="全部状态" style="width: 160px" @change="search"><el-option v-for="(label, value) in statusOptions" :key="value" :label="label" :value="value" /></el-select><el-button type="primary" @click="search">搜索</el-button><el-button @click="reset">重置</el-button><el-tag v-if="tab === 'imports' && query.file_id" closable @close="query.file_id = ''; search()">文件 {{ query.file_id }}</el-tag></div>
      <p class="hint">{{ tab === 'imports' ? '每次重新解析单独记录；新解析保存独立正文快照，旧记录缺少快照时只展示当时日志。' : '评估执行日志独立保存，包含历史成功、失败和人工处理事件；此页面仅供查询。' }}</p>
      <el-alert v-if="error" type="error" :title="error" :closable="false" style="margin-bottom: 12px" />
      <el-table v-if="tab === 'imports'" :data="rows" v-loading="loading" row-key="id">
        <el-table-column label="简历文件" prop="filename" min-width="240" show-overflow-tooltip /><el-table-column label="解析记录" width="120"><template #default="{ row }">#{{ row.id }}</template></el-table-column>
        <el-table-column label="解析状态" width="110"><template #default="{ row }"><el-tag :type="row.status === 'failed' ? 'danger' : row.status === 'completed' ? 'success' : 'info'">{{ parseLabels[row.status] }}</el-tag></template></el-table-column>
        <el-table-column label="正文快照" width="110"><template #default="{ row }">{{ row.has_snapshot ? '已保存' : '仅日志' }}</template></el-table-column><el-table-column label="开始时间" min-width="170"><template #default="{ row }">{{ formatTime(row.started_at || row.created_at) }}</template></el-table-column><el-table-column label="结束时间" min-width="170"><template #default="{ row }">{{ formatTime(row.finished_at) }}</template></el-table-column><el-table-column label="失败原因" prop="error_message" min-width="190" show-overflow-tooltip /><el-table-column label="操作" width="120" fixed="right"><template #default="{ row }"><el-button text type="primary" @click="openParse(row)">查看记录</el-button></template></el-table-column>
      </el-table>
      <el-table v-else :data="rows" v-loading="loading" row-key="id"><el-table-column label="评估名称" prop="name" min-width="240" show-overflow-tooltip /><el-table-column label="岗位" prop="job_name" min-width="180" show-overflow-tooltip /><el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="row.progress.failed ? 'warning' : row.status === 'evaluation_done' ? 'success' : 'info'">{{ batchStatusLabels[row.status] }}</el-tag></template></el-table-column><el-table-column label="简历 / 失败" width="120"><template #default="{ row }">{{ row.total }} / {{ row.progress.failed || 0 }}</template></el-table-column><el-table-column label="创建时间" min-width="170"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column><el-table-column label="结束时间" min-width="170"><template #default="{ row }">{{ formatTime(row.evaluation_completed_at) }}</template></el-table-column><el-table-column label="操作" width="120" fixed="right"><template #default="{ row }"><el-button text type="primary" @click="openEvaluation(row)">查看日志</el-button></template></el-table-column></el-table>
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="total" layout="total, sizes, prev, pager, next" style="margin-top: 18px; justify-content: flex-end" @current-change="load" @size-change="search" />
    </el-card>
    <el-drawer v-model="parseVisible" title="历史解析记录" size="min(1080px, 96vw)" destroy-on-close>
      <div v-loading="parseLoading"><el-alert v-if="parseError" type="error" :title="parseError" :closable="false" /><template v-if="parseDetail"><h2>{{ parseDetail.filename }}</h2><el-descriptions :column="2" border><el-descriptions-item label="任务编号">{{ parseDetail.task_id }}</el-descriptions-item><el-descriptions-item label="状态">{{ parseLabels[parseDetail.status] }}</el-descriptions-item><el-descriptions-item label="开始时间">{{ formatTime(parseDetail.started_at) }}</el-descriptions-item><el-descriptions-item label="结束时间">{{ formatTime(parseDetail.finished_at) }}</el-descriptions-item><el-descriptions-item v-if="parseDetail.artifact" label="解析器">{{ parseDetail.artifact.parser_name }} / {{ parseDetail.artifact.parser_version }}</el-descriptions-item><el-descriptions-item v-if="parseDetail.artifact" label="正文字数">{{ parseDetail.artifact.char_count }}</el-descriptions-item></el-descriptions>
      <el-alert v-if="parseDetail.error_message" type="error" :title="parseDetail.error_message" :closable="false" style="margin-top: 16px" />
      <h3>节点记录</h3><el-table :data="parseDetail.node_progress || []" size="small"><el-table-column label="节点" min-width="180"><template #default="{ row }">{{ nodeLabels[row.name] || row.name }}</template></el-table-column><el-table-column label="状态" width="100"><template #default="{ row }">{{ nodeStatusLabels[row.status] || row.status }}</template></el-table-column><el-table-column label="开始时间" min-width="170"><template #default="{ row }">{{ formatTime(row.started_at) }}</template></el-table-column><el-table-column label="结束时间" min-width="170"><template #default="{ row }">{{ formatTime(row.finished_at) }}</template></el-table-column><el-table-column label="错误" prop="error" min-width="180" /></el-table>
      <h3>本次解析正文</h3><el-alert v-if="parseDetail.artifact_error" type="info" :title="parseDetail.artifact_error" :closable="false" /><pre v-if="parseDetail.markdown !== null" class="snapshot">{{ parseDetail.markdown }}</pre></template></div>
    </el-drawer>
    <el-drawer v-model="evaluationVisible" title="历史评估日志" size="min(1280px, 96vw)" destroy-on-close>
      <template v-if="evaluationDetail"><h2>{{ evaluationDetail.job_name }}</h2><p class="hint">{{ evaluationDetail.name }} · 记录 #{{ evaluationDetail.id }}</p><el-tabs v-model="evaluationTab"><el-tab-pane label="执行日志" name="events"><BatchEventsView :key="evaluationDetail.id" :batch-id="evaluationDetail.id" /></el-tab-pane><el-tab-pane label="候选人结果" name="results"><el-alert v-if="candidatesError" type="error" :title="candidatesError" :closable="false" /><el-table :data="candidates" v-loading="candidatesLoading"><el-table-column label="候选人 / 简历" min-width="240"><template #default="{ row }">{{ row.name || row.original_filename }}</template></el-table-column><el-table-column label="得分" width="100"><template #default="{ row }">{{ formatScore(row.total_score) }}</template></el-table-column><el-table-column label="状态" width="140"><template #default="{ row }">{{ processingStatusLabels[row.processing_status] }}</template></el-table-column><el-table-column label="错误" prop="error_message" min-width="220" /></el-table></el-tab-pane></el-tabs></template>
    </el-drawer>
  </div>
</template>

<style scoped>
.history-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 20px; }h1 { font-size: 22px; margin: 8px 0; }h2 { font-size: 17px; margin: 0 0 18px; }.history-heading p,.hint { font-size: 13px; color: var(--ha-text-muted); line-height: 1.8; margin: 0; }.filters { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-top: 6px; }.hint { margin: 14px 0; }.snapshot { white-space: pre-wrap; overflow-wrap: anywhere; font-family: inherit; font-size: 14px; line-height: 1.8; background: #f6f8fb; padding: 18px; border-radius: 6px; }h3 { margin-top: 24px; font-size: 15px; }
</style>
