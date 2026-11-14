<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Back, View } from '@element-plus/icons-vue'
import { pdfUrl, retryCandidate } from '@/api/batches'
import { getCandidate, submitReview } from '@/api/reviews'
import { ApiError } from '@/api/http'
import {
  actionStatusLabels,
  actionStatusTypes,
  conditionResultLabels,
  conditionResultTypes,
  formatScore,
  formatTime,
  processingStatusLabels,
  processingStatusTypes,
  recommendationLabels,
  recommendationTypes,
  reviewOperationLabels,
  reviewStatusLabels,
  scheduleStatusLabels,
} from '@/utils/format'
import type { CandidateDetail } from '@/api/types'

const route = useRoute()
const router = useRouter()
const candidateId = route.params.id as string

const loading = ref(false)
const candidate = ref<CandidateDetail | null>(null)

const pdfViewerVisible = ref(false)
const pdfViewerFileId = ref('')
const pdfViewerPage = ref(1)

/* 审核表单 */
const reviewDialogVisible = ref(false)
const reviewSubmitting = ref(false)
const reviewForm = reactive({
  operation: 'approve' as 'supplement' | 'approve' | 'defer',
  reason: '',
  operator_name: '',
  supplements: [] as { source: string; description: string }[],
})

/** 根据证据 ID 找到对应页码，找不到时默认第 1 页 */
function evidencePage(evidence: CandidateDetail['evidence'], evidenceId: string): number {
  const item = evidence?.find((e) => e.evidence_id === evidenceId)
  return item?.page_no ?? 1
}async function load() {
  loading.value = true
  try {
    candidate.value = await getCandidate(candidateId)
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    loading.value = false
  }
}

onMounted(load)

function viewPage(fileId: string, page: number) {
  pdfViewerFileId.value = fileId
  pdfViewerPage.value = Math.max(1, page)
  pdfViewerVisible.value = true
}

function viewPdf(fileId: string) {
  viewPage(fileId, 1)
}

function openReview() {
  reviewForm.operation = 'approve'
  reviewForm.reason = ''
  reviewForm.operator_name = ''
  reviewForm.supplements = []
  reviewDialogVisible.value = true
}

function addSupplement() {
  reviewForm.supplements.push({ source: '', description: '' })
}

function removeSupplement(index: number) {
  reviewForm.supplements.splice(index, 1)
}

function validateReviewForm(): string | null {
  if (!reviewForm.reason.trim()) return '请填写审核理由'
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

const canReview = computed(
  () =>
    candidate.value?.processing_status === 'waiting_review' ||
    (candidate.value?.processing_status === 'completed' &&
      candidate.value?.review_status === 'pending'),
)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <el-button :icon="Back" @click="router.back()">返回</el-button>
      <div class="spacer" />
      <el-button v-if="candidate?.processing_status === 'failed'" type="danger" plain @click="retry">
        重试
      </el-button>
      <el-button type="primary" :disabled="!canReview" @click="openReview">人工审核</el-button>
    </div>

    <template v-if="candidate">
      <el-card class="page-card">
        <template #header><span class="section-title" style="margin: 0">基本信息</span></template>
        <el-descriptions :column="4" border size="small">
          <el-descriptions-item label="姓名">{{ candidate.name ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="原文件名">{{ candidate.original_filename }}</el-descriptions-item>
          <el-descriptions-item label="处理状态">
            <el-tag :type="processingStatusTypes[candidate.processing_status]">
              {{ processingStatusLabels[candidate.processing_status] }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="总分">{{ formatScore(candidate.total_score) }}</el-descriptions-item>
          <el-descriptions-item label="结论">
            <el-tag v-if="candidate.recommendation" :type="recommendationTypes[candidate.recommendation]">
              {{ recommendationLabels[candidate.recommendation] }}
            </el-tag>
            <span v-else class="muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="审核状态">{{ reviewStatusLabels[candidate.review_status] }}</el-descriptions-item>
          <el-descriptions-item label="排期状态">{{ scheduleStatusLabels[candidate.schedule_status] }}</el-descriptions-item>
          <el-descriptions-item label="重试次数">{{ candidate.retry_count }}</el-descriptions-item>
          <el-descriptions-item label="批次 ID"><span class="mono">{{ candidate.batch_id }}</span></el-descriptions-item>
          <el-descriptions-item label="文件 ID"><span class="mono">{{ candidate.file_id }}</span></el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatTime(candidate.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ formatTime(candidate.completed_at) }}</el-descriptions-item>
          <el-descriptions-item label="当前节点">{{ candidate.current_node ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ candidate.model_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="提示词版本">
            <span v-if="candidate.prompt_versions" class="mono">
              {{ Object.entries(candidate.prompt_versions).map(([k, v]) => `${k}:${v}`).join(' / ') }}
            </span>
            <span v-else class="muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="查看原件">
            <el-button size="small" :icon="View" @click="viewPdf(candidate.file_id)">PDF 原件</el-button>
          </el-descriptions-item>
          <el-descriptions-item v-if="candidate.error_message" label="错误信息" :span="2">
            <span class="error-text">{{ candidate.error_node ? `[${candidate.error_node}] ` : '' }}{{ candidate.error_message }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card class="page-card">
        <template #header><span class="section-title" style="margin: 0">硬性条件</span></template>
        <el-table
          v-if="candidate.hard_conditions && candidate.hard_conditions.length"
          :data="candidate.hard_conditions"
          border
          size="small"
        >
          <el-table-column label="条件 ID" prop="condition_id" width="180" />
          <el-table-column label="判定" width="110">
            <template #default="{ row }">
              <el-tag :type="conditionResultTypes[row.result]">{{ conditionResultLabels[row.result] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="判定理由" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">{{ row.reason }}</template>
          </el-table-column>
          <el-table-column label="证据" width="120">
            <template #default="{ row }">
              <el-button
                v-for="eid in row.evidence_ids"
                :key="eid"
                size="small"
                link
                type="primary"
                @click="viewPage(candidate!.file_id!, evidencePage(candidate!.evidence, eid))"
              >证据 {{ eid.slice(-4) }}</el-button>
            </template>
          </el-table-column>
        </el-table>
        <span v-else class="muted">暂无硬性条件判定结果</span>
      </el-card>

      <el-card class="page-card">
        <template #header><span class="section-title" style="margin: 0">维度评分</span></template>
        <div v-if="candidate.dimension_scores && candidate.dimension_scores.length">
          <div v-for="dim in candidate.dimension_scores" :key="dim.dimension_id" class="dim-row">
            <div class="dim-head">
              <span class="dim-name">{{ dim.dimension_id }}</span>
              <span class="dim-score">{{ formatScore(dim.score) }} 分</span>
            </div>
            <el-progress
              :percentage="Math.min(100, Math.round(Number(dim.score) || 0))"
              :stroke-width="8"
              :show-text="false"
            />
            <div class="dim-reason">{{ dim.reason }}</div>
            <div class="dim-evidence">
              <el-button
                v-for="eid in dim.evidence_ids"
                :key="eid"
                size="small"
                link
                type="primary"
                @click="viewPage(candidate!.file_id!, evidencePage(candidate!.evidence, eid))"
              >证据 {{ eid.slice(-4) }}</el-button>
            </div>
            <el-divider style="margin: 10px 0" />
          </div>
        </div>
        <span v-else class="muted">暂无维度评分</span>
      </el-card>

      <el-card class="page-card">
        <template #header><span class="section-title" style="margin: 0">原始事实与证据</span></template>
        <el-row :gutter="16">
          <el-col :span="12">
            <h4>提取事实</h4>
            <el-table
              v-if="candidate.extracted_facts && candidate.extracted_facts.length"
              :data="candidate.extracted_facts"
              border
              size="small"
            >
              <el-table-column label="类型" prop="type" width="120" />
              <el-table-column label="描述" min-width="240" show-overflow-tooltip>
                <template #default="{ row }">{{ row.description }}</template>
              </el-table-column>
              <el-table-column label="证据" width="130">
                <template #default="{ row }">
                  <el-button
                    v-for="eid in row.evidence_ids"
                    :key="eid"
                    size="small"
                    link
                    type="primary"
                    @click="viewPage(candidate!.file_id!, evidencePage(candidate!.evidence, eid))"
                  >证据 {{ eid.slice(-4) }}</el-button>
                </template>
              </el-table-column>
            </el-table>
            <span v-else class="muted">暂无事实数据</span>
          </el-col>
          <el-col :span="12">
            <h4>证据原文（含页码）</h4>
            <el-table
              v-if="candidate.evidence && candidate.evidence.length"
              :data="candidate.evidence"
              border
              size="small"
            >
              <el-table-column label="页码" width="80">
                <template #default="{ row }">第 {{ row.page_no }} 页</template>
              </el-table-column>
              <el-table-column label="原文片段" min-width="280">
                <template #default="{ row }">
                  <span style="white-space: pre-wrap">{{ row.quote }}</span>
                </template>
              </el-table-column>
              <el-table-column label="定位" width="90">
                <template #default="{ row }">
                  <el-button size="small" link type="primary" @click="viewPage(candidate!.file_id!, row.page_no)">
                    打开原件
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <span v-else class="muted">暂无证据数据</span>
          </el-col>
        </el-row>
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

      <el-card class="page-card">
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
        <div style="margin-top: 12px">
          <el-button size="small" type="primary" plain @click="router.push(`/schedules/${candidate.batch_id}`)">
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

      <el-dialog v-model="pdfViewerVisible" title="简历原件" width="880px" destroy-on-close>
        <iframe
          v-if="pdfViewerFileId"
          :src="`${pdfUrl(pdfViewerFileId)}#page=${pdfViewerPage}`"
          style="width: 100%; height: 60vh; border: none"
        />
        <div class="muted">定位到第 {{ pdfViewerPage }} 页（如浏览器 PDF 插件不支持跳页，请手动翻页）</div>
      </el-dialog>

      <el-dialog v-model="reviewDialogVisible" title="人工审核决定" width="640px">
        <el-form label-width="90px">
          <el-form-item label="操作类型">
            <el-radio-group v-model="reviewForm.operation">
              <el-radio-button value="supplement">补充说明</el-radio-button>
              <el-radio-button value="approve">批准</el-radio-button>
              <el-radio-button value="defer">暂缓</el-radio-button>
            </el-radio-group>
            <div class="muted" style="margin-top: 4px">
              补充说明不会自动批准候选人；批准后恢复流程已排队，刷新详情查看最终状态。
            </div>
          </el-form-item>
          <el-form-item label="理由" required>
            <el-input v-model="reviewForm.reason" type="textarea" :rows="3" placeholder="说明审核依据，如：已核对项目经历与证据" />
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
            <el-input v-model="reviewForm.operator_name" maxlength="128" placeholder="招聘人员姓名" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="reviewDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="reviewSubmitting" @click="submitReviewForm">保存决定</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<style scoped>
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
