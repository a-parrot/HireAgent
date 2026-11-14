<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import {
  approveActions,
  createSlot,
  deleteSlot,
  generateSchedule,
  getActionPreview,
  getSchedule,
  listSlots,
  patchSlot,
  putActionPreview,
  reconcileActions,
  retryActions,
} from '@/api/schedules'
import { getBatch, listCandidates } from '@/api/batches'
import { ApiError } from '@/api/http'
import { formatRange } from '@/utils/datetime'
import { formatTime } from '@/utils/format'
import {
  actionStatusLabels,
  actionStatusTypes,
  batchStatusLabels,
  batchStatusTypes,
  scheduleStatusLabels,
} from '@/utils/format'
import type { ActionPreviewResult, BatchDetail, Candidate, Slot } from '@/api/types'

const route = useRoute()
const batchId = route.params.batchId as string

const loading = ref(false)
const batch = ref<BatchDetail | null>(null)
const slots = ref<Slot[]>([])
const reservations = ref<Awaited<ReturnType<typeof getSchedule>>['reservations']>([])
const waitlist = ref<Candidate[]>([])
const candidateNames = ref<Record<string, string>>({})

/* 时段表单 */
const slotDialogVisible = ref(false)
const slotSubmitting = ref(false)
const editingSlotId = ref<string | null>(null)
const slotForm = reactive({
  range: [] as string[],
  interviewer: '',
})

/* 动作预览对话框 */
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewData = ref<ActionPreviewResult | null>(null)
const previewForm = reactive({ recipient: '', content: '' })
const previewDirty = ref(false)
const operatorName = ref('')
const previewSubmitting = ref(false)

const slotNameMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const s of slots.value) {
    map[s.id] = `${formatRange(s.starts_at, s.ends_at)}${s.interviewer ? `（${s.interviewer}）` : ''}`
  }
  return map
})

const canSchedule = computed(
  () => batch.value?.status === 'evaluation_done' && slots.value.length === 4,
)

async function loadAll() {
  loading.value = true
  try {
    const [batchData, slotData, scheduleData, candidateData] = await Promise.all([
      getBatch(batchId),
      listSlots(batchId).catch(() => [] as Slot[]),
      getSchedule(batchId).catch(() => ({ reservations: [], waitlist: [] })),
      listCandidates({ batch_id: batchId, page: 1, page_size: 1000 }),
    ])
    batch.value = batchData
    slots.value = slotData
    reservations.value = scheduleData.reservations
    waitlist.value = scheduleData.waitlist
    const names: Record<string, string> = {}
    for (const c of candidateData.items) {
      names[c.id] = c.name || c.original_filename
    }
    candidateNames.value = names
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)

/* 时段管理 */
function openAddSlot() {
  editingSlotId.value = null
  slotForm.range = []
  slotForm.interviewer = ''
  slotDialogVisible.value = true
}

function openEditSlot(slot: Slot) {
  editingSlotId.value = slot.id
  const start = new Date(slot.starts_at)
  const end = new Date(slot.ends_at)
  const pad = (n: number) => String(n).padStart(2, '0')
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
  slotForm.range = [fmt(start), fmt(end)]
  slotForm.interviewer = slot.interviewer ?? ''
  slotDialogVisible.value = true
}

async function submitSlot() {
  if (!slotForm.range || slotForm.range.length !== 2) {
    ElMessage.warning('请选择开始与结束时间')
    return
  }
  const startsAt = new Date(slotForm.range[0])
  const endsAt = new Date(slotForm.range[1])
  if (endsAt.getTime() - startsAt.getTime() !== 45 * 60 * 1000) {
    ElMessage.warning('每个时段固定 45 分钟')
    return
  }
  const pad = (n: number) => String(n).padStart(2, '0')
  const offsetMinutes = -startsAt.getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const abs = Math.abs(offsetMinutes)
  const offsetStr = `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  const iso = (d: Date) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:00${offsetStr}`
  const body = {
    starts_at: iso(startsAt),
    ends_at: iso(endsAt),
    timezone: 'Asia/Shanghai',
    interviewer: slotForm.interviewer.trim() || null,
  }
  slotSubmitting.value = true
  try {
    if (editingSlotId.value) {
      await patchSlot(editingSlotId.value, body)
      ElMessage.success('时段已更新')
    } else {
      await createSlot(batchId, body)
      ElMessage.success('时段已添加')
    }
    slotDialogVisible.value = false
    await loadAll()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    slotSubmitting.value = false
  }
}

async function removeSlot(slot: Slot) {
  try {
    await ElMessageBox.confirm(`确认删除时段 ${formatRange(slot.starts_at, slot.ends_at)}？`, '删除时段', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteSlot(slot.id)
    ElMessage.success('时段已删除')
    await loadAll()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  }
}

/* 统一排期 */
async function doSchedule() {
  try {
    await ElMessageBox.confirm(
      '将按岗位规则对有效批准者统一排序并分配时段，满额者进入候补。确认执行排期？',
      '统一排期',
      { type: 'info', confirmButtonText: '执行排期' },
    )
  } catch {
    return
  }
  try {
    const result = await generateSchedule(batchId)
    ElMessage.success(`排期完成：${result.reservations.length} 人已预约，${result.waitlist.length} 人候补`)
    await loadAll()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  }
}

/* 动作预览与审批 */
async function openPreview(reservationId: string) {
  previewVisible.value = true
  previewLoading.value = true
  previewData.value = null
  previewDirty.value = false
  try {
    const data = await getActionPreview(reservationId)
    previewData.value = data
    previewForm.recipient = data.reservation.action_preview?.recipient ?? ''
    previewForm.content = data.reservation.action_preview?.content ?? ''
  } catch (err) {
    if (err instanceof ApiError) {
      ElMessage.error(err.message)
      previewVisible.value = false
    }
  } finally {
    previewLoading.value = false
  }
}

async function savePreview() {
  if (!previewData.value) return
  const current = previewData.value.reservation.preview_version
  if (!previewForm.recipient.trim() || !previewForm.content.trim()) {
    ElMessage.warning('收件人与通知内容不能为空')
    return
  }
  previewSubmitting.value = true
  try {
    await putActionPreview(previewData.value.reservation.id, {
      preview_version: current,
      recipient: previewForm.recipient.trim(),
      content: previewForm.content.trim(),
    })
    ElMessage.success('预览已保存为新版本，旧授权已清除')
    previewDirty.value = false
    const data = await getActionPreview(previewData.value.reservation.id)
    previewData.value = data
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    previewSubmitting.value = false
  }
}

async function approve() {
  if (!previewData.value) return
  if (!operatorName.value.trim()) {
    ElMessage.warning('请填写操作人姓名')
    return
  }
  previewSubmitting.value = true
  try {
    const data = await approveActions(previewData.value.reservation.id, {
      preview_version: previewData.value.reservation.preview_version,
      operator_name: operatorName.value.trim(),
    })
    previewData.value = data
    ElMessage.success('动作已批准并执行当前快照（未配置的平台会返回 not_configured）')
    await loadAll()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    previewSubmitting.value = false
  }
}

async function retry() {
  if (!previewData.value) return
  previewSubmitting.value = true
  try {
    const data = await retryActions(previewData.value.reservation.id)
    previewData.value = data
    ElMessage.success('已重试未成功动作')
    await loadAll()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    previewSubmitting.value = false
  }
}

async function reconcile() {
  if (!previewData.value) return
  previewSubmitting.value = true
  try {
    const data = await reconcileActions(previewData.value.reservation.id)
    previewData.value = data
    ElMessage.success('已向平台核实动作状态')
    await loadAll()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    previewSubmitting.value = false
  }
}

function onPreviewInput() {
  previewDirty.value = true
}
</script>

<template>
  <div v-loading="loading">
    <el-card class="page-card">
      <template #header>
        <div class="toolbar" style="margin-bottom: 0">
          <span class="section-title" style="margin: 0">评估记录排期</span>
          <el-tag v-if="batch" :type="batchStatusTypes[batch.status]">
            {{ batchStatusLabels[batch.status] }}
          </el-tag>
          <div class="spacer" />
          <el-button :icon="Refresh" circle @click="loadAll" />
          <el-button type="primary" :disabled="!canSchedule" @click="doSchedule">统一排期</el-button>
        </div>
      </template>
      <el-descriptions v-if="batch" :column="3" border size="small">
        <el-descriptions-item label="评估记录 ID"><span class="mono">{{ batch.id }}</span></el-descriptions-item>
        <el-descriptions-item label="评估记录名称">{{ batch.name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="候选人总数">{{ batch.total }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="batch && batch.status !== 'evaluation_done'"
        type="info"
        :closable="false"
        show-icon
        title="评估记录评估尚未完成，评估完成后才能执行统一排期。"
        style="margin-top: 12px"
      />
    </el-card>

    <el-card class="page-card">
      <template #header>
        <div class="toolbar" style="margin-bottom: 0">
          <span class="section-title" style="margin: 0">面试时段（{{ slots.length }}/4，每个固定 45 分钟）</span>
          <div class="spacer" />
          <el-button
            v-if="slots.length < 4"
            size="small"
            type="primary"
            @click="openAddSlot"
          >添加时段</el-button>
        </div>
      </template>
      <el-table v-if="slots.length" :data="slots" border size="small">
        <el-table-column label="开始时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.starts_at) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.ends_at) }}</template>
        </el-table-column>
        <el-table-column label="时区" prop="timezone" width="140" />
        <el-table-column label="面试官" width="140">
          <template #default="{ row }">{{ row.interviewer ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEditSlot(row)">修改</el-button>
            <el-button size="small" link type="danger" @click="removeSlot(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <span v-else class="muted">尚未添加时段</span>
    </el-card>

    <el-card class="page-card">
      <template #header><span class="section-title" style="margin: 0">预约（{{ reservations.length }}）</span></template>
      <el-table v-if="reservations.length" :data="reservations" border size="small">
        <el-table-column label="候选人" min-width="150">
          <template #default="{ row }">{{ candidateNames[row.candidate_id] ?? row.candidate_id }}</template>
        </el-table-column>
        <el-table-column label="时段" min-width="220">
          <template #default="{ row }">{{ slotNameMap[row.slot_id] ?? row.slot_id }}</template>
        </el-table-column>
        <el-table-column label="预览版本" prop="preview_version" width="90" />
        <el-table-column label="已批准版本" width="100">
          <template #default="{ row }">{{ row.approved_preview_version ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="批准人" width="110">
          <template #default="{ row }">{{ row.approved_by ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="批准时间" width="160">
          <template #default="{ row }">{{ formatTime(row.approved_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="openPreview(row.id)">动作审批</el-button>
          </template>
        </el-table-column>
      </el-table>
      <span v-else class="muted">尚无预约记录，评估完成且配置 4 个时段后可执行统一排期。</span>
    </el-card>

    <el-card>
      <template #header><span class="section-title" style="margin: 0">候补（{{ waitlist.length }}）</span></template>
      <el-table v-if="waitlist.length" :data="waitlist" border size="small">
        <el-table-column label="候选人" min-width="150">
          <template #default="{ row }">{{ row.name || row.original_filename }}</template>
        </el-table-column>
        <el-table-column label="总分" width="100">
          <template #default="{ row }">{{ row.total_score ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="排期状态" width="110">
          <template #default="{ row }">{{ scheduleStatusLabels[row.schedule_status] }}</template>
        </el-table-column>
        <el-table-column label="候补原因" min-width="240">
          <template #default="{ row }">{{ row.waitlist_reason ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/candidates/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <span v-else class="muted">无候补候选人</span>
    </el-card>

    <!-- 时段编辑对话框 -->
    <el-dialog
      v-model="slotDialogVisible"
      :title="editingSlotId ? '修改时段' : '添加时段'"
      width="520px"
    >
      <el-form label-width="90px">
        <el-form-item label="时间段" required>
          <el-date-picker
            v-model="slotForm.range"
            type="datetimerange"
            value-format="YYYY-MM-DDTHH:mm"
            format="YYYY-MM-DD HH:mm"
            start-placeholder="开始时间"
            end-placeholder="结束时间（+45 分钟）"
            style="width: 100%"
          />
          <div class="muted" style="margin-top: 4px">结束时间须恰好晚于开始 45 分钟</div>
        </el-form-item>
        <el-form-item label="面试官">
          <el-input v-model="slotForm.interviewer" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="slotDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="slotSubmitting" @click="submitSlot">保存</el-button>
      </template>
    </el-dialog>

    <!-- 动作预览与审批对话框 -->
    <el-dialog v-model="previewVisible" title="预约动作预览与审批" width="820px" destroy-on-close>
      <div v-loading="previewLoading">
        <template v-if="previewData">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="候选人">
              {{ previewData.candidate_name ?? candidateNames[previewData.reservation.candidate_id] ?? '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="时段">
              {{ formatRange(previewData.slot.starts_at, previewData.slot.ends_at) }}
              {{ previewData.slot.interviewer ? `（${previewData.slot.interviewer}）` : '' }}
            </el-descriptions-item>
            <el-descriptions-item label="会议平台">
              <el-tag :type="previewData.meeting_configured ? 'success' : 'info'">
                {{ previewData.meeting_configured ? '已配置' : '未配置' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="通知平台">
              <el-tag :type="previewData.notification_configured ? 'success' : 'info'">
                {{ previewData.notification_configured ? '已配置' : '未配置' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <h4 style="margin: 16px 0 8px">通知内容预览（版本 {{ previewData.reservation.preview_version }}）</h4>
          <el-form label-width="80px">
            <el-form-item label="收件人">
              <el-input v-model="previewForm.recipient" maxlength="255" @input="onPreviewInput" />
            </el-form-item>
            <el-form-item label="内容">
              <el-input
                v-model="previewForm.content"
                type="textarea"
                :rows="6"
                maxlength="10000"
                @input="onPreviewInput"
              />
            </el-form-item>
          </el-form>
          <div class="muted" style="margin-bottom: 12px">
            保存新版本会清除旧的授权；批准后执行当前版本快照。
          </div>
          <el-button
            size="small"
            type="primary"
            :loading="previewSubmitting"
            :disabled="!previewDirty"
            @click="savePreview"
          >保存新版本</el-button>

          <h4 style="margin: 16px 0 8px">动作执行记录</h4>
          <el-table v-if="previewData.actions.length" :data="previewData.actions" border size="small">
            <el-table-column label="类型" width="100">
              <template #default="{ row }">{{ row.action_type === 'meeting' ? '创建会议' : '发送通知' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="actionStatusTypes[row.status]">{{ actionStatusLabels[row.status] }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="尝试" prop="attempt_count" width="70" />
            <el-table-column label="会议链接" min-width="180">
              <template #default="{ row }">
                <a v-if="row.meeting_url" :href="row.meeting_url" target="_blank" rel="noopener" class="mono">
                  {{ row.meeting_url }}
                </a>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column label="最后错误" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.last_error ?? '-' }}</template>
            </el-table-column>
          </el-table>
          <span v-else class="muted">暂无动作记录</span>

          <div class="toolbar" style="margin-top: 16px">
            <el-input
              v-model="operatorName"
              maxlength="128"
              placeholder="操作人姓名"
              style="width: 200px"
            />
            <el-button type="primary" :loading="previewSubmitting" @click="approve">
              批准并执行
            </el-button>
            <el-button :loading="previewSubmitting" @click="retry">重试未成功动作</el-button>
            <el-button :loading="previewSubmitting" @click="reconcile">向平台核实</el-button>
          </div>
          <div class="muted" style="margin-top: 6px">
            平台未配置时批准仍会执行并返回 not_configured，不创建真实会议或发送通知。
          </div>
        </template>
      </div>
    </el-dialog>
  </div>
</template>
