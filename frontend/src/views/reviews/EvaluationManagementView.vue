<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { TableInstance } from 'element-plus'
import { auth, can } from '@/stores/auth'
import { submitReview } from '@/api/reviews'
import { useRoute } from 'vue-router'
import { Refresh, Search } from '@element-plus/icons-vue'
import { listEvaluations, deleteEvaluations, autoScheduleEvaluations } from '@/api/evaluations'
import type { EvaluationRow, EvaluationResults } from '@/api/evaluations'
import { workspaceJobs } from '@/api/resumes'
import type { WorkspaceJob } from '@/api/resumes'
import type { CandidateDetail } from '@/api/types'
import { ApiError } from '@/api/http'
import { restoreCandidateReview } from '@/api/batches'
import { formatScore, formatTime, processingStatusLabels, recommendationLabels, reviewStatusLabels, scheduleStatusLabels } from '@/utils/format'
import CandidateDetailView from './CandidateDetailView.vue'
import InterviewWorkspaceView from '@/views/schedules/InterviewWorkspaceView.vue'

const route = useRoute()
const jobs = ref<WorkspaceJob[]>([])
const query = reactive({ job_id: typeof route.query.job_id === 'string' ? route.query.job_id : '', keyword: '', bucket: '', workflow: typeof route.query.workflow === 'string' && ['waiting_review', 'awaiting_schedule', 'scheduled', 'deferred'].includes(route.query.workflow) ? route.query.workflow : '', min_score: undefined as number | undefined, max_score: undefined as number | undefined, page: 1, page_size: 20 })
const history = ref(false)
const data = ref<EvaluationResults>({ items: [], total: 0, counts: {}, thresholds: [] })
const loading = ref(false)
const deleting = ref(false)
const restoring = ref('')
const approving = ref('')
const scheduling = ref(false)
const autoScheduleVisible = ref(false)
const scheduleTarget = ref<{ job_id?: string; candidate_ids?: string[] }>({})
const scheduleScope = ref('')
const scheduleForm = reactive({ startsAt: '', interviewer: '' })
const selectedRows = ref<EvaluationRow[]>([])
const tableRef = ref<TableInstance>()
const error = ref('')
const jobError = ref('')
const selected = ref<EvaluationRow | null>(null)
const detailVisible = ref(false)
const scheduleVisible = ref(false)
let controller: AbortController | undefined
let disposed = false
let timer: ReturnType<typeof setTimeout> | undefined
const bands = computed(() => {
  const line = data.value.thresholds.length === 1 ? data.value.thresholds[0] : null
  return [
    { key: '', title: '全部结果', caption: '已结束的评估记录', count: data.value.counts.all || 0 },
    { key: 'high', title: '高分简历', caption: line ? `≥ ${line.recommend} 分 · 推荐分数线` : '达到各自岗位推荐线', count: data.value.counts.high || 0 },
    { key: 'middle', title: '临界分数', caption: line ? `${line.review} ≤ 得分 < ${line.recommend}` : '复核线至推荐线之间', count: data.value.counts.middle || 0 },
    { key: 'low', title: '低分简历', caption: line ? `< ${line.review} 分 · 暂缓 / 不推荐` : '低于各自岗位复核线', count: data.value.counts.low || 0 },
    { key: 'unscored', title: '未评分', caption: '硬条件未通过、失败或未生成总分', count: data.value.counts.unscored || 0 },
  ]
})
async function load(background = false) {
  if (disposed || (background && (controller || deleting.value || scheduling.value || restoring.value || approving.value || detailVisible.value || scheduleVisible.value || selectedRows.value.length))) return
  controller?.abort()
  const current = new AbortController()
  controller = current
  if (!background) loading.value = true
  try {
    const result = await listEvaluations({ ...query, job_id: query.job_id || undefined, keyword: query.keyword || undefined, bucket: query.bucket || undefined, workflow: query.workflow || undefined, min_score: query.min_score ?? undefined, max_score: query.max_score ?? undefined, latest_only: !history.value }, current.signal)
    if (disposed || current.signal.aborted) return
    data.value = result; error.value = ''; selectedRows.value = []; tableRef.value?.clearSelection()
    const updated = result.items.find(row => row.id === selected.value?.id)
    if (updated) selected.value = updated
    if (!result.items.length && query.page > 1) { query.page = 1; await load() }
  } catch (err) { if (!disposed && !current.signal.aborted) error.value = err instanceof ApiError ? err.message : '评估结果读取失败' }
  finally { if (controller === current) { controller = undefined; loading.value = false } }
}
function search() { query.page = 1; void load() }
function resetFilters() { Object.assign(query, { job_id: '', keyword: '', bucket: '', workflow: '', min_score: undefined, max_score: undefined, page: 1 }); history.value = false; void load() }
function selectBand(key: string) { query.bucket = key; search() }
function openDetail(row: EvaluationRow) { selected.value = row; scheduleVisible.value = false; detailVisible.value = true }
function openSchedule(row: EvaluationRow) { selected.value = row; detailVisible.value = false; scheduleVisible.value = true }
function onCandidateChanged(candidate?: CandidateDetail) {
  if (candidate && selected.value?.id === candidate.id) selected.value = { ...selected.value, ...candidate }
  void load()
}
function canDelete(row: EvaluationRow) {
  return ['failed', 'completed', 'waiting_review'].includes(row.processing_status) && row.review_status !== 'approved' && row.schedule_status !== 'scheduled'
}
function unsatisfiedConditions(row: EvaluationRow) { return (row.hard_conditions || []).filter(c => c.result === 'unsatisfied' && c.blocking !== false) }
const workflowTabs = [
  { value: '', label: '全部结果' },
  { value: 'waiting_review', label: '待人工审核' },
  { value: 'awaiting_schedule', label: '待安排面试' },
  { value: 'scheduled', label: '已排期' },
  { value: 'deferred', label: '不推荐 / 暂缓' },
]
function isReview(row: EvaluationRow) { return row.processing_status === 'waiting_review' && row.review_status === 'pending' }
function isReviewed(row: EvaluationRow) { return !!row.manual_review && ['approved', 'deferred'].includes(row.review_status) }
function canRestore(row: EvaluationRow) { return row.processing_status === 'failed' && row.error_node === 'human_review' && row.review_status === 'pending' }
function nextLabel(row: EvaluationRow) {
  if (!can('evaluations.run') && !can('evaluations.review') && !can('schedules.write')) return '查看详情'
  if (canRestore(row)) return '恢复待审核'
  if (row.review_status === 'approved') return row.schedule_status === 'scheduled' ? '查看面试安排' : '排期管理'
  if (row.processing_status === 'failed') return '查看并重试'
  if (isReview(row)) return '人工审核'
  return row.recommendation === 'deferred' ? '查看依据' : '查看详情'
}
function nextAction(row: EvaluationRow) {
  if (nextLabel(row) === '查看详情') { openDetail(row); return }
  if (canRestore(row)) void restoreReview(row)
  else if (row.review_status === 'approved') openSchedule(row)
  else openDetail(row)
}
function executionLabel(row: EvaluationRow) { return row.processing_status === 'failed' ? '评估失败' : row.processing_status === 'waiting_review' ? '评分完成' : processingStatusLabels[row.processing_status] }
function reviewLabel(row: EvaluationRow) {
  if (isReview(row)) return '待人工审核'
  if (row.review_status === 'approved') return '已准入面试'
  if (row.processing_status === 'failed') return canRestore(row) ? '待恢复审核' : '尚未进入审核'
  return row.review_status === 'pending' ? '无需审核' : reviewStatusLabels[row.review_status]
}
async function quickApprove(row: EvaluationRow) {
  if (approving.value) return
  approving.value = row.id
  try {
    await submitReview(row.id, { operation: 'approve', review_version: row.review_version, reason: '', operator_name: auth.user?.display_name || '' })
    ElMessage.success('已批准面试，可使用已批准自动排期')
    await load()
  } catch (err) { ElMessage.error(err instanceof ApiError ? err.message : '批准失败，请刷新后重试') }
  finally { approving.value = '' }
}
async function restoreReview(row: EvaluationRow) {
  restoring.value = row.id
  try { await restoreCandidateReview(row.id); ElMessage.success('已提交缓存恢复，不重新调用模型；稍后刷新查看待审核状态'); await load() }
  catch (err) { ElMessage.error(err instanceof ApiError ? err.message : '恢复失败，请查看执行日志') }
  finally { restoring.value = '' }
}
async function removeRows(rows: EvaluationRow[]) {
  if (!rows.length) return
  try { await ElMessageBox.confirm(`确认删除选中的 ${rows.length} 条无效评估记录？记录将从评估列表移除，简历原件、解析历史和审计日志保留。`, '删除无效记录', { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }) } catch { return }
  deleting.value = true
  try {
    const result = await deleteEvaluations(rows.map(row => row.id))
    ElMessage.success(`已删除 ${result.deleted.length} 条记录`)
    await load()
  } catch (err) { ElMessage.error(err instanceof ApiError ? err.message : '删除失败，请刷新后重试') }
  finally { deleting.value = false }
}
function scheduleHighScores() {
  const picked = selectedRows.value.map(row => row.id)
  scheduleTarget.value = { job_id: query.job_id || undefined, candidate_ids: picked.length ? picked : undefined }
  scheduleScope.value = picked.length ? `所选 ${picked.length} 条记录` : query.job_id ? '当前岗位已批准面试的记录' : '全部在招岗位已批准面试的记录'
  scheduleForm.startsAt = ''; scheduleForm.interviewer = ''
  autoScheduleVisible.value = true
}
async function submitAutoSchedule() {
  if (!scheduleForm.startsAt) { ElMessage.warning('请选择面试起始时间'); return }
  const start = scheduleForm.startsAt.replace(' ', 'T') + ':00+08:00'
  if (new Date(start).getTime() <= Date.now()) { ElMessage.warning('请选择未来的面试起始时间'); return }
  scheduling.value = true
  try {
    const result = await autoScheduleEvaluations({ ...scheduleTarget.value, starts_at: start, timezone: 'Asia/Shanghai', interviewer: scheduleForm.interviewer.trim() || undefined })
    autoScheduleVisible.value = false
    if (!result.eligible) ElMessage.info('没有可排期记录；请先批准面试，可手动批准未通过或未评分的简历')
    else ElMessage.success(`符合条件 ${result.eligible} 人：已安排 ${result.scheduled} 人，新增 ${result.new_reservations ?? 0} 个预约`)
    await load()
  } catch (err) { ElMessage.error(err instanceof ApiError ? err.message : '自动排期失败，请稍后重试') }
  finally { scheduling.value = false }
}
async function loadJobs() {
  try { jobs.value = (await workspaceJobs()).items; jobError.value = '' }
  catch (err) { jobError.value = err instanceof ApiError ? err.message : '岗位列表读取失败' }
}
async function poll() {
  try { if (!document.hidden) await load(true) }
  finally { if (!disposed) timer = setTimeout(poll, 5000) }
}
onMounted(async () => { await Promise.all([loadJobs(), load()]); if (!disposed) timer = setTimeout(poll, 5000) })
onBeforeUnmount(() => { disposed = true; controller?.abort(); if (timer) clearTimeout(timer) })
</script>

<template>
  <div class="evaluation-management">
    <div class="heading"><div><h1>评估管理</h1><p>先处理待审核简历，再为已准入候选人安排面试。打开详情可核对评分与原文。</p></div><div class="header-actions"><el-button v-permission="'schedules.write'" type="primary" :loading="scheduling" :disabled="!!error || deleting || loading" @click="scheduleHighScores">已批准自动排期</el-button><el-button :icon="Refresh" @click="load()">刷新结果</el-button></div></div>
    <el-alert v-if="jobError" type="warning" :title="jobError" :closable="false"><el-button text @click="loadJobs">重试加载岗位</el-button></el-alert>
    <div class="score-bands"><button v-for="band in bands" :key="band.key" class="band" :class="[{ active: query.bucket === band.key }, band.key]" :aria-pressed="query.bucket === band.key" @click="selectBand(band.key)"><span>{{ band.title }}</span><strong>{{ band.count }}</strong><small>{{ band.caption }}</small></button></div>
    <el-card shadow="never" class="results-card">
      <el-tabs v-model="query.workflow" class="workflow-tabs" @tab-change="search" aria-label="处理阶段"><el-tab-pane v-for="tab in workflowTabs" :key="tab.value" :name="tab.value" :label="tab.label" /></el-tabs>
      <div class="filters">
        <el-select v-model="query.job_id" filterable clearable placeholder="全部岗位" aria-label="筛选岗位" style="width: 250px" @change="search"><el-option v-for="job in jobs" :key="job.id" :label="job.name" :value="job.id" /></el-select>
        <el-input v-model="query.keyword" :prefix-icon="Search" placeholder="搜索姓名或简历文件名" clearable style="width: 230px" @keyup.enter="search" @clear="search" />

        <el-input-number v-model="query.min_score" :min="0" :max="100" :controls="false" placeholder="最低分" aria-label="最低分" style="width: 110px" />
        <span class="muted">至</span><el-input-number v-model="query.max_score" :min="0" :max="100" :controls="false" placeholder="最高分" aria-label="最高分" style="width: 110px" /><el-button type="primary" @click="search">筛选</el-button><el-button @click="resetFilters">重置</el-button>
        <el-checkbox v-model="history" @change="search">包含历史评估</el-checkbox>
      </div>
      <div v-if="selectedRows.length" class="selection-actions"><el-button type="danger" plain :loading="deleting" :disabled="!!error || !selectedRows.length || selectedRows.some(row => !canDelete(row)) || scheduling || loading" @click="removeRows(selectedRows)">删除选中记录{{ selectedRows.length ? `（${selectedRows.length}）` : '' }}</el-button><span class="muted">{{ selectedRows.length ? `已选 ${selectedRows.length} 条。` : '勾选记录可批量排期或删除。' }}仅清理未准入、未预约的记录，原件与日志保留。</span></div><p class="hint">评分按岗位阈值分组，硬条件不合格直接不推荐；信息不足需人工核实。默认显示每份简历最新结果。</p>
      <el-alert v-if="error" type="error" :title="`结果刷新失败：${error}。当前数据可能不是最新。`" :closable="false" style="margin-bottom: 12px" />
      <el-table ref="tableRef" :data="data.items" v-loading="loading" row-key="id" @selection-change="selectedRows = $event"><el-table-column type="selection" width="44" />
        <el-table-column label="候选人 / 岗位" min-width="220"><template #default="{ row }"><el-link type="primary" :underline="false" @click="openDetail(row)">{{ row.name || row.original_filename }}</el-link><div class="row-job">{{ row.job_name }}</div><div v-if="row.name" class="muted file-name" :title="row.original_filename">{{ row.original_filename }}</div><div class="muted file-name">{{ formatTime(row.completed_at || row.created_at) }}</div></template></el-table-column>
        <el-table-column label="得分" width="80"><template #default="{ row }"><el-tooltip :content="`推荐线 ${row.recommend_threshold} 分 / 复核线 ${row.review_threshold} 分`"><div class="score-cell"><strong>{{ row.total_score == null ? '未评分' : formatScore(row.total_score) }}</strong><small v-if="row.total_score != null">/ 100 分</small></div></el-tooltip></template></el-table-column>
        <el-table-column label="结论与依据" min-width="210"><template #default="{ row }"><el-tag :type="isReviewed(row) ? 'success' : row.recommendation === 'recommended' ? 'success' : row.recommendation === 'needs_review' ? 'warning' : 'info'">{{ isReviewed(row) ? '已复核' : row.recommendation ? recommendationLabels[row.recommendation] : '尚无结论' }}</el-tag><div v-if="isReviewed(row)" class="row-reason">{{ row.manual_review?.operation === 'approve' ? '批准面试' : '暂缓' }} · {{ row.manual_review?.operator_name }}<br /><span v-if="row.manual_review?.reason">审核理由：{{ row.manual_review.reason }}</span></div><template v-else-if="row.recommendation === 'deferred' && row.total_score == null"><div v-for="condition in unsatisfiedConditions(row)" :key="condition.condition_id" class="row-reason">未满足：{{ condition.condition_name || condition.condition_id }}<br />{{ condition.reason }}</div></template><div v-else-if="row.processing_status === 'failed'" class="row-reason error-reason">{{ row.error_message || '处理出现异常，请查看详情后重试。' }}</div><div v-else-if="isReview(row)" class="row-reason">核对硬条件、评分依据及原文，再决定是否准入。</div><div v-else-if="row.recommendation === 'deferred'" class="row-reason">得分低于岗位复核线，可查看逐项评分依据。</div></template></el-table-column>
        <el-table-column label="处理进度" width="145"><template #default="{ row }"><div class="row-progress"><el-tag :type="row.processing_status === 'failed' ? 'danger' : 'success'" size="small">{{ executionLabel(row) }}</el-tag><span :class="{ 'review-pending': isReview(row) }">{{ reviewLabel(row) }}</span></div></template></el-table-column>
        <el-table-column label="面试安排" width="95"><template #default="{ row }"><el-tooltip :content="row.waitlist_reason || scheduleStatusLabels[row.schedule_status]"><el-tag :type="row.schedule_status === 'scheduled' ? 'success' : row.schedule_status === 'waitlisted' ? 'warning' : 'info'" size="small">{{ scheduleStatusLabels[row.schedule_status] }}</el-tag></el-tooltip></template></el-table-column>
        <el-table-column label="下一步操作" width="180" fixed="right"><template #default="{ row }"><div class="next-actions"><el-button v-permission="'evaluations.review'" v-if="row.review_status !== 'approved'" type="primary" size="small" :loading="approving === row.id" :disabled="!!approving || !!error || deleting || scheduling" @click="quickApprove(row)">一键批准</el-button><el-button :type="isReview(row) || canRestore(row) || row.review_status === 'approved' ? 'primary' : 'default'" :loading="restoring === row.id" :disabled="!!error || deleting || scheduling" size="small" @click="nextAction(row)">{{ nextLabel(row) }}</el-button><div class="secondary-actions"><el-button v-if="nextLabel(row) !== '查看详情' && nextLabel(row) !== '查看依据' && nextLabel(row) !== '查看并重试'" link type="primary" :disabled="!!error" @click="openDetail(row)">详情</el-button><el-button v-permission="'evaluations.delete'" v-if="canDelete(row)" link type="danger" :disabled="deleting || scheduling || !!error" @click="removeRows([row])">删除</el-button></div></div></template></el-table-column>
        <template #empty><el-empty :description="query.workflow === 'waiting_review' ? '当前没有待人工审核的简历' : query.workflow === 'awaiting_schedule' ? '当前没有待安排面试的候选人' : '暂无匹配的评估结果'" :image-size="70"><el-button @click="resetFilters">查看全部结果</el-button></el-empty></template>
      </el-table>
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="data.total" layout="total, sizes, prev, pager, next" style="margin-top: 18px; justify-content: flex-end" @current-change="load()" @size-change="search" />
    </el-card>
    <el-dialog v-model="autoScheduleVisible" title="已批准自动排期" width="min(600px, calc(100vw - 24px))" :close-on-click-modal="false" :close-on-press-escape="!scheduling" :show-close="!scheduling">
      <el-alert type="info" :closable="false" :title="`处理范围：${scheduleScope}。人工批准后均可排期，不受硬条件或评分限制；未评分排在有分数者之后；评分达标且证据完整的结果保留原有自动准入规则。`" />
      <el-form label-position="top" style="margin-top: 20px">
        <el-form-item label="面试起始时间（北京时间 UTC+8）" required><el-date-picker v-model="scheduleForm.startsAt" type="datetime" value-format="YYYY-MM-DD HH:mm" format="YYYY-MM-DD HH:mm" placeholder="选择面试起始时间" :disabled="scheduling" style="width: 100%" /></el-form-item>
        <el-form-item label="面试官"><el-input v-model="scheduleForm.interviewer" placeholder="填写面试官，留空使用默认面试日历" maxlength="128" :disabled="scheduling" /></el-form-item>
      </el-form>
      <p class="hint">从起始时间按高分顺序连续生成时段，每人 45 分钟。已有预约保持不变，遇面试官冲突自动顺延。尚未批准且仍需人工复核的记录跳过；人工批准后即使低于推荐线也可安排。会议与通知仍需单独授权。</p>
      <template #footer><el-button :disabled="scheduling" @click="autoScheduleVisible = false">取消</el-button><el-button v-permission="'schedules.write'" type="primary" :loading="scheduling" @click="submitAutoSchedule">开始自动排期</el-button></template>
    </el-dialog>
    <el-drawer v-model="detailVisible" title="简历详情与人工审核" size="min(1280px, 96vw)" destroy-on-close @closed="load()">
      <template v-if="selected"><p class="drawer-context">{{ selected.job_name }} · {{ selected.name || selected.original_filename }}</p><CandidateDetailView :key="selected.id" :candidate-id="selected.id" embedded @changed="onCandidateChanged" @schedule="selected && openSchedule(selected)" /></template>
      <template #footer><el-button @click="detailVisible = false">关闭</el-button><el-button v-if="selected?.review_status === 'approved'" type="primary" @click="openSchedule(selected)">管理面试排期</el-button></template>
    </el-drawer>
    <el-drawer v-model="scheduleVisible" title="面试排期管理" size="min(1280px, 96vw)" destroy-on-close @closed="load()">
      <template v-if="selected"><InterviewWorkspaceView :key="selected.id" :candidate-id="selected.id" /></template>
    </el-drawer>
  </div>
</template>

<style scoped>
.workflow-tabs :deep(.el-tabs__header) { margin-bottom: 12px; }.workflow-tabs :deep(.el-tabs__content) { display: none; }
.row-job { font-size: 13px; color: var(--ha-text-secondary); margin-top: 6px; line-height: 1.5; }.row-reason { margin-top: 8px; font-size: 12px; line-height: 1.7; color: var(--ha-text-secondary); overflow-wrap: anywhere; }.error-reason { color: #c45656; }.score-cell strong { display: block; font-size: 18px; }.score-cell small { font-size: 11px; color: var(--ha-text-muted); }.row-progress { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; font-size: 12px; }.next-actions { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; }.secondary-actions { display: flex; gap: 16px; }.file-name { overflow-wrap: anywhere; }.results-card :deep(.el-table__cell) { padding-top: 16px; padding-bottom: 16px; }.heading { flex-wrap: wrap; }

.header-actions { display: flex; gap: 12px; flex-wrap: wrap; }.selection-actions { display: flex; align-items: center; gap: 12px; margin-top: 14px; font-size: 12px; }.heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }h1 { font-size: 22px; margin: 4px 0; }.heading p,.hint { color: var(--ha-text-muted); font-size: 13px; line-height: 1.7; margin: 0; }.score-bands { display: grid; grid-template-columns: repeat(5,minmax(0,1fr)); gap: 14px; margin-bottom: 18px; }.band { background: white; border: 1px solid var(--ha-border); border-radius: 6px; padding: 12px 16px; text-align: left; cursor: pointer; color: var(--ha-text); }.band.active { border-color: var(--ha-primary); box-shadow: 0 0 0 1px var(--ha-primary); }.band strong { display: block; font-size: 24px; line-height: 1.5; }.band small { color: var(--ha-text-muted); font-size: 12px; }.band.high strong { color: #389e0d; }.band.middle strong { color: #d48806; }.band.low strong { color: #cf1322; }.filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }.hint { margin: 10px 0; }.file-name { font-size: 12px; margin-top: 6px; }.review-pending { color: #d48806; }.drawer-context { margin: 0 0 16px; font-size: 14px; color: var(--ha-text-secondary); }@media(max-width:1000px) { .score-bands { display: flex; overflow-x: auto; padding: 1px 1px 6px; }.band { flex: 0 0 160px; padding: 12px; }.band strong { font-size: 24px; line-height: 1.5; } }@media(max-width:600px) { .score-bands { grid-template-columns: repeat(2,minmax(0,1fr)); }.band { padding: 12px; } }
</style>
