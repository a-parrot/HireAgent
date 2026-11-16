<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Calendar, Refresh, Search } from '@element-plus/icons-vue'
import { bookInterviews, cancelInterview, listInterviews, rescheduleInterview } from '@/api/schedules'
import type { InterviewPage, InterviewRow } from '@/api/schedules'
import { formatScore } from '@/utils/format'
import { ApiError } from '@/api/http'
import ScheduleDetailView from './ScheduleDetailView.vue'

const props = defineProps<{ candidateId?: string }>()
const route = useRoute()
const candidateFilter = ref(props.candidateId || (typeof route.query.candidate_id === 'string' ? route.query.candidate_id : ''))

const data = ref<InterviewPage>({ items: [], total: 0, counts: { all: 0, pending: 0, scheduled: 0 } })
const query = reactive({ keyword: '', status: '', page: 1, page_size: 20 })
const loading = ref(false), error = ref(''), saving = ref(false), dialog = ref(false)
const selected = ref<InterviewRow[]>([]), targets = ref<InterviewRow[]>([])
const editing = ref<InterviewRow | null>(null)
const form = reactive({ start: '', end: '', interviewer: '', gap: 0 })
const advancedBatch = ref(''), advancedVisible = ref(false)
const advancedReservation = ref('')
let controller: AbortController | undefined
const asIso = (value: string) => `${value}:00+08:00`
function beijingInput(value: string) { return new Date(new Date(value).getTime() + 8 * 3600000).toISOString().slice(0, 16) }
function time(value: string) { return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) }
const duration = computed(() => (Date.parse(asIso(form.end)) - Date.parse(asIso(form.start))) / 60000)
const preview = computed(() => {
  if (!form.start || !form.end || !Number.isFinite(duration.value) || duration.value <= 0) return []
  const start = Date.parse(asIso(form.start))
  return targets.value.map((row, index) => {
    const at = start + index * (duration.value + (form.gap || 0)) * 60000
    return { name: row.candidate.name || row.candidate.original_filename, start: new Date(at).toISOString(), end: new Date(at + duration.value * 60000).toISOString() }
  })
})
async function load() {
  controller?.abort()
  const current = new AbortController(); controller = current
  loading.value = true
  try {
    const result = await listInterviews({ ...query, candidate_id: candidateFilter.value || undefined, keyword: query.keyword || undefined, status: query.status || undefined }, current.signal)
    if (current.signal.aborted) return
    data.value = result; selected.value = []; error.value = ''
    if (!result.items.length && query.page > 1) { query.page--; await load() }
  } catch (err) { if (!current.signal.aborted) error.value = err instanceof ApiError ? err.message : '无法加载面试安排' }
  finally { if (controller === current) loading.value = false }
}
function search() { query.page = 1; void load() }
function defaultEnd() {
  form.end = form.start ? beijingInput(new Date(Date.parse(asIso(form.start)) + 45 * 60000).toISOString()) : ''
}
function open(rows: InterviewRow[], edit = false) {
  targets.value = [...rows]; editing.value = edit ? rows[0]! : null
  const slot = editing.value?.slot
  form.start = slot ? beijingInput(slot.starts_at) : ''; form.end = slot ? beijingInput(slot.ends_at) : ''
  form.interviewer = slot?.interviewer || ''; form.gap = 0; dialog.value = true
}
async function submit() {
  if (!preview.value.length) { ElMessage.warning('请选择有效的开始和结束时间'); return }
  if (Date.parse(asIso(form.start)) <= Date.now()) { ElMessage.warning('请选择未来的面试时间'); return }
  saving.value = true
  try {
    const body = { starts_at: asIso(form.start), ends_at: asIso(form.end), timezone: 'Asia/Shanghai', interviewer: form.interviewer.trim() || null }
    if (editing.value?.reservation) {
      await rescheduleInterview(editing.value.reservation.id, { ...body, preview_version: editing.value.reservation.preview_version })
      ElMessage.success('面试时间已更新')
    } else {
      const result = await bookInterviews({ ...body, candidate_ids: targets.value.map(row => row.candidate.id), gap_minutes: form.gap || 0 })
      ElMessage.success(`已安排 ${result.scheduled} 人面试`)
    }
    dialog.value = false; await load()
  } catch (err) { ElMessage.error(err instanceof ApiError ? err.message : '保存失败，请刷新后重试') }
  finally { saving.value = false }
}
async function cancel(row: InterviewRow) {
  if (!row.reservation) return
  try { await ElMessageBox.confirm(`取消 ${row.candidate.name || row.candidate.original_filename} 的面试？取消后回到待排期，操作记录保留。`, '取消面试', { type: 'warning', confirmButtonText: '确认取消', cancelButtonText: '保留预约' }) } catch { return }
  saving.value = true
  try { await cancelInterview(row.reservation.id, row.reservation.preview_version); ElMessage.success('已取消面试'); await load() }
  catch (err) { ElMessage.error(err instanceof ApiError ? err.message : '取消失败') }
  finally { saving.value = false }
}
function advanced(row: InterviewRow) { advancedBatch.value = row.candidate.batch_id; advancedReservation.value = row.reservation?.id || ''; advancedVisible.value = true }
onMounted(load)
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <div>
    <header class="interview-heading"><div><h1>面试排期</h1><p>直接为已准入候选人安排时间，支持批量连续排期。所有时间均为北京时间。</p></div><el-button :icon="Refresh" :loading="loading" :disabled="saving" @click="load">刷新</el-button></header>
    <el-card shadow="never">
      <el-alert v-if="candidateFilter && !candidateId" title="当前只显示所选候选人的面试安排" type="info" :closable="false" style="margin-bottom: 12px"><el-button text type="primary" @click="candidateFilter = ''; search()">查看全部候选人</el-button></el-alert>
      <el-tabs v-model="query.status" @tab-change="search"><el-tab-pane :label="`全部 ${data.counts.all}`" name="" /><el-tab-pane :label="`待排期 ${data.counts.pending}`" name="pending" /><el-tab-pane :label="`已排期 ${data.counts.scheduled}`" name="scheduled" /></el-tabs>
      <div class="interview-toolbar"><el-input v-model="query.keyword" clearable :prefix-icon="Search" placeholder="搜索候选人或岗位" @keyup.enter="search" @clear="search" /><el-button @click="search">搜索</el-button><span class="spacer" /><span v-if="selected.length" class="muted">已选 {{ selected.length }} 人</span><el-button v-permission="'schedules.write'" type="primary" :icon="Calendar" :disabled="!selected.length || loading || saving || !!error" @click="open(selected)">批量排期</el-button></div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" style="margin-bottom: 12px" />
      <el-table :data="data.items" row-key="candidate.id" v-loading="loading" @selection-change="selected = $event">
        <el-table-column type="selection" width="44" :selectable="(row: InterviewRow) => !row.reservation" />
        <el-table-column label="候选人 / 岗位" min-width="230"><template #default="{ row }"><strong>{{ row.candidate.name || row.candidate.original_filename }}</strong><p class="row-caption">{{ row.job_name }}</p></template></el-table-column>
        <el-table-column label="评分" width="85"><template #default="{ row }">{{ formatScore(row.candidate.total_score) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.reservation ? 'success' : 'info'">{{ row.reservation ? '已排期' : '待排期' }}</el-tag></template></el-table-column>
        <el-table-column label="面试时间（北京时间）" min-width="255"><template #default="{ row }"><template v-if="row.slot"><div>{{ time(row.slot.starts_at) }}</div><div class="row-caption">至 {{ time(row.slot.ends_at) }} · {{ Math.round((Date.parse(row.slot.ends_at) - Date.parse(row.slot.starts_at)) / 60000) }} 分钟</div></template><span v-else class="muted">待设置</span></template></el-table-column>
        <el-table-column label="面试官" min-width="120"><template #default="{ row }">{{ row.slot?.interviewer || (row.slot ? '默认面试日历' : '—') }}</template></el-table-column>
        <el-table-column label="操作" width="245" fixed="right"><template #default="{ row }"><div class="interview-row-actions"><el-button v-permission="'schedules.write'" v-if="!row.reservation" type="primary" plain size="small" :disabled="saving || !!error" @click="open([row])">安排面试</el-button><template v-else><el-tooltip :disabled="row.editable" content="已有外部动作执行记录，请先核实会议与通知"><span><el-button v-permission="'schedules.write'" size="small" :disabled="!row.editable || saving || !!error" @click="open([row], true)">改期</el-button></span></el-tooltip><el-button v-permission="'schedules.write'" size="small" text type="danger" :disabled="!row.editable || saving || !!error" @click="cancel(row)">取消</el-button><el-button v-permission="'actions.execute'" size="small" text type="primary" @click="advanced(row)">会议与通知</el-button></template></div></template></el-table-column>
        <template #empty><el-empty :image-size="70" :description="error ? '暂时无法读取排期' : query.keyword ? '没有匹配的候选人' : query.status === 'scheduled' ? '暂无已安排的面试' : '暂无待安排的候选人，请先在评估管理完成审核'" /></template>
      </el-table>
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="data.total" layout="total, sizes, prev, pager, next" style="margin-top: 18px; justify-content: flex-end" @current-change="load" @size-change="search" />
    </el-card>
    <el-dialog v-model="dialog" :title="editing ? '调整面试时间' : targets.length > 1 ? '批量安排面试' : '安排面试'" width="min(650px, calc(100vw - 24px))" :close-on-click-modal="false" :before-close="(done: () => void) => { if (!saving) done() }" :close-on-press-escape="!saving" :show-close="!saving">
      <p class="booking-context">{{ targets.length === 1 ? targets[0]?.candidate.name || targets[0]?.candidate.original_filename : `已选择 ${targets.length} 人，按下方预览顺序依次安排` }}</p>
      <el-form label-position="top" :disabled="saving"><div class="time-fields"><el-form-item label="开始时间（北京时间）" required><el-date-picker v-model="form.start" type="datetime" value-format="YYYY-MM-DDTHH:mm" format="YYYY-MM-DD HH:mm" placeholder="选择开始时间" style="width: 100%" @change="defaultEnd" /></el-form-item><el-form-item :label="targets.length > 1 ? '首位候选人结束时间' : '结束时间'" required><el-date-picker v-model="form.end" type="datetime" value-format="YYYY-MM-DDTHH:mm" format="YYYY-MM-DD HH:mm" placeholder="默认开始后 45 分钟" style="width: 100%" /></el-form-item></div><div class="time-fields"><el-form-item label="面试官"><el-input v-model="form.interviewer" maxlength="200" placeholder="留空使用默认面试日历" /></el-form-item><el-form-item v-if="targets.length > 1" label="每场间隔（分钟）"><el-input-number v-model="form.gap" :min="0" :max="240" :precision="0" /></el-form-item></div></el-form>
      <p class="muted">默认每人 45 分钟，可调整结束时间。{{ targets.length > 1 ? '所有候选人使用相同时长，冲突时整批不保存。' : '' }}</p>
      <div v-if="preview.length" class="booking-preview"><strong>排期预览 · 每人 {{ duration }} 分钟</strong><div v-for="(item, index) in preview" :key="index" class="preview-row"><span>{{ index + 1 }}. {{ item.name }}</span><span>{{ time(item.start) }} — {{ time(item.end) }}</span></div></div>
      <template #footer><el-button :disabled="saving" @click="dialog = false">取消</el-button><el-button v-permission="'schedules.write'" type="primary" :loading="saving" :disabled="!preview.length" @click="submit">{{ editing ? '保存改期' : `确认安排 ${targets.length} 人` }}</el-button></template>
    </el-dialog>
    <el-drawer v-model="advancedVisible" title="会议与通知管理" size="min(1200px, 96vw)" destroy-on-close @closed="load"><ScheduleDetailView v-if="advancedBatch" :key="advancedReservation" :batch-id="advancedBatch" :reservation-id="advancedReservation" actions-only @changed="load" /></el-drawer>
  </div>
</template>

<style scoped>
.interview-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 20px; }.interview-heading h1 { margin: 6px 0 10px; font-size: 22px; }.interview-heading p,.row-caption { margin: 6px 0; font-size: 13px; color: var(--ha-text-muted); line-height: 1.6; }.interview-toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }.interview-toolbar .el-input { width: 280px; }.spacer { flex: 1; }.interview-row-actions { display: flex; align-items: center; gap: 6px; white-space: nowrap; }.interview-row-actions :deep(.el-button) { margin: 0; }.time-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }.booking-context { margin: 0 0 20px; font-weight: 600; }.booking-preview { max-height: 260px; overflow: auto; margin-top: 16px; padding: 14px; background: #f5f7fa; border-radius: 8px; }.preview-row { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 16px; padding: 10px 0; border-bottom: 1px solid var(--ha-border); font-size: 13px; line-height: 1.6; }.preview-row:last-child { border-bottom: 0; }@media(max-width:600px) { .time-fields { grid-template-columns: 1fr; gap: 0; }.interview-toolbar .el-input { width: 100%; }.interview-heading { align-items: flex-start; } }
</style>
