<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadUserFile, TableInstance } from 'element-plus'
import { Search, Refresh, UploadFilled, FolderOpened, Document, Plus } from '@element-plus/icons-vue'
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
const query = reactive({ page: 1, page_size: 20, keyword: '', status: '' })
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
const busyId = ref('')
const statusLabels: Record<string, string> = { pending: '等待解析', running: '解析中', completed: '解析完成', failed: '解析失败' }
const nodeLabels: Record<string, string> = { prepare_import: '校验原件 SHA-256', parse_pdf: '解析 PDF', parse_word: 'Word 转 PDF 并解析', normalize_content: '整理文本与来源索引', save_import_result: '保存解析结果' }
let timer: ReturnType<typeof setInterval> | undefined
let requestSequence = 0
let disposed = false

function showError(err: unknown) { ElMessage.error(err instanceof ApiError ? err.message : '操作失败，请稍后重试') }
async function loadJobs() {
  try {
    const result = await workspaceJobs()
    if (disposed) return
    jobs.value = result.items
    jobError.value = ''
    if (!selectedJob.value && jobs.value.length) { const preferred = jobs.value.find(j => j.id === route.query.job_id); await selectJob(preferred?.id || jobs.value[0]!.id) }
  } catch (err) { jobError.value = err instanceof ApiError ? err.message : '无法读取岗位'; }
}
async function loadRows(silent = false) {
  if (!selectedJob.value) return
  const seq = ++requestSequence
  if (!silent) loading.value = true
  try {
    const result = await jobResumes(selectedJob.value, { ...query, keyword: query.keyword || undefined, status: query.status || undefined })
    if (seq !== requestSequence || disposed) return
    if (JSON.stringify(rows.value) !== JSON.stringify(result.items)) {
      const selected = new Set(selectedRows.value.map(row => row.id))
      rows.value = result.items
      await nextTick()
      tableRef.value?.clearSelection()
      result.items.filter(row => selected.has(row.id) && canSelect(row)).forEach(row => tableRef.value?.toggleRowSelection(row, true))
    }
    total.value = result.total; loadError.value = ''
    if (!result.items.length && query.page > 1) { query.page--; await loadRows(silent) }
  } catch (err) { if (seq === requestSequence) loadError.value = err instanceof ApiError ? err.message : '读取简历失败' }
  finally { if (seq === requestSequence) loading.value = false }
}
async function selectJob(id: string) {
  selectedJob.value = id; selectedRows.value = []; rows.value = []; query.page = 1; query.keyword = ''; query.status = ''
  await loadRows()
}
async function refresh() { await Promise.all([loadJobs(), loadRows()]) }
function openImport() { files.value = []; importResult.value = null; importVisible.value = true }
function beforeImportClose(done: () => void) { if (!uploading.value) done() }
async function submitImport() {
  const raw = files.value.map(f => f.raw).filter(Boolean) as File[]
  if (!raw.length) { ElMessage.warning('请选择至少一份 PDF 或 DOCX 简历'); return }
  uploading.value = true
  try {
    importResult.value = await uploadResumes(selectedJob.value, raw)
    files.value = []
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
  try { await ElMessageBox.confirm(`从「${currentJob.value?.name}」移除「${row.display_name}」？历史评估、原件和其他岗位下的简历保留。`, '移除简历', { type: 'warning', confirmButtonText: '确认移除', cancelButtonText: '取消' }) } catch { return }
  busyId.value = row.id
  try { await removeResume(selectedJob.value, row.id); selectedRows.value = []; ElMessage.success('已移除简历'); await refresh() }
  catch (err) { showError(err) } finally { busyId.value = '' }
}
async function retry(row: Resume) {
  busyId.value = row.id
  try { await retryImport(selectedJob.value, row.id); ElMessage.success('已提交重新解析'); await loadRows(); if (detail.value?.id === row.id) await openDetail(row) }
  catch (err) { showError(err) } finally { busyId.value = '' }
}
async function openEvaluation() {
  if (!selectedRows.value.length) { ElMessage.warning('请勾选解析完成的简历'); return }
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
function canSelect(row: Resume) {
  const evaluation = row.latest_evaluation
  return row.parse_status === 'completed' && !(evaluation && (evaluation.processing_status === 'running' || (evaluation.processing_status === 'pending' && evaluation.queued)))
}
async function retryEvaluation(row: Resume) {
  if (!row.latest_evaluation) return
  busyId.value = row.id
  try { await retryCandidate(row.latest_evaluation.id); ElMessage.success('已提交评估重试'); await loadRows() }
  catch (err) { showError(err) } finally { busyId.value = '' }
}
onMounted(async () => {
  await loadJobs()
  timer = setInterval(async () => {
    if (disposed || document.hidden) return
    await Promise.all([loadRows(true), loadJobs()])
    if (detailVisible.value && detail.value && ['pending', 'running'].includes(detail.value.parse_status)) {
      const id = detail.value.id
      try { const next = await resumeDetail(detailJob.value, id); if (detail.value?.id === id) detail.value = next } catch { /* Main list exposes transport errors. */ }
    }
  }, 5000)
})
onBeforeUnmount(() => { disposed = true; if (timer) clearInterval(timer) })
</script>

<template>
  <div class="resume-workspace">
    <div class="workspace-heading"><div><h1>简历评估</h1><p>按岗位统一导入、解析和评估简历，直接查看得分与评估结果。</p></div></div>
    <el-alert v-if="jobError" type="error" :title="jobError" :closable="false"><el-button text @click="loadJobs">重新加载岗位</el-button></el-alert>
    <div class="workspace-columns">
      <aside class="job-panel"><div class="panel-title"><strong>招聘岗位</strong><el-tag type="info" size="small">{{ jobs.length }}</el-tag></div><el-input v-model="jobSearch" :prefix-icon="Search" placeholder="查找岗位" clearable />
        <div class="job-options"><button v-for="job in visibleJobs" :key="job.id" class="job-option" :class="{ active: selectedJob === job.id }" :aria-pressed="selectedJob === job.id" @click="selectJob(job.id)"><el-icon><FolderOpened /></el-icon><span><strong>{{ job.name }}</strong><small>{{ job.resume_count }} 份简历 · 已解析 {{ job.parsed_count }} 份<span v-if="job.status === 'disabled'"> · 已停用</span></small></span></button></div>
        <el-empty v-if="!visibleJobs.length" :image-size="50" description="暂无匹配岗位"><el-button text type="primary" @click="router.push('/jobs')">管理岗位</el-button></el-empty>
      </aside>
      <el-card shadow="never" class="resume-panel">
        <template v-if="currentJob"><div class="panel-title"><div><h2>{{ currentJob.name }}</h2><span class="muted">已解析 {{ currentJob.parsed_count }} / {{ currentJob.resume_count }} 份 · 原件按 SHA-256 去重</span></div><el-button type="primary" :icon="Plus" :disabled="currentJob.status !== 'active'" @click="openImport">导入简历</el-button></div>
          <div class="toolbar"><el-input v-model="query.keyword" placeholder="搜索简历文件名" clearable :prefix-icon="Search" class="resume-search" @keyup.enter="query.page = 1; loadRows()" @clear="query.page = 1; loadRows()" /><el-select v-model="query.status" placeholder="全部解析状态" clearable style="width: 150px" @change="query.page = 1; selectedRows = []; loadRows()"><el-option v-for="(label, value) in statusLabels" :key="value" :label="label" :value="value" /></el-select><el-button @click="query.page = 1; loadRows()">搜索</el-button><div class="spacer" /><el-button :icon="Refresh" aria-label="刷新简历" @click="refresh" /><el-button type="primary" plain :disabled="!selectedRows.length || currentJob.status !== 'active'" @click="openEvaluation">开始评估{{ selectedRows.length ? `（${selectedRows.length}）` : '' }}</el-button></div>
          <el-alert v-if="loadError" type="error" :title="loadError" :closable="false" style="margin-bottom: 12px" />
          <el-table ref="tableRef" :data="rows" row-key="id" v-loading="loading" @selection-change="selectedRows = $event"><el-table-column type="selection" width="44" :selectable="canSelect" /><el-table-column label="简历" min-width="180"><template #default="{ row }"><el-link type="primary" :underline="false" @click="openDetail(row)">{{ row.display_name }}</el-link><div class="file-caption"><el-tag size="small" :type="row.parse_status === 'completed' ? 'success' : row.parse_status === 'failed' ? 'danger' : 'info'">{{ statusLabels[row.parse_status] }}</el-tag> {{ row.file_type.toUpperCase() }} · {{ (row.size_bytes / 1024).toFixed(1) }} KB <span v-if="row.page_count">· {{ row.page_count }} 页</span></div></template></el-table-column><el-table-column label="评估状态" width="110"><template #default="{ row }"><el-tag v-if="row.latest_evaluation" :type="processingStatusTypes[row.latest_evaluation.processing_status]">{{ processingStatusLabels[row.latest_evaluation.processing_status] }}</el-tag><span v-else class="muted">未评估</span></template></el-table-column><el-table-column label="得分 / 结论" min-width="110"><template #default="{ row }"><span v-if="row.latest_evaluation">{{ formatScore(row.latest_evaluation.total_score) }}<span v-if="row.latest_evaluation.recommendation"> · {{ recommendationLabels[row.latest_evaluation.recommendation] }}</span></span><span v-else class="muted">—</span></template></el-table-column><el-table-column label="操作" width="230" fixed="right"><template #default="{ row }"><div class="row-actions"><el-button text type="primary" @click="openDetail(row)">详情</el-button><el-button v-if="row.parse_status === 'failed'" text :loading="busyId === row.id" @click="retry(row)">重试</el-button><el-button v-if="row.latest_evaluation" text type="primary" @click="router.push(`/candidates/${row.latest_evaluation.id}`)">评估结果</el-button><el-button v-if="row.latest_evaluation?.processing_status === 'failed'" text :loading="busyId === row.id" @click="retryEvaluation(row)">重试评估</el-button><el-button text type="danger" :disabled="busyId === row.id" @click="remove(row)">移除</el-button></div></template></el-table-column><template #empty><el-empty :image-size="65" :description="loadError ? '简历暂时无法加载' : query.keyword || query.status ? '没有匹配的简历' : '该岗位还没有简历，支持单份或多份导入'" /></template></el-table>
          <el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="total" layout="total, sizes, prev, pager, next" style="margin-top: 20px; justify-content: flex-end" @current-change="selectedRows = []; loadRows()" @size-change="query.page = 1; selectedRows = []; loadRows()" />
        </template><el-empty v-else :image-size="85" description="选择一个岗位，查看已导入和已解析的简历" />
      </el-card>
    </div>
    <el-dialog v-model="importVisible" title="导入岗位简历" width="min(720px, calc(100vw - 24px))" :close-on-click-modal="false" :before-close="beforeImportClose">
      <el-alert type="info" :closable="false" :title="`导入到：${currentJob?.name || ''}。接收后自动解析，不自动调用模型评估。`" style="margin-bottom: 16px" />
      <el-upload v-model:file-list="files" drag multiple :auto-upload="false" :disabled="uploading" accept=".pdf,.docx"><el-icon :size="32"><UploadFilled /></el-icon><p>拖入简历，或点击选择文件</p><p class="muted">支持单份及多文件批量导入，PDF / DOCX；SHA-256 自动校验并识别重复内容。</p></el-upload>
      <p class="muted">DOCX 需要服务器安装 LibreOffice；扫描 PDF 暂需转为可读取文本的 PDF。</p>
      <div v-if="importResult" class="import-results" aria-live="polite"><strong>接收 {{ importResult.accepted }} · 重复 {{ importResult.duplicates }} · 未接收 {{ importResult.rejected }}</strong><div v-for="(item, i) in importResult.items" :key="i" class="import-item"><span>{{ item.filename }}</span><el-tag :type="item.result === 'rejected' ? 'danger' : item.result === 'duplicate' ? 'warning' : 'success'" size="small">{{ item.result === 'accepted' ? '已接收' : item.result === 'duplicate' ? '重复' : '未接收' }}</el-tag><small>{{ item.message }}</small></div></div>
      <template #footer><el-button :disabled="uploading" @click="importVisible = false">关闭</el-button><el-button type="primary" :disabled="!files.length" :loading="uploading" @click="submitImport">{{ uploading ? '校验并上传中' : `导入${files.length ? ` ${files.length} 份` : ''}简历` }}</el-button></template>
    </el-dialog>
    <el-dialog v-model="detailVisible" title="简历详情" width="min(1100px, calc(100vw - 24px))" top="4vh" destroy-on-close>
      <div v-loading="detailLoading" class="detail-body"><el-alert v-if="detailError" type="error" :title="detailError" :closable="false" />
        <template v-if="detail"><div class="panel-title"><h2>{{ detail.display_name }}</h2><el-tag :type="detail.sha256_verified ? 'success' : 'danger'">{{ detail.sha256_verified ? '原件 SHA-256 校验通过' : '原件缺失或 SHA-256 不一致' }}</el-tag></div><div class="hash-value">SHA-256：{{ detail.sha256 }}</div><p class="muted" v-if="detail.added_at">添加于 {{ formatTime(detail.added_at) }}</p>
          <el-alert v-if="detail.parse_error" type="error" :title="detail.parse_error" :closable="false" show-icon style="margin: 14px 0" />
          <div class="detail-actions"><el-tag>{{ statusLabels[detail.parse_status] }}</el-tag><span class="muted">{{ detail.parser_name || '尚未解析' }}</span><el-button v-if="detail.parse_status === 'failed'" size="small" @click="retry(detail)">重新解析</el-button><a :href="`/api/files/${detail.file_id}`" target="_blank" rel="noopener">打开 / 下载原件</a></div>
          <div v-if="detail.import_task" class="node-progress"><span v-for="node in detail.import_task.node_progress" :key="node.name" :class="node.status"><el-icon><Document /></el-icon>{{ nodeLabels[node.name] || node.name }} · {{ node.status === 'completed' ? '完成' : node.status === 'failed' ? '失败' : '处理中' }}</span></div>
          <el-tabs><el-tab-pane label="解析文本"><div class="parsed-pages"><section v-for="page in detail.pages" :key="page.page_no"><h3>第 {{ page.page_no }} 页{{ detail.file_type === 'docx' ? '（转换后 PDF）' : '' }}</h3><pre>{{ page.text }}</pre></section><el-empty v-if="!detail.pages.length" :image-size="60" description="暂无解析文本，请等待解析完成或重试失败任务" /></div></el-tab-pane><el-tab-pane label="原件预览" lazy><iframe v-if="detail.file_type === 'pdf' || detail.parse_status === 'completed'" :src="`/api/files/${detail.file_id}/preview`" title="简历原件 PDF 预览" class="pdf-preview" /><el-empty v-else description="Word 转换完成后提供 PDF 预览" /></el-tab-pane><el-tab-pane label="评估记录"><el-table :data="detail.evaluations"><el-table-column label="评估时间"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column><el-table-column label="得分"><template #default="{ row }">{{ formatScore(row.total_score) }}</template></el-table-column><el-table-column label="状态"><template #default="{ row }">{{ processingStatusLabels[row.processing_status] }}</template></el-table-column><el-table-column label="操作"><template #default="{ row }"><el-button text type="primary" @click="router.push(`/candidates/${row.id}`)">查看评估详情</el-button></template></el-table-column></el-table><el-empty v-if="!detail.evaluations.length" description="尚未评估" :image-size="50" /></el-tab-pane></el-tabs>
        </template>
      </div>
    </el-dialog>
    <el-dialog v-model="evaluationVisible" title="开始简历评估" width="min(540px, calc(100vw - 24px))"><p>已选择 {{ selectedRows.length }} 份解析完成的简历，复用已有解析结果。</p><el-form label-position="top"><el-form-item label="岗位评分规则"><el-select v-model="versionId" placeholder="选择已发布规则" style="width: 100%"><el-option v-for="v in versions" :key="v.id" :value="v.id" :label="`v${v.version_no} · ${v.published_by || '已发布规则'}`" /></el-select><el-link v-if="!versions.length" type="primary" @click="router.push(`/jobs/${selectedJob}`)">该岗位尚无发布版本，前往配置</el-link></el-form-item></el-form><p class="muted">确认开始后，将按所选岗位规则向已配置模型发送简历内容进行评估，结果在当前列表查看。</p><template #footer><el-button :disabled="evaluating" @click="evaluationVisible = false">取消</el-button><el-button type="primary" :disabled="!versionId" :loading="evaluating" @click="createEvaluation">确认开始</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.workspace-heading,.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }h1 { font-size: 22px; margin: 10px 0; }h2 { font-size: 17px; margin: 0 0 8px; }.workspace-heading p { font-size: 13px; color: var(--ha-text-muted); margin: 0; }.workspace-columns { display: grid; grid-template-columns: 220px minmax(0,1fr); gap: 16px; }.job-panel { background: white; border: 1px solid var(--ha-border); border-radius: var(--ha-radius); padding: 18px 12px; }.job-panel .panel-title { margin-bottom: 14px; padding: 0 4px; }.job-options { margin-top: 12px; max-height: 65vh; overflow: auto; }.job-option { display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 14px 12px; border: 0; border-radius: 6px; background: transparent; text-align: left; color: var(--ha-text-secondary); cursor: pointer; }.job-option.active { background: var(--el-color-primary-light-9); color: var(--ha-primary); }.job-option:hover { background: #f5f7fa; }.job-option strong { display: block; font-size: 14px; font-weight: 500; line-height: 1.6; }.job-option small { display: block; font-size: 12px; color: var(--ha-text-muted); margin-top: 6px; }.job-option .el-icon { margin-top: 4px; flex-shrink: 0; }.resume-panel { min-width: 0; }.resume-search { width: 220px; }.row-actions { display: flex; flex-wrap: wrap; gap: 0; }.row-actions :deep(.el-button) { margin-left: 0; padding-left: 6px; padding-right: 6px; }.file-caption { font-size: 12px; color: var(--ha-text-muted); margin-top: 6px; }.import-results { margin-top: 20px; max-height: 260px; overflow: auto; }.import-item { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 0; border-bottom: 1px solid var(--ha-border); }.import-item small { width: 100%; color: var(--ha-text-secondary); }.detail-body { min-height: 140px; max-height: 76vh; overflow: auto; }.hash-value { font-size: 12px; color: var(--ha-text-secondary); word-break: break-all; font-family: monospace; }.detail-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin: 16px 0; }.detail-actions a { color: var(--ha-primary); font-size: 13px; }.node-progress { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }.node-progress span { display: inline-flex; align-items: center; gap: 4px; background: #f5f7fa; padding: 6px 8px; font-size: 12px; border-radius: 4px; }.node-progress .completed { color: #389e0d; }.node-progress .failed { color: #f56c6c; }.parsed-pages pre { white-space: pre-wrap; overflow-wrap: anywhere; font-family: inherit; line-height: 1.8; font-size: 14px; }.parsed-pages section { padding: 14px; border: 1px solid var(--ha-border); margin-bottom: 12px; border-radius: 6px; }.parsed-pages h3 { font-size: 13px; color: var(--ha-text-muted); margin: 0 0 10px; }.pdf-preview { width: 100%; height: 58vh; border: 1px solid var(--ha-border); }@media(max-width:1000px) { .workspace-columns { grid-template-columns: 1fr; }.job-options { display: flex; max-height: 180px; }.job-option { min-width: 210px; }.job-panel { padding: 12px; } }@media(max-width:600px) { .workspace-heading { flex-wrap: wrap; }.resume-search { width: 100%; }.panel-title { flex-wrap: wrap; } }
</style>
