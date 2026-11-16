<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadUserFile, TableInstance } from 'element-plus'
import { Search, Refresh, RefreshRight, UploadFilled, FolderOpened, Document, Plus, View, Delete } from '@element-plus/icons-vue'
import { workspaceJobs, jobResumes, uploadResumes, resumeDetail, removeResume, retryImport, evaluateResumes } from '@/api/resumes'
import type { WorkspaceJob, Resume, ResumeDetail, ImportResult } from '@/api/resumes'
import { getJob } from '@/api/jobs'
import type { JobRuleVersion } from '@/api/types'
import { formatTime, formatScore, processingStatusLabels, processingStatusTypes, recommendationLabels } from '@/utils/format'
import { ApiError } from '@/api/http'
import { retryCandidate } from '@/api/batches'
import { newId } from '@/utils/jobRules'

const router = useRouter()
const route = useRoute()
const jobs = ref<WorkspaceJob[]>([])
const selectedJob = ref('')
const jobSearch = ref('')
const currentJob = computed(() => jobs.value.find(j => j.id === selectedJob.value))
const visibleJobs = computed(() => jobs.value.filter(j => j.name.includes(jobSearch.value)))
const rows = ref<Resume[]>([])
const total = ref(0)
const selectedRows = ref<Resume[]>([])
const tableRef = ref<TableInstance>()
const query = reactive({ page: 1, page_size: 20, keyword: '', status: '', evaluation_status: '' })
const loading = ref(false)
const loadError = ref('')
const jobError = ref('')
const importVisible = ref(false)
const files = ref<UploadUserFile[]>([])
const uploading = ref(false)
const importResult = ref<ImportResult | null>(null)
const detail = ref<ResumeDetail | null>(null)
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detailJob = ref('')
const evaluating = ref(false)
const evaluationVisible = ref(false)
const versions = ref<JobRuleVersion[]>([])
const versionId = ref('')
const evaluationRequestId = ref('')
const importVersionId = ref('')
const importRequestId = ref('')
const busyId = ref('')
const statusLabels: Record<string, string> = { pending: '等待解析', running: '解析中', completed: '解析完成', failed: '解析失败' }
const nodeLabels: Record<string, string> = { prepare_import: '校验原件 SHA-256', parse_pdf: '本地提取整份 PDF', normalize_content: '整理文本与来源索引', save_import_result: '保存解析结果' }
let timer: ReturnType<typeof setTimeout> | undefined
let requestSequence = 0
let disposed = false
let jobsLoading = false
let rowsController: AbortController | undefined

function showError(err: unknown) { ElMessage.error(err instanceof ApiError ? err.message : '操作失败，请稍后重试') }
async function loadJobs() {
  if (jobsLoading || disposed) return
  jobsLoading = true
  try {
    const result = await workspaceJobs()
    if (disposed) return
    jobs.value = result.items
    jobError.value = ''
    if (!selectedJob.value && jobs.value.length) { const preferred = jobs.value.find(j => j.id === route.query.job_id); await selectJob(preferred?.id || jobs.value[0]!.id) }
  } catch (err) { if (!disposed) jobError.value = err instanceof ApiError ? err.message : '无法读取岗位'; }
  finally { jobsLoading = false }
}
async function loadRows(silent = false) {
  if (!selectedJob.value || disposed || (silent && rowsController)) return
  rowsController?.abort()
  const controller = new AbortController()
  rowsController = controller
  const seq = ++requestSequence
  if (!silent) loading.value = true
  try {
    const result = await jobResumes(selectedJob.value, { ...query, keyword: query.keyword || undefined, status: query.status || undefined, evaluation_status: query.evaluation_status || undefined }, controller.signal)
    if (seq !== requestSequence || disposed) return
    if (JSON.stringify(rows.value) !== JSON.stringify(result.items)) {
      const selected = new Set(selectedRows.value.map(row => row.id))
      rows.value = result.items
      await nextTick()
      tableRef.value?.clearSelection()
      result.items.filter(row => selected.has(row.id) && canSelect(row)).forEach(row => tableRef.value?.toggleRowSelection(row, true))
    }
    total.value = result.total; loadError.value = ''
    if (!result.items.length && query.page > 1) { query.page--; await loadRows(false) }
  } catch (err) { if (!controller.signal.aborted && !disposed && seq === requestSequence) loadError.value = err instanceof ApiError ? err.message : '读取简历失败' }
  finally { if (seq === requestSequence) { loading.value = false; rowsController = undefined } }
}
async function selectJob(id: string) {
  selectedJob.value = id; selectedRows.value = []; rows.value = []; query.page = 1; query.keyword = ''; query.status = ''; query.evaluation_status = ''
  await loadRows()
}
async function refresh() { await Promise.all([loadJobs(), loadRows()]) }
async function openImport() {
  try {
    versions.value = (await getJob(selectedJob.value)).versions
    if (!versions.value.length) { ElMessage.warning('请先发布当前岗位的评分规则'); return }
    importVersionId.value = versions.value[0]!.id
    importRequestId.value = newId('import')
    files.value = []; importResult.value = null; importVisible.value = true
  } catch (err) { showError(err) }
}
function beforeImportClose(done: () => void) { if (!uploading.value) done() }
async function submitImport() {
  const raw = files.value.map(f => f.raw).filter(Boolean) as File[]
  if (!raw.length) { ElMessage.warning('请选择至少一份 PDF 简历'); return }
  uploading.value = true
  try {
    importResult.value = await uploadResumes(selectedJob.value, raw, { version: importVersionId.value, requestId: importRequestId.value })
    files.value = []
    importRequestId.value = newId('import')
    ElMessage.success(`接收 ${importResult.value.accepted} 份，重复 ${importResult.value.duplicates} 份，未接收 ${importResult.value.rejected} 份`)
    await refresh()
  } catch (err) { showError(err); await refresh() }
  finally { uploading.value = false }
}
async function openDetail(row: Resume) {
  detail.value = null; detailVisible.value = true; detailLoading.value = true; detailError.value = ''; detailJob.value = selectedJob.value
  try { detail.value = await resumeDetail(detailJob.value, row.id) }
  catch (err) { detailError.value = err instanceof ApiError ? err.message : '读取详情失败' }
  finally { detailLoading.value = false }
}
async function remove(row: Resume) {
  try { await ElMessageBox.confirm(`删除「${row.display_name}」？将同时删除「${currentJob.value?.name}」下该简历的所有关联评估，并取消关联面试预约、清理对应时段。原件、审计日志及其他岗位数据保留。已有会议或通知执行记录时会阻止删除。`, '删除简历及关联数据', { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }) } catch { return }
  busyId.value = row.id
  try { await removeResume(selectedJob.value, row.id); selectedRows.value = []; if (detail.value?.id === row.id) { detailVisible.value = false; detail.value = null }; ElMessage.success('已删除简历及关联评估、面试排期'); await refresh() }
  catch (err) { showError(err) } finally { busyId.value = '' }
}
async function retry(row: Resume) {
  if (row.parse_status === 'completed') {
    try { await ElMessageBox.confirm('将使用本地 PyMuPDF 重新提取原 PDF 正文，已有评估记录保留。', '重新解析简历', { confirmButtonText: '确认重新解析', cancelButtonText: '取消', type: 'warning' }) } catch { return }
  }
  busyId.value = row.id
  try { await retryImport(selectedJob.value, row.id); ElMessage.success('已提交重新解析'); await loadRows(); if (detail.value?.id === row.id) await openDetail(row) }
  catch (err) { showError(err) } finally { busyId.value = '' }
}
async function openEvaluation() {
  if (!selectedRows.value.length) { ElMessage.warning('请勾选需要处理的简历'); return }
  try {
    versions.value = (await getJob(selectedJob.value)).versions
    versionId.value = versions.value[0]?.id || ''; evaluationRequestId.value = newId('evaluation'); evaluationVisible.value = true
  } catch (err) { showError(err) }
}
async function createEvaluation() {
  if (!versionId.value) { ElMessage.warning('请先为该岗位发布评分规则'); return }
  evaluating.value = true
  try {
    await evaluateResumes(selectedJob.value, selectedRows.value.map(r => r.id), versionId.value, evaluationRequestId.value)
    evaluationVisible.value = false
    ElMessage.success('已开始评估，可在当前列表查看状态和结果')
    selectedRows.value = []
    tableRef.value?.clearSelection()
    await refresh()
  } catch (err) { showError(err) } finally { evaluating.value = false }
}
const evaluationNodes: Record<string, string> = { parse_pdf: '准备正文', screen_hard_conditions: '筛选硬条件', verify_hard_conditions: '复核硬条件', extract_scoring_evidence: '提取评分证据', verify_scoring_evidence: '复核评分证据', calculate_score: '计算得分', human_review: '等待人工审核', analyze_resume: '分析简历', evaluate_candidate: '岗位评分' }
function evaluationLabel(row: Resume) {
  const item = row.latest_evaluation
  if (!item) return '未评估'
  return item.processing_status === 'pending' && item.queued ? '排队中' : processingStatusLabels[item.processing_status]
}
function evaluationNode(row: Resume) {
  const item = row.latest_evaluation
  const label = item?.current_node ? evaluationNodes[item.current_node] || '处理中' : '准备评估'
  return item?.progress ? `${label} · 第 ${item.progress.current}/${item.progress.total} 段` : label
}
function showActive(kind: 'parse' | 'evaluation') {
  query.page = 1; query.status = kind === 'parse' ? 'running' : ''
  query.evaluation_status = kind === 'evaluation' ? 'running' : ''
  selectedRows.value = []; void loadRows()
}
function canSelect(row: Resume) {
  const evaluation = row.latest_evaluation
  return !(evaluation && (evaluation.processing_status === 'running' || (evaluation.processing_status === 'pending' && evaluation.queued)))
}
async function retryEvaluation(row: Resume) {
  if (!row.latest_evaluation) return
  busyId.value = row.id
  try { await retryCandidate(row.latest_evaluation.id); ElMessage.success('已提交评估重试'); await loadRows() }
  catch (err) { showError(err) } finally { busyId.value = '' }
}
async function poll() {
  try {
    if (!disposed && !document.hidden) {
      await Promise.all([loadRows(true), loadJobs()])
      if (detailVisible.value && detail.value && ['pending', 'running'].includes(detail.value.parse_status)) {
        const id = detail.value.id
        try { const next = await resumeDetail(detailJob.value, id); if (!disposed && detail.value?.id === id) detail.value = next } catch { /* Main list exposes transport errors. */ }
      }
    }
  } finally { if (!disposed) timer = setTimeout(poll, 5000) }
}
onMounted(async () => { await loadJobs(); if (!disposed) timer = setTimeout(poll, 5000) })
onBeforeUnmount(() => { disposed = true; rowsController?.abort(); if (timer) clearTimeout(timer) })
</script>

<template>
  <div class="resume-workspace">
    <div class="workspace-heading"><div><h1>简历评估</h1><p>选择岗位并导入 PDF，系统先检查硬条件，再提取原文并计分；审核和面试操作集中在评估管理。</p></div><el-button @click="router.push({ path: '/evaluations', query: { job_id: selectedJob || undefined } })">评估管理</el-button></div>
    <el-alert v-if="jobError" type="error" :title="jobError" :closable="false"><el-button text @click="loadJobs">重新加载岗位</el-button></el-alert>
    <div class="workspace-columns">
      <aside class="job-panel"><div class="panel-title"><strong>招聘岗位</strong><el-tag type="info" size="small">{{ jobs.length }}</el-tag></div><el-input v-model="jobSearch" :prefix-icon="Search" placeholder="查找岗位" clearable />
        <div class="job-options"><button v-for="job in visibleJobs" :key="job.id" class="job-option" :class="{ active: selectedJob === job.id }" :aria-pressed="selectedJob === job.id" @click="selectJob(job.id)"><el-icon><FolderOpened /></el-icon><span><strong>{{ job.name }}</strong><small>{{ job.resume_count }} 份简历 · 已解析 {{ job.parsed_count }} 份<span v-if="job.status === 'disabled'"> · 已停用</span></small></span></button></div>
        <el-empty v-if="!visibleJobs.length" :image-size="50" description="暂无匹配岗位"><el-button text type="primary" @click="router.push('/jobs')">管理岗位</el-button></el-empty>
      </aside>
      <el-card shadow="never" class="resume-panel">
        <template v-if="currentJob"><div class="panel-title"><div><h2>{{ currentJob.name }}</h2><span class="muted">已解析 {{ currentJob.parsed_count }} / {{ currentJob.resume_count }} 份 · 原件按 SHA-256 去重</span></div><el-button v-permission="'resumes.write'" type="primary" :icon="Plus" :disabled="currentJob.status !== 'active'" @click="openImport">导入简历</el-button></div>
          <div class="active-tasks"><span>按顺序逐份处理，队列会自动继续。</span><el-button :type="query.evaluation_status === 'running' ? 'primary' : 'default'" plain size="small" @click="showActive('evaluation')">查看正在评估</el-button><el-button :type="query.status === 'running' ? 'primary' : 'default'" plain size="small" @click="showActive('parse')">查看正在解析</el-button><el-button size="small" @click="query.status = ''; query.evaluation_status = ''; query.page = 1; loadRows()">全部简历</el-button></div>
          <div class="toolbar"><el-input v-model="query.keyword" placeholder="搜索简历文件名" clearable :prefix-icon="Search" class="resume-search" @keyup.enter="query.page = 1; loadRows()" @clear="query.page = 1; loadRows()" /><el-select v-model="query.status" placeholder="全部解析状态" clearable style="width: 150px" @change="query.page = 1; selectedRows = []; loadRows()"><el-option v-for="(label, value) in statusLabels" :key="value" :label="label" :value="value" /></el-select><el-select v-model="query.evaluation_status" aria-label="评估状态筛选" placeholder="全部评估状态" clearable style="width: 155px" @change="query.page = 1; selectedRows = []; loadRows()"><el-option label="正在评估" value="running" /><el-option label="排队中" value="queued" /><el-option label="待人工审核" value="waiting_review" /><el-option label="评估完成" value="completed" /><el-option label="评估失败" value="failed" /><el-option label="未评估" value="none" /></el-select><el-button @click="query.page = 1; loadRows()">搜索</el-button><div class="spacer" /><el-button :icon="Refresh" aria-label="刷新简历" @click="refresh" /><el-button v-permission="'evaluations.run'" type="primary" plain :disabled="!!loadError || !selectedRows.length || currentJob.status !== 'active'" @click="openEvaluation">开始评估{{ selectedRows.length ? `（${selectedRows.length}）` : '' }}</el-button></div>
          <div class="workspace-next"><span>{{ selectedRows.length ? `已选 ${selectedRows.length} 份简历，点击“开始评估”按当前岗位规则处理。` : '解析完成后仍需排队评估；“排队中”会自动处理，请勿重复提交。新文件可点击“导入简历”。' }}</span><el-button v-if="selectedRows.length" link @click="tableRef?.clearSelection()">取消选择</el-button><el-button link type="primary" @click="router.push({ path: '/evaluations', query: { job_id: selectedJob } })">处理评估结果 →</el-button></div>
          <el-alert v-if="loadError" :type="rows.length ? 'warning' : 'error'" :title="rows.length ? `列表刷新失败：${loadError}。当前显示上次成功加载的数据，评估状态可能不是最新。` : loadError" :closable="false" show-icon style="margin-bottom: 12px"><el-button text type="primary" @click="refresh">重试连接</el-button></el-alert>
          <el-table ref="tableRef" :data="rows" row-key="id" v-loading="loading" @selection-change="selectedRows = $event"><el-table-column type="selection" width="44" :selectable="canSelect" /><el-table-column label="简历" min-width="180"><template #default="{ row }"><el-link type="primary" :underline="false" @click="openDetail(row)">{{ row.display_name }}</el-link><div class="file-caption"><el-tag size="small" :type="row.parse_status === 'completed' ? 'success' : row.parse_status === 'failed' ? 'danger' : 'info'">{{ statusLabels[row.parse_status] }}</el-tag> {{ row.file_type.toUpperCase() }} · {{ (row.size_bytes / 1024).toFixed(1) }} KB <span v-if="row.page_count">· {{ row.page_count }} 页</span></div></template></el-table-column><el-table-column label="评估状态" width="110"><template #default="{ row }"><template v-if="row.latest_evaluation"><el-tag :type="processingStatusTypes[row.latest_evaluation.processing_status]">{{ evaluationLabel(row) }}</el-tag><div v-if="row.latest_evaluation.processing_status === 'running'" class="file-caption">{{ evaluationNode(row) }}</div><div v-else-if="row.latest_evaluation.processing_status === 'pending' && row.latest_evaluation.queued" class="file-caption">等待模型处理，无需重复提交</div></template><span v-else class="muted">未评估</span></template></el-table-column><el-table-column label="得分 / 结论" min-width="110"><template #default="{ row }"><span v-if="row.latest_evaluation">{{ formatScore(row.latest_evaluation.total_score) }}<span v-if="row.latest_evaluation.recommendation"> · {{ recommendationLabels[row.latest_evaluation.recommendation] }}</span></span><span v-else class="muted">—</span></template></el-table-column><el-table-column label="面试安排" width="140"><template #default="{ row }"><el-tag v-if="row.latest_evaluation?.schedule_status === 'scheduled'" type="success">已安排</el-tag><el-tooltip v-else-if="row.latest_evaluation?.schedule_status === 'waitlisted'" :content="row.latest_evaluation.waitlist_reason || '暂无可用时段'"><el-tag type="warning">候补</el-tag></el-tooltip><span v-else class="muted">—</span></template></el-table-column><el-table-column label="操作" width="196" fixed="right"><template #default="{ row }"><div class="row-actions"><el-tooltip content="查看详情"><el-button circle text type="primary" :icon="View" aria-label="查看详情" @click="openDetail(row)" /></el-tooltip><el-tooltip v-if="row.file_type === 'pdf' && (row.parse_status === 'failed' || row.parse_status === 'completed')" :content="row.parse_status === 'completed' ? '重新解析' : '重试解析'"><el-button v-permission="'resumes.write'" circle text :icon="RefreshRight" :loading="busyId === row.id" :aria-label="row.parse_status === 'completed' ? '重新解析' : '重试解析'" @click="retry(row)" /></el-tooltip><el-tooltip v-if="row.latest_evaluation" content="查看评估结果"><el-button circle text type="primary" :icon="Document" aria-label="查看评估结果" @click="router.push(`/candidates/${row.latest_evaluation.id}`)" /></el-tooltip><el-tooltip v-if="row.latest_evaluation?.processing_status === 'failed'" content="重试评估"><el-button v-permission="'evaluations.run'" circle text :icon="RefreshRight" :loading="busyId === row.id" aria-label="重试评估" @click="retryEvaluation(row)" /></el-tooltip><el-tooltip content="移除简历"><el-button v-permission="'resumes.write'" circle text type="danger" :icon="Delete" :disabled="busyId === row.id" aria-label="移除简历" @click="remove(row)" /></el-tooltip></div></template></el-table-column><template #empty><el-empty :image-size="65" :description="loadError ? '简历暂时无法加载' : query.evaluation_status === 'running' ? '当前没有正在评估的简历；可切换排队中查看等待任务' : query.status === 'running' ? '当前没有正在解析的简历' : query.keyword || query.status || query.evaluation_status ? '没有匹配的简历' : '该岗位还没有简历，支持单份或多份导入'" /></template></el-table>
          <el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="total" layout="total, sizes, prev, pager, next" style="margin-top: 20px; justify-content: flex-end" @current-change="selectedRows = []; loadRows()" @size-change="query.page = 1; selectedRows = []; loadRows()" />
        </template><el-empty v-else :image-size="85" description="选择一个岗位，查看已导入和已解析的简历" />
      </el-card>
    </div>
    <el-dialog v-model="importVisible" title="导入岗位简历" width="min(720px, calc(100vw - 24px))" :close-on-click-modal="false" :before-close="beforeImportClose">
      <el-alert type="info" :closable="false" :title="`导入到：${currentJob?.name || ''}。接收后自动完成解析和评分，并按结果分流。`" style="margin-bottom: 16px" />
      <el-form label-position="top"><el-form-item label="岗位评分规则"><el-select v-model="importVersionId" :disabled="uploading" style="width: 100%"><el-option v-for="v in versions" :key="v.id" :value="v.id" :label="`v${v.version_no} · ${v.published_by || '已发布规则'}`" /></el-select></el-form-item></el-form>
      <el-upload v-model:file-list="files" drag multiple :auto-upload="false" :disabled="uploading" accept=".pdf"><el-icon :size="32"><UploadFilled /></el-icon><p>拖入简历，或点击选择文件</p><p class="muted">支持单份及多文件批量导入，仅 PDF；SHA-256 自动校验并识别重复内容。</p></el-upload>
      <p class="muted">确认后，PDF 在本地提取全文，正文发送至模型评分。硬条件不合格直接不推荐；通过后按证据赋分。临界分数或硬条件信息不足的结果等待人工确认，达标者进入面试队列。</p>
      <div v-if="importResult" class="import-results" aria-live="polite"><strong>接收 {{ importResult.accepted }} · 重复 {{ importResult.duplicates }} · 未接收 {{ importResult.rejected }}</strong><div v-for="(item, i) in importResult.items" :key="i" class="import-item"><span>{{ item.filename }}</span><el-tag :type="item.result === 'rejected' ? 'danger' : item.result === 'duplicate' ? 'warning' : 'success'" size="small">{{ item.result === 'accepted' ? '已接收' : item.result === 'duplicate' ? '重复' : '未接收' }}</el-tag><small>{{ item.message }}</small></div></div>
      <template #footer><el-button :disabled="uploading" @click="importVisible = false">关闭</el-button><el-button v-permission="'resumes.write'" type="primary" :disabled="!files.length" :loading="uploading" @click="submitImport">{{ uploading ? '校验并上传中' : `导入并评估${files.length ? ` ${files.length} 份` : ''}简历` }}</el-button></template>
    </el-dialog>
    <el-dialog v-model="detailVisible" title="简历详情" width="min(1100px, calc(100vw - 24px))" top="4vh" destroy-on-close>
      <div v-loading="detailLoading" class="detail-body"><el-alert v-if="detailError" type="error" :title="detailError" :closable="false" />
        <template v-if="detail"><div class="panel-title"><h2>{{ detail.display_name }}</h2><el-tag :type="detail.sha256_verified ? 'success' : 'danger'">{{ detail.sha256_verified ? '原件 SHA-256 校验通过' : '原件缺失或 SHA-256 不一致' }}</el-tag></div><div class="hash-value">SHA-256：{{ detail.sha256 }}</div><p class="muted" v-if="detail.added_at">添加于 {{ formatTime(detail.added_at) }}</p>
          <el-alert v-if="detail.parse_error" type="error" :title="detail.parse_error" :closable="false" show-icon style="margin: 14px 0" />
          <div class="detail-actions"><el-tag>{{ statusLabels[detail.parse_status] }}</el-tag><span class="muted">{{ detail.parser_name || '尚未解析' }}</span><el-button v-permission="'resumes.write'" v-if="detail.parse_status === 'failed'" size="small" @click="retry(detail)">重新解析</el-button><el-button size="small" @click="router.push({ path: '/history', query: { file_id: detail.file_id } })">历史解析记录</el-button><a :href="`/api/files/${detail.file_id}`" target="_blank" rel="noopener">打开 / 下载原件</a></div>
          <div v-if="detail.import_task" class="node-progress"><span v-for="node in detail.import_task.node_progress" :key="node.name" :class="node.status"><el-icon><Document /></el-icon>{{ nodeLabels[node.name] || node.name }} · {{ node.status === 'completed' ? '完成' : node.status === 'failed' ? '失败' : '处理中' }}</span></div>
          <el-tabs><el-tab-pane label="解析文本"><div class="parsed-pages"><pre v-if="detail.markdown || detail.pages.length">{{ detail.markdown || detail.pages.map(part => part.text).join('\n\n') }}</pre><el-empty v-else :image-size="60" description="暂无解析正文，请等待解析完成或重试失败任务" /></div></el-tab-pane><el-tab-pane label="原件预览" lazy><iframe v-if="detail.file_type === 'pdf'" :src="`/api/files/${detail.file_id}/preview`" title="简历原件 PDF 预览" class="pdf-preview" /><el-empty v-else description="历史文件请通过原件下载查看" /></el-tab-pane><el-tab-pane label="评估记录"><el-table :data="detail.evaluations"><el-table-column label="评估时间"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column><el-table-column label="得分"><template #default="{ row }">{{ formatScore(row.total_score) }}</template></el-table-column><el-table-column label="状态"><template #default="{ row }">{{ processingStatusLabels[row.processing_status] }}</template></el-table-column><el-table-column label="操作"><template #default="{ row }"><el-button text type="primary" @click="router.push(`/candidates/${row.id}`)">查看评估详情</el-button></template></el-table-column></el-table><el-empty v-if="!detail.evaluations.length" description="尚未评估" :image-size="50" /></el-tab-pane></el-tabs>
        </template>
      </div>
    </el-dialog>
    <el-dialog v-model="evaluationVisible" title="开始简历评估" width="min(540px, calc(100vw - 24px))"><p>已选择 {{ selectedRows.length }} 份简历，自动解析未完成的文件，已解析文件直接复用正文。</p><el-form label-position="top"><el-form-item label="岗位评分规则"><el-select v-model="versionId" placeholder="选择已发布规则" style="width: 100%"><el-option v-for="v in versions" :key="v.id" :value="v.id" :label="`v${v.version_no} · ${v.published_by || '已发布规则'}`" /></el-select><el-link v-if="!versions.length" type="primary" @click="router.push(`/jobs/${selectedJob}`)">该岗位尚无发布版本，前往配置</el-link></el-form-item></el-form><p class="muted">确认后，未解析 PDF 将在本地提取全文，正文按所选规则发送至模型评估；先筛选硬条件，再逐项匹配原文计分；临界或信息不足转人工确认。</p><template #footer><el-button :disabled="evaluating" @click="evaluationVisible = false">取消</el-button><el-button v-permission="'evaluations.run'" type="primary" :disabled="!versionId" :loading="evaluating" @click="createEvaluation">确认开始</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.active-tasks { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 0 0 16px; }.active-tasks > span { color: var(--ha-text-muted); font-size: 12px; margin-right: auto; }

.row-actions { display: flex; align-items: center; flex-wrap: nowrap; gap: 4px; white-space: nowrap; }
.workspace-next { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 0 0 16px; padding: 12px; border-radius: 6px; background: #f5f8ff; font-size: 12px; color: var(--ha-text-secondary); }.workspace-next > span { flex: 1; min-width: 180px; }

.workspace-heading,.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }h1 { font-size: 22px; margin: 10px 0; }h2 { font-size: 17px; margin: 0 0 8px; }.workspace-heading p { font-size: 13px; color: var(--ha-text-muted); margin: 0; }.workspace-columns { display: grid; grid-template-columns: 220px minmax(0,1fr); gap: 16px; }.job-panel { background: white; border: 1px solid var(--ha-border); border-radius: var(--ha-radius); padding: 18px 12px; }.job-panel .panel-title { margin-bottom: 14px; padding: 0 4px; }.job-options { margin-top: 12px; max-height: 65vh; overflow: auto; }.job-option { display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 14px 12px; border: 0; border-radius: 6px; background: transparent; text-align: left; color: var(--ha-text-secondary); cursor: pointer; }.job-option.active { background: var(--el-color-primary-light-9); color: var(--ha-primary); }.job-option:hover { background: #f5f7fa; }.job-option strong { display: block; font-size: 14px; font-weight: 500; line-height: 1.6; }.job-option small { display: block; font-size: 12px; color: var(--ha-text-muted); margin-top: 6px; }.job-option .el-icon { margin-top: 4px; flex-shrink: 0; }.resume-panel { min-width: 0; }.resume-search { width: 220px; }.row-actions { display: flex; flex-wrap: wrap; gap: 0; }.row-actions :deep(.el-button) { margin-left: 0; padding-left: 6px; padding-right: 6px; }.file-caption { font-size: 12px; color: var(--ha-text-muted); margin-top: 6px; }.import-results { margin-top: 20px; max-height: 260px; overflow: auto; }.import-item { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 0; border-bottom: 1px solid var(--ha-border); }.import-item small { width: 100%; color: var(--ha-text-secondary); }.detail-body { min-height: 140px; max-height: 76vh; overflow: auto; }.hash-value { font-size: 12px; color: var(--ha-text-secondary); word-break: break-all; font-family: monospace; }.detail-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin: 16px 0; }.detail-actions a { color: var(--ha-primary); font-size: 13px; }.node-progress { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }.node-progress span { display: inline-flex; align-items: center; gap: 4px; background: #f5f7fa; padding: 6px 8px; font-size: 12px; border-radius: 4px; }.node-progress .completed { color: #389e0d; }.node-progress .failed { color: #f56c6c; }.parsed-pages pre { white-space: pre-wrap; overflow-wrap: anywhere; font-family: inherit; line-height: 1.8; font-size: 14px; }.parsed-pages section { padding: 14px; border: 1px solid var(--ha-border); margin-bottom: 12px; border-radius: 6px; }.parsed-pages h3 { font-size: 13px; color: var(--ha-text-muted); margin: 0 0 10px; }.pdf-preview { width: 100%; height: 58vh; border: 1px solid var(--ha-border); }@media(max-width:1000px) { .workspace-columns { grid-template-columns: 1fr; }.job-options { display: flex; max-height: 180px; }.job-option { min-width: 210px; }.job-panel { padding: 12px; } }@media(max-width:600px) { .workspace-heading { flex-wrap: wrap; }.resume-search { width: 100%; }.panel-title { flex-wrap: wrap; } }
</style>
