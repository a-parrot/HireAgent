<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretRight, Document, Refresh, View } from '@element-plus/icons-vue'
import {
  getBatch,
  listCandidates,
  pdfUrl,
  retryCandidate,
  runBatch,
  type CandidateQuery,
} from '@/api/batches'
import { exportBatch } from '@/api/workflows'
import { ApiError } from '@/api/http'
import {
  batchStatusLabels,
  batchStatusTypes,
  formatScore,
  formatTime,
  processingStatusLabels,
  processingStatusTypes,
  recommendationLabels,
  recommendationTypes,
  scheduleStatusLabels,
} from '@/utils/format'
import type { BatchDetail, Candidate } from '@/api/types'

const route = useRoute()
const router = useRouter()
const batchId = route.params.id as string

const loading = ref(false)
const batch = ref<BatchDetail | null>(null)
let pollTimer: number | undefined

const candidates = ref<Candidate[]>([])
const candidateTotal = ref(0)
const candidateLoading = ref(false)
const filters = reactive({
  status: '',
  recommendation: '',
  page: 1,
  pageSize: 10,
})

const statusOptions = [
  { value: 'pending', label: '待处理' },
  { value: 'running', label: '评估中' },
  { value: 'waiting_review', label: '待人工审核' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
]

const recommendationOptions = [
  { value: 'recommended', label: '推荐' },
  { value: 'needs_review', label: '需复核' },
  { value: 'deferred', label: '暂缓' },
]

const pdfViewerVisible = ref(false)
const pdfViewerFileId = ref('')

async function loadBatch() {
  try {
    batch.value = await getBatch(batchId)
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  }
}

async function loadCandidates() {
  candidateLoading.value = true
  try {
    const query: CandidateQuery = {
      batch_id: batchId,
      page: filters.page,
      page_size: filters.pageSize,
    }
    if (filters.status) query.status = filters.status
    if (filters.recommendation) query.recommendation = filters.recommendation
    const data = await listCandidates(query)
    candidates.value = data.items
    candidateTotal.value = data.total
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    candidateLoading.value = false
  }
}

const canRun = computed(() => batch.value?.status === 'pending' || batch.value?.status === 'evaluation_done')

async function run() {
  try {
    const result = await runBatch(batchId)
    if (result.already_started) {
      ElMessage.info('批次已在执行中')
    } else {
      ElMessage.success('批次已启动')
    }
    await loadBatch()
    await loadCandidates()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  }
}

async function retry(row: Candidate) {
  try {
    await ElMessageBox.confirm(
      `从失败节点继续处理「${row.name ?? row.original_filename}」？`,
      '重试候选人',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await retryCandidate(row.id)
    ElMessage.success('已提交重试，状态刷新中')
    await loadBatch()
    await loadCandidates()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  }
}

function refreshAll() {
  loadBatch()
  loadCandidates()
}

function viewPdf(fileId: string) {
  pdfViewerFileId.value = fileId
  pdfViewerVisible.value = true
}

function openCandidate(id: string) {
  router.push(`/candidates/${id}`)
}

function doExport(format: 'json' | 'csv') {
  exportBatch(batchId, format)
}

onMounted(() => {
  refreshAll()
  pollTimer = window.setInterval(() => {
    if (batch.value && batch.value.status === 'running') {
      loadBatch()
      loadCandidates()
    }
  }, 5000)
})

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<template>
  <div v-loading="loading">
    <el-card class="page-card">
      <template #header>
        <div class="toolbar" style="margin-bottom: 0">
          <span class="section-title" style="margin: 0">{{ batch?.name || '批次详情' }}</span>
          <el-tag v-if="batch" :type="batchStatusTypes[batch.status]">
            {{ batchStatusLabels[batch.status] }}
          </el-tag>
          <div class="spacer" />
          <el-button :icon="Refresh" circle @click="refreshAll" />
          <el-button :icon="Document" @click="router.push(`/events/${batchId}`)">执行日志</el-button>
          <el-dropdown @command="doExport">
            <el-button>导出结果</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="json">JSON 完整导出</el-dropdown-item>
                <el-dropdown-item command="csv">CSV 表格导出</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button
            type="primary"
            :icon="CaretRight"
            :disabled="!canRun"
            @click="run"
          >{{ batch?.status === 'evaluation_done' ? '重新评估（新建批次推荐）' : '启动评估' }}</el-button>
        </div>
      </template>

      <el-descriptions v-if="batch" :column="4" border size="small">
        <el-descriptions-item label="批次 ID"><span class="mono">{{ batch.id }}</span></el-descriptions-item>
        <el-descriptions-item label="岗位 ID"><span class="mono">{{ batch.job_id }}</span></el-descriptions-item>
        <el-descriptions-item label="规则版本 ID"><span class="mono">{{ batch.rule_version_id }}</span></el-descriptions-item>
        <el-descriptions-item label="候选人总数">{{ batch.total }}</el-descriptions-item>
        <el-descriptions-item label="启动时间">{{ formatTime(batch.started_at) }}</el-descriptions-item>
        <el-descriptions-item label="评估完成时间">{{ formatTime(batch.evaluation_completed_at) }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(batch.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatTime(batch.updated_at) }}</el-descriptions-item>
      </el-descriptions>

      <div v-if="batch" style="margin-top: 14px">
        <el-progress
          :percentage="batch.total ? Math.round(((batch.progress.completed + batch.progress.failed) / batch.total) * 100) : 0"
          :stroke-width="14"
        />
        <div class="progress-tags">
          <el-tag type="info">待处理 {{ batch.progress.pending }}</el-tag>
          <el-tag type="primary">评估中 {{ batch.progress.running }}</el-tag>
          <el-tag type="warning">待人工审核 {{ batch.progress.waiting_review }}</el-tag>
          <el-tag type="success">已完成 {{ batch.progress.completed }}</el-tag>
          <el-tag type="danger">失败 {{ batch.progress.failed }}</el-tag>
        </div>
      </div>
    </el-card>

    <el-card>
      <template #header>
        <div class="toolbar" style="margin-bottom: 0">
          <span class="section-title" style="margin: 0">候选人（{{ candidateTotal }}）</span>
          <div class="spacer" />
          <el-select v-model="filters.status" placeholder="处理状态" clearable style="width: 140px" @change="filters.page = 1; loadCandidates()">
            <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <el-select v-model="filters.recommendation" placeholder="结论" clearable style="width: 140px" @change="filters.page = 1; loadCandidates()">
            <el-option v-for="o in recommendationOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </div>
      </template>

      <el-table :data="candidates" v-loading="candidateLoading" border stripe>
        <el-table-column label="姓名/文件" min-width="200">
          <template #default="{ row }">
            <el-link type="primary" @click="openCandidate(row.id)">
              {{ row.name || row.original_filename }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column label="处理状态" width="120">
          <template #default="{ row }">
            <el-tag :type="processingStatusTypes[row.processing_status]">
              {{ processingStatusLabels[row.processing_status] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="总分" width="90">
          <template #default="{ row }">{{ formatScore(row.total_score) }}</template>
        </el-table-column>
        <el-table-column label="结论" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.recommendation" :type="recommendationTypes[row.recommendation]">
              {{ recommendationLabels[row.recommendation] }}
            </el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="审核状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.needs_human_review" type="warning" effect="plain">需人工</el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="排期" width="100">
          <template #default="{ row }">{{ scheduleStatusLabels[row.schedule_status] }}</template>
        </el-table-column>
        <el-table-column label="错误信息" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_message" class="error-text">{{ row.error_message }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :icon="View" @click="viewPdf(row.file_id)">原件</el-button>
            <el-button size="small" type="primary" plain @click="openCandidate(row.id)">详情</el-button>
            <el-button v-if="row.processing_status === 'failed'" size="small" type="danger" plain @click="retry(row)">
              重试
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="filters.page"
        v-model:page-size="filters.pageSize"
        :total="candidateTotal"
        layout="total, prev, pager, next, sizes"
        style="margin-top: 16px; justify-content: flex-end"
        @current-change="loadCandidates"
        @size-change="loadCandidates"
      />
    </el-card>

    <el-dialog v-model="pdfViewerVisible" title="简历原件" width="880px" destroy-on-close>
      <iframe
        v-if="pdfViewerFileId"
        :src="pdfUrl(pdfViewerFileId)"
        style="width: 100%; height: 60vh; border: none"
      />
    </el-dialog>
  </div>
</template>

<style scoped>
.progress-tags {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.error-text {
  color: var(--el-color-danger);
  font-size: 12px;
}
</style>
