<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { auth, can } from '@/stores/auth'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Back, View } from '@element-plus/icons-vue'
import { pdfUrl, retryCandidate } from '@/api/batches'
import { getCandidate, submitReview } from '@/api/reviews'
import { exportCandidate } from '@/api/workflows'
import { ApiError, http } from '@/api/http'
import {
  actionStatusLabels,
  actionStatusTypes,
  conditionResultLabels,
  conditionResultTypes,
  formatScore,
  formatTime,
  processingStatusLabels,
  recommendationLabels,
  recommendationTypes,
  reviewOperationLabels,
  scheduleStatusLabels,
} from '@/utils/format'
import type { CandidateDetail, RuleCondition, ConditionResult } from '@/api/types'

const props = defineProps<{ candidateId?: string; embedded?: boolean }>()
const emit = defineEmits<{ changed: [candidate?: CandidateDetail]; schedule: [batchId: string] }>()
const route = useRoute()
const router = useRouter()
const candidateId = props.candidateId || route.params.id as string

const loading = ref(false)
const candidate = ref<CandidateDetail | null>(null)
const loadError = ref('')

const pdfViewerVisible = ref(false)
const pdfViewerFileId = ref('')
const pdfViewerPage = ref(1)
const sourceVisible = ref(false)
const sourceText = ref('')
const sourceBefore = ref('')
const sourceAfter = ref('')
const sourceNotice = ref('')
const sourceLabel = ref('')
let sourceRequest = 0
const sourceLoading = ref(false)

/* 审核表单 */
const reviewDialogVisible = ref(false)
const reviewSubmitting = ref(false)
const reviewForm = reactive({
  operation: 'approve' as 'supplement' | 'approve' | 'defer',
  reason: '',
  operator_name: '',
  supplements: [] as { source: string; description: string }[],
})

async function load() {
  loading.value = true
  try {
    candidate.value = await getCandidate(candidateId)
    loadError.value = ''
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : '详情读取失败，请重试'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function viewEvidence(evidenceId: string) {
  const evidence = candidate.value?.evidence?.find(item => item.evidence_id === evidenceId)
  if (!evidence) { ElMessage.warning('未找到该证据'); return }
  const request = ++sourceRequest
  sourceVisible.value = true; sourceLoading.value = true
  sourceText.value = evidence.quote; sourceBefore.value = ''; sourceAfter.value = ''; sourceNotice.value = ''
  sourceLabel.value = evidence.page_no ? `原件第 ${evidence.page_no} 页` : '简历解析正文'
  try {
    const text: string = (await http.get(`/files/${evidence.file_id}/content`)).data.markdown || ''
    if (request !== sourceRequest) return
    // Match the same whitespace-insensitive quotations accepted by the backend,
    // while keeping original characters and offsets for safe text highlighting.
    const offsets: number[] = []
    let normalized = ''
    for (let index = 0; index < text.length; index++) {
      if (!/\s/.test(text[index]!)) { normalized += text[index]; offsets.push(index) }
    }
    const needle = evidence.quote.replace(/\s/g, '')
    const match = needle ? normalized.indexOf(needle) : -1
    if (match < 0) {
      sourceNotice.value = '当前解析正文中未定位到该片段，以下为评估时保存的原文证据。'
      return
    }
    const start = offsets[match]!
    const end = offsets[match + needle.length - 1]! + 1
    sourceBefore.value = (start > 160 ? '…' : '') + text.slice(Math.max(0, start - 160), start)
    sourceText.value = text.slice(start, end)
    sourceAfter.value = text.slice(end, end + 160) + (end + 160 < text.length ? '…' : '')
  } catch {
    if (request === sourceRequest) sourceNotice.value = '上下文读取失败，以下为评估时保存的原文证据。'
  } finally { if (request === sourceRequest) sourceLoading.value = false }
}

function viewPdf(fileId: string) {
  pdfViewerFileId.value = fileId
  pdfViewerPage.value = 1
  pdfViewerVisible.value = true
}

function openReview() {
  reviewForm.operation = 'approve'
  reviewForm.reason = ''
  reviewForm.operator_name = auth.user?.display_name || ''
  reviewForm.supplements = []
  reviewDialogVisible.value = true
}

async function quickApprove() {
  if (reviewSubmitting.value) return
  openReview()
  reviewDialogVisible.value = false
  await submitReviewForm()
}

function addSupplement() {
  reviewForm.supplements.push({ source: '', description: '' })
}

function removeSupplement(index: number) {
  reviewForm.supplements.splice(index, 1)
}

function validateReviewForm(): string | null {
  if (reviewForm.operation !== 'approve' && !reviewForm.reason.trim()) return '请填写审核理由'
  if (!reviewForm.operator_name.trim()) return '请填写审核人姓名'
  for (const s of reviewForm.supplements) {
    if (!s.description.trim()) return '补充说明内容不能为空'
    if (!s.source.trim()) return '补充说明来源不能为空'
  }
  return null
}

async function submitReviewForm() {
  if (!candidate.value) return
  const error = validateReviewForm()
  if (error) {
    ElMessage.warning(error)
    return
  }
  reviewSubmitting.value = true
  try {
    const review = await submitReview(candidateId, {
      operation: reviewForm.operation,
      review_version: candidate.value.review_version,
      reason: reviewForm.reason.trim(),
      operator_name: reviewForm.operator_name.trim(),
      supplements:
        reviewForm.operation === 'supplement' && reviewForm.supplements.length > 0
          ? reviewForm.supplements.map((s) => ({ description: s.description.trim(), source: s.source.trim() }))
          : null,
    })
    ElMessage.success(
      review.resume_status === 'pending'
        ? '审核决定已保存，恢复已排队（稍后刷新查看恢复结果）'
        : '审核决定已保存',
    )
    reviewDialogVisible.value = false
    await load()
    emit('changed', candidate.value || undefined)
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    reviewSubmitting.value = false
  }
}

async function retry() {
  try {
    await retryCandidate(candidateId)
    ElMessage.success('已提交重试，状态刷新中')
    await load()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  }
}

const canApprove = computed(() => can('evaluations.review') && !!candidate.value && !candidate.value.deleted && candidate.value.review_status !== 'approved')
const canReview = computed(() => can('evaluations.review') && !candidate.value?.deleted && candidate.value?.processing_status === 'waiting_review' && candidate.value?.review_status === 'pending')

function conditionName(id: string): string {
  function find(node?: RuleCondition): string | undefined {
    if (node?.id === id && node.description) return node.description
    return node?.items?.map(find).find(Boolean)
  }
  return candidate.value?.hard_conditions?.find(c => c.condition_id === id)?.condition_name
    || find(candidate.value?.rule_snapshot?.hard_conditions) || id
}
function dimension(id: string) { return candidate.value?.rule_snapshot?.dimensions?.find(d => d.id === id) }
type ConditionRow = ConditionResult & { children?: ConditionRow[] }
const conditionRows = computed<ConditionRow[]>(() => {
  const results = candidate.value?.hard_conditions || []
  const root = candidate.value?.rule_snapshot?.hard_conditions
  if (!root?.items) return results
  const seen = new Set<string>()
  function build(node: RuleCondition, path: string): ConditionRow {
    if (!node.items) {
      if (node.id) seen.add(node.id)
      return results.find(item => item.condition_id === node.id) || {
        condition_id: node.id || path, condition_name: node.description,
        result: 'unknown', reason: '尚无判定结果', evidence_ids: [],
      }
    }
    const children = node.items.map((child, index) => build(child, `${path}-${index}`))
    const values = children.map(child => child.result)
    const any = node.operator === 'any'
    const result = any
      ? values.includes('satisfied') ? 'satisfied' : values.includes('unknown') ? 'unknown' : 'unsatisfied'
      : values.includes('unsatisfied') ? 'unsatisfied' : values.includes('unknown') ? 'unknown' : 'satisfied'
    const decisive = children.filter(child => child.result === result)
    return {
      condition_id: `group-${path}`,
      condition_name: children.map(child => `（${child.condition_name || conditionName(child.condition_id)}）`).join(any ? ' 或 ' : ' 且 '),
      result,
      basis: decisive.length && decisive.every(child => child.basis === 'not_found') ? 'not_found' : undefined,
      reason: decisive.map(child => `${child.condition_name || conditionName(child.condition_id)}：${child.reason}`).join('；'),
      evidence_ids: [...new Set(decisive.flatMap(child => child.evidence_ids))],
      children,
    }
  }
  const tree = build(root, 'root')
  // One visible row per rule requirement, including an entire alternative group.
  const rows = root.operator === 'any' ? [tree] : tree.children || []
  return [...rows.map(({ children: _children, ...row }) => row), ...results.filter(item => !seen.has(item.condition_id))]
})
function quotes(ids: string[]) { return candidate.value?.evidence?.filter(e => ids.includes(e.evidence_id)) || [] }
const hardRejected = computed(() => candidate.value?.recommendation === 'deferred' && candidate.value?.total_score == null && candidate.value?.hard_conditions?.some(c => c.result === 'unsatisfied'))
const rejectionReason = computed(() => candidate.value?.hard_conditions?.filter(c => c.result === 'unsatisfied' && c.blocking !== false).map(c => `${conditionName(c.condition_id)}：${c.reason}`).join('；') || '')

const guidance = computed(() => {
  const c = candidate.value
  if (c?.deleted) return { title: '历史评估记录', text: '此记录已移除，仅供查看原有结果与日志。' }
  if (c?.review_status === 'approved') return { title: c.schedule_status === 'scheduled' ? '面试已安排' : '已准入面试 · 待安排时间', text: c.schedule_status === 'scheduled' ? '可在面试排期中查看预约时间与面试官。' : '前往排期管理设置时间；批量安排可返回评估管理使用“已批准自动排期”。' }
  if (c?.processing_status === 'failed') return { title: '需要处理异常', text: '已有结果保留。查看错误原因后重试，不需要重新上传简历。' }
  if (c?.processing_status === 'waiting_review' && c.review_status === 'pending') return { title: '等待人工确认', text: '先核对下方硬条件与原文，再检查逐项得分。确认后点击“人工审核”，批准面试、补充说明或暂缓。' }
  if (hardRejected.value) return { title: '不推荐 · 硬条件未通过', text: '已停止本轮评估。下方列出未满足的硬条件和原文依据，未执行匹配评分。' }
  if (c?.recommendation === 'deferred') return { title: '不推荐', text: '可查看每项得分及原文依据；原始评分和历史记录保留。' }
  return { title: '简历处理中', text: '硬条件筛选、评分证据提取和计分将依次完成，可稍后刷新查看结果。' }
})
function scrollToSection(section: string) { document.getElementById(`${section}-${candidateId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }

</script>

<template>
  <div v-loading="loading">
    <div class="toolbar review-toolbar">
      <el-button v-if="!embedded" :icon="Back" @click="router.push({ path: '/resumes', query: { job_id: candidate?.job_id } })">返回简历评估</el-button>
      <div class="spacer" />
      <el-button v-if="candidate" @click="router.push(`/events/${candidate.batch_id}`)">执行日志</el-button>
      <el-dropdown v-if="candidate" @command="(format: 'json' | 'csv') => exportCandidate(candidateId, format)"><el-button>导出结果</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="json">JSON</el-dropdown-item><el-dropdown-item command="csv">CSV</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
      <el-button v-permission="'evaluations.run'" v-if="candidate?.processing_status === 'failed' && !candidate.deleted" type="danger" plain @click="retry">
        重试
      </el-button>
      <el-button v-permission="'evaluations.review'" v-if="canApprove" type="primary" :loading="reviewSubmitting" @click="quickApprove">一键批准</el-button>
      <el-button v-permission="'evaluations.review'" v-if="canReview || canApprove" :disabled="reviewSubmitting" @click="openReview">人工审核</el-button>
    </div>

    <el-alert v-if="loadError" type="error" :title="loadError" :closable="false" style="margin-bottom: 16px"><el-button text @click="load">重新加载详情</el-button></el-alert>
    <template v-if="candidate">
      <el-alert v-if="candidate.deleted" type="info" title="该评估记录已删除，当前仅供历史查询。" :closable="false" style="margin-bottom: 16px" />
      <section class="candidate-summary" aria-label="审核概览">
        <div class="summary-main"><div><span class="summary-eyebrow">{{ guidance.title }}</span><h2>{{ candidate.name || candidate.original_filename }}</h2><p>{{ guidance.text }}</p></div><div class="summary-score"><strong>{{ candidate.total_score == null ? '未评分' : formatScore(candidate.total_score) }}</strong><span v-if="candidate.total_score != null">/ 100 分</span></div></div>
        <div class="summary-meta"><span>{{ candidate.original_filename }}</span><el-tag v-if="candidate.recommendation" :type="recommendationTypes[candidate.recommendation]">{{ recommendationLabels[candidate.recommendation] }}</el-tag><span>{{ processingStatusLabels[candidate.processing_status] }}</span><span>面试：{{ scheduleStatusLabels[candidate.schedule_status] }}</span><el-button size="small" :icon="View" @click="viewPdf(candidate.file_id)">PDF 原件</el-button></div>
        <el-alert v-if="candidate.error_message" :title="candidate.error_message" type="error" :closable="false" style="margin-top: 16px" />
      </section>
      <nav class="evidence-nav" aria-label="审核内容定位"><span>核对依据</span><el-button text @click="scrollToSection('conditions')">1. 硬条件</el-button><el-button text @click="scrollToSection('scores')">2. 匹配评分</el-button><el-button text @click="scrollToSection('review-records')">3. 审核记录</el-button></nav>
      <el-card :id="`conditions-${candidateId}`" class="page-card evidence-section">
        <template #header><span class="section-title" style="margin: 0">硬性条件</span></template>
        <el-alert v-if="hardRejected" title="硬条件未通过，不推荐；未进入评分" :description="rejectionReason" type="warning" :closable="false" style="margin-bottom: 14px" />
        <el-table
          v-if="candidate.hard_conditions && candidate.hard_conditions.length"
          :data="conditionRows"
          row-key="condition_id"
          border
          size="small"
        >
          <el-table-column label="硬条件内容" min-width="300"><template #default="{ row }">{{ row.condition_name || conditionName(row.condition_id) }}</template></el-table-column>
          <el-table-column label="判定" width="110">
            <template #default="{ row }">
              <el-tag :type="conditionResultTypes[row.result]">{{ conditionResultLabels[row.result] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="判定理由" min-width="300">
            <template #default="{ row }">{{ row.reason }}</template>
          </el-table-column>
          <el-table-column label="原文证据" width="200">
            <template #default="{ row }">
              <div class="evidence-actions">
              <span v-if="!quotes(row.evidence_ids).length" class="muted">{{ row.result === 'unsatisfied' && row.basis === 'not_found' ? '未匹配' : '暂无对应证据' }}</span>
              <el-button
                v-for="(e, index) in quotes(row.evidence_ids)"
                :key="e.evidence_id"
                size="small"
                plain
                :icon="View"
                type="primary"
                :aria-label="`${row.condition_name || conditionName(row.condition_id)}：查看证据 ${index + 1}`"
                @click="viewEvidence(e.evidence_id)"
              >证据 {{ index + 1 }}</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <span v-else class="muted">暂无硬性条件判定结果</span>
      </el-card>

      <el-card :id="`scores-${candidateId}`" class="page-card evidence-section">
        <template #header><span class="section-title" style="margin: 0">维度评分</span></template>
        <el-table v-if="candidate.dimension_scores && candidate.dimension_scores.length" :data="candidate.dimension_scores" row-key="dimension_id" border size="small">
          <el-table-column label="评分内容" min-width="300"><template #default="{ row }">{{ row.dimension_name || dimension(row.dimension_id)?.name || row.dimension_id }}</template></el-table-column>
          <el-table-column label="得分 / 满分" width="130"><template #default="{ row }"><span class="dim-score">{{ formatScore(row.score) }} / {{ row.max_score ?? dimension(row.dimension_id)?.max_score ?? 100 }} 分</span></template></el-table-column>
          <el-table-column label="评分理由" min-width="300"><template #default="{ row }">{{ row.reason }}</template></el-table-column>
          <el-table-column label="原文证据" width="200">
            <template #default="{ row }">
              <div class="evidence-actions">
              <span v-if="!quotes(row.evidence_ids).length" class="muted">{{ row.matched === false || Number(row.score) === 0 ? '未匹配' : '暂无对应证据' }}</span>
              <el-button
                v-for="(e, index) in quotes(row.evidence_ids)"
                :key="e.evidence_id"
                size="small"
                plain
                :icon="View"
                type="primary"
                :aria-label="`${row.dimension_name || dimension(row.dimension_id)?.name || row.dimension_id}：查看证据 ${index + 1}`"
                @click="viewEvidence(e.evidence_id)"
              >证据 {{ index + 1 }}</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <span v-else class="muted">{{ hardRejected ? '硬条件未通过，已跳过评分' : '暂无维度评分' }}</span>
      </el-card>

      <el-card class="page-card">
        <template #header><span class="section-title" style="margin: 0">缺失字段 · 风险 · 复核意见</span></template>
        <el-row :gutter="16">
          <el-col :span="8">
            <h4>缺失字段</h4>
            <template v-if="candidate.missing_fields && candidate.missing_fields.length">
              <el-tag v-for="f in candidate.missing_fields" :key="f" style="margin: 0 6px 6px 0" type="warning" effect="plain">
                {{ f }}
              </el-tag>
            </template>
            <span v-else class="muted">无</span>
          </el-col>
          <el-col :span="8">
            <h4>风险提示</h4>
            <template v-if="candidate.risks && candidate.risks.length">
              <el-tag v-for="r in candidate.risks" :key="r" style="margin: 0 6px 6px 0" type="danger" effect="plain">
                {{ r }}
              </el-tag>
            </template>
            <span v-else class="muted">无</span>
          </el-col>
          <el-col :span="8">
            <h4>复核意见</h4>
            <template v-if="candidate.review_notes && candidate.review_notes.length">
              <div v-for="n in candidate.review_notes" :key="n" class="note-item">{{ n }}</div>
            </template>
            <span v-else class="muted">无</span>
          </el-col>
        </el-row>
      </el-card>

      <el-card :id="`review-records-${candidateId}`" class="page-card evidence-section">
        <template #header><span class="section-title" style="margin: 0">审核历史</span></template>
        <el-table
          v-if="candidate.review_history.length"
          :data="candidate.review_history"
          border
          size="small"
        >
          <el-table-column label="操作" width="100">
            <template #default="{ row }">{{ reviewOperationLabels[row.operation] }}</template>
          </el-table-column>
          <el-table-column label="审核版本" prop="review_version" width="90" />
          <el-table-column label="理由" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.reason }}</template>
          </el-table-column>
          <el-table-column label="补充说明" min-width="220">
            <template #default="{ row }">
              <div v-for="(s, i) in row.supplements ?? []" :key="i" class="note-item">
                {{ s.description }}（来源：{{ s.source }}）
              </div>
              <span v-if="!row.supplements?.length" class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="审核人" prop="operator_name" width="120" />
          <el-table-column label="恢复状态" width="110">
            <template #default="{ row }">
              <el-tag
                :type="row.resume_status === 'succeeded' ? 'success' : row.resume_status === 'failed' ? 'danger' : row.resume_status === 'pending' ? 'warning' : 'info'"
              >{{ row.resume_status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
        <span v-else class="muted">暂无审核记录</span>
      </el-card>

      <el-card>
        <template #header><span class="section-title" style="margin: 0">排期与外部动作</span></template>
        <el-descriptions v-if="candidate.reservation" :column="3" border size="small">
          <el-descriptions-item label="预约 ID"><span class="mono">{{ candidate.reservation.id }}</span></el-descriptions-item>
          <el-descriptions-item label="时段 ID"><span class="mono">{{ candidate.reservation.slot_id }}</span></el-descriptions-item>
          <el-descriptions-item label="预览版本">{{ candidate.reservation.preview_version }}</el-descriptions-item>
          <el-descriptions-item label="已批准版本">
            {{ candidate.reservation.approved_preview_version ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="批准人">{{ candidate.reservation.approved_by ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="批准时间">{{ formatTime(candidate.reservation.approved_at) }}</el-descriptions-item>
        </el-descriptions>
        <span v-else class="muted">尚未排期</span>
        <div v-if="candidate.review_status === 'approved'" style="margin-top: 12px">
          <el-button size="small" type="primary" plain @click="embedded ? emit('schedule', candidate.batch_id) : router.push({ path: '/schedules', query: { candidate_id: candidate.id } })">
            前往排期管理
          </el-button>
        </div>
        <el-table v-if="candidate.actions.length" :data="candidate.actions" border size="small" style="margin-top: 12px">
          <el-table-column label="动作类型" width="110">
            <template #default="{ row }">{{ row.action_type === 'meeting' ? '创建会议' : '发送通知' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="actionStatusTypes[row.status]">{{ actionStatusLabels[row.status] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="尝试次数" prop="attempt_count" width="90" />
          <el-table-column label="外部 ID" width="150">
            <template #default="{ row }"><span class="mono">{{ row.external_id ?? '-' }}</span></template>
          </el-table-column>
          <el-table-column label="最后错误" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.last_error ?? '-' }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-collapse class="technical-details"><el-collapse-item title="查看处理信息与技术记录" name="technical"><el-descriptions :column="2" border size="small"><el-descriptions-item label="当前节点">{{ candidate.current_node || '-' }}</el-descriptions-item><el-descriptions-item label="重试次数">{{ candidate.retry_count }}</el-descriptions-item><el-descriptions-item label="模型">{{ candidate.model_id || '-' }}</el-descriptions-item><el-descriptions-item label="文件 ID">{{ candidate.file_id }}</el-descriptions-item><el-descriptions-item label="开始时间">{{ formatTime(candidate.started_at) }}</el-descriptions-item><el-descriptions-item label="完成时间">{{ formatTime(candidate.completed_at) }}</el-descriptions-item><el-descriptions-item label="提示词版本" :span="2"><span class="technical-version">{{ candidate.prompt_versions ? Object.entries(candidate.prompt_versions).map(([k, v]) => `${k}:${v}`).join(' / ') : '-' }}</span></el-descriptions-item></el-descriptions></el-collapse-item></el-collapse>

      <el-dialog v-model="pdfViewerVisible" title="简历原件" width="880px" destroy-on-close>
        <iframe
          v-if="pdfViewerFileId"
          :src="`${pdfUrl(pdfViewerFileId)}#page=${pdfViewerPage}`"
          style="width: 100%; height: 60vh; border: none"
        />
        <div class="muted">定位到第 {{ pdfViewerPage }} 页（如浏览器 PDF 插件不支持跳页，请手动翻页）</div>
      </el-dialog>

      <el-dialog v-model="reviewDialogVisible" title="人工审核决定" width="min(640px, calc(100vw - 24px))" :close-on-click-modal="false" :close-on-press-escape="!reviewSubmitting" :show-close="!reviewSubmitting">
        <div class="review-context"><strong>{{ candidate.name || candidate.original_filename }}</strong><span>{{ candidate.total_score == null ? '未评分' : `${formatScore(candidate.total_score)} / 100 分` }}</span></div>
        <el-form label-width="90px" :disabled="reviewSubmitting">
          <el-form-item label="操作类型">
            <el-radio-group v-model="reviewForm.operation">
              <el-radio-button value="supplement" :disabled="!canReview">补充说明</el-radio-button>
              <el-radio-button value="approve">批准面试</el-radio-button>
              <el-radio-button value="defer" :disabled="!canReview">暂缓</el-radio-button>
            </el-radio-group>
            <div class="muted" style="margin-top: 4px">
              可手动批准未通过或未评分的简历，原评估结果保留。批准后可直接安排面试；补充说明不会自动批准。
            </div>
          </el-form-item>
          <el-form-item label="理由" :required="reviewForm.operation !== 'approve'">
            <el-select v-if="reviewForm.operation === 'approve'" v-model="reviewForm.reason" clearable filterable allow-create default-first-option placeholder="选择或输入理由（选填，可直接批准）" style="width: 100%"><el-option v-for="reason in ['符合岗位要求', '已核对简历与评分依据', '经验符合，建议面试确认']" :key="reason" :label="reason" :value="reason" /></el-select>
            <el-input v-else v-model="reviewForm.reason" type="textarea" :rows="3" placeholder="说明审核依据，如：已核对项目经历与证据" />
          </el-form-item>
          <el-form-item v-if="reviewForm.operation === 'supplement'" label="补充说明">
            <div class="supplement-list">
              <div v-for="(s, i) in reviewForm.supplements" :key="i" class="supplement-row">
                <el-input v-model="s.description" placeholder="补充内容" style="flex: 2" />
                <el-input v-model="s.source" placeholder="来源（如：人工面谈记录）" style="flex: 1" />
                <el-button type="danger" plain @click="removeSupplement(i)">删除</el-button>
              </div>
              <el-button @click="addSupplement">添加补充</el-button>
            </div>
          </el-form-item>
          <el-form-item label="审核人" required>
            <el-input v-model="reviewForm.operator_name" disabled maxlength="128" placeholder="招聘人员姓名" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button :disabled="reviewSubmitting" @click="reviewDialogVisible = false">取消</el-button>
          <el-button v-permission="'evaluations.review'" type="primary" :loading="reviewSubmitting" @click="submitReviewForm">保存决定</el-button>
        </template>
      </el-dialog>
    </template>
    <el-dialog v-model="sourceVisible" title="证据片段与上下文" width="min(800px, calc(100vw - 24px))" top="8vh"><p class="muted">{{ sourceLabel }} · 高亮部分为本项引用的原文</p><el-alert v-if="sourceNotice" :title="sourceNotice" type="warning" :closable="false" /><div v-loading="sourceLoading" style="min-height: 120px; max-height: 65vh; overflow: auto"><p class="evidence-context"><span>{{ sourceBefore }}</span><mark>{{ sourceText }}</mark><span>{{ sourceAfter }}</span></p></div></el-dialog>
  </div>
</template>

<style scoped>
.review-toolbar { position: sticky; top: -1px; z-index: 5; padding: 10px 0; background: white; flex-wrap: wrap; margin-bottom: 16px; }
.candidate-summary { padding: 22px; background: white; border: 1px solid var(--ha-border); border-radius: 8px; margin-bottom: 14px; }.summary-main { display: flex; justify-content: space-between; gap: 24px; }.summary-main h2 { margin: 8px 0; font-size: 22px; overflow-wrap: anywhere; }.summary-main p { margin: 0; color: var(--ha-text-secondary); font-size: 13px; line-height: 1.8; max-width: 720px; }.summary-eyebrow { color: var(--ha-primary); font-size: 13px; font-weight: 600; }.summary-score { text-align: right; flex-shrink: 0; }.summary-score strong { display: block; font-size: 30px; color: var(--ha-primary); }.summary-score span { font-size: 12px; color: var(--ha-text-muted); }.summary-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 18px; color: var(--ha-text-muted); font-size: 12px; }.summary-meta > span:first-child { overflow-wrap: anywhere; max-width: 100%; }.evidence-nav { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }.evidence-nav > span { color: var(--ha-text-muted); font-size: 12px; margin-right: 8px; }.evidence-section { scroll-margin-top: 70px; }.technical-details { margin: 16px 0; }.technical-version { overflow-wrap: anywhere; }.review-context { padding: 12px 16px; margin-bottom: 20px; border-radius: 6px; background: #f5f7fa; display: flex; justify-content: space-between; gap: 20px; }.review-context span { color: var(--ha-primary); white-space: nowrap; }
@media(max-width: 600px) { .candidate-summary { padding: 16px; }.summary-main { gap: 12px; }.summary-main h2 { font-size: 18px; }.summary-score strong { font-size: 23px; } }

.evidence-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.evidence-actions :deep(.el-button) { margin: 0; border-radius: 6px; }
.evidence-section :deep(.el-table__cell) { padding: 12px 0; }
.evidence-section :deep(.cell) { line-height: 1.7; overflow-wrap: anywhere; }
.evidence-context { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.9; color: var(--ha-text-secondary); }
.evidence-context mark { background: #fff1b8; color: var(--ha-text); }
.dim-row {
  margin-bottom: 8px;
}

.dim-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.dim-name {
  font-weight: 600;
  color: #303133;
}

.dim-score {
  color: var(--el-color-primary);
  font-weight: 600;
}

.dim-reason {
  color: #606266;
  font-size: 13px;
  margin-top: 6px;
  white-space: pre-wrap;
}

.dim-evidence {
  margin-top: 4px;
}

.note-item {
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
  white-space: pre-wrap;
}

.error-text {
  color: var(--el-color-danger);
}

.supplement-list {
  width: 100%;
}

.supplement-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

h4 {
  margin: 0 0 10px;
  color: #303133;
  font-size: 14px;
}
</style>
