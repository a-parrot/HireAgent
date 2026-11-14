<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { UploadUserFile } from 'element-plus'
import { createBatch, listBatches } from '@/api/batches'
import { getJob, listJobs } from '@/api/jobs'
import { ApiError } from '@/api/http'
import { batchStatusLabels, batchStatusTypes, formatTime } from '@/utils/format'
import type { Batch, Job, JobRuleVersion } from '@/api/types'

const router = useRouter()

const loading = ref(false)
const items = ref<Batch[]>([])
const total = ref(0)
const query = reactive({ page: 1, pageSize: 10 })

async function load() {
  loading.value = true
  try {
    const data = await listBatches(query.page, query.pageSize)
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

/* 创建批次对话框 */
const dialogVisible = ref(false)
const submitting = ref(false)
const jobs = ref<Job[]>([])
const versions = ref<JobRuleVersion[]>([])
const createForm = reactive({
  job_id: '',
  rule_version_id: '',
  name: '',
  files: [] as UploadUserFile[],
})

const activeJobs = computed(() => jobs.value.filter((j) => j.status === 'active'))

watch(dialogVisible, async (visible) => {
  if (!visible) return
  createForm.job_id = ''
  createForm.rule_version_id = ''
  createForm.name = ''
  createForm.files = []
  versions.value = []
  try {
    const data = await listJobs(1, 100)
    jobs.value = data.items
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  }
})

async function onJobChange(jobId: string) {
  createForm.rule_version_id = ''
  versions.value = []
  if (!jobId) return
  try {
    const detail = await getJob(jobId)
    versions.value = detail.versions
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  }
}

function onFileChange(files: UploadUserFile[]) {
  const invalid = files.filter((f) => !f.name.toLowerCase().endsWith('.pdf'))
  if (invalid.length > 0) {
    ElMessage.warning('仅支持 PDF 文件')
    createForm.files = files.filter((f) => f.name.toLowerCase().endsWith('.pdf'))
  }
}

async function submitCreate() {
  if (!createForm.job_id) {
    ElMessage.warning('请选择岗位')
    return
  }
  if (!createForm.rule_version_id) {
    ElMessage.warning('请选择规则版本')
    return
  }
  const rawFiles = createForm.files
    .map((f) => f.raw)
    .filter((f) => !!f) as File[]
  if (rawFiles.length === 0) {
    ElMessage.warning('请选择至少一份简历 PDF')
    return
  }
  submitting.value = true
  try {
    const batch = await createBatch({
      job_id: createForm.job_id,
      rule_version_id: createForm.rule_version_id,
      files: rawFiles,
      name: createForm.name || undefined,
    })
    ElMessage.success(`批次已创建，本次导入 ${batch.imported_count} 位候选人`)
    dialogVisible.value = false
    router.push(`/batches/${batch.id}`)
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    submitting.value = false
  }
}

function openBatch(id: string) {
  router.push(`/batches/${id}`)
}
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="dialogVisible = true">创建批次</el-button>
      <div class="spacer" />
      <span class="muted">共 {{ total }} 个批次</span>
    </div>

    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column label="批次" min-width="200">
        <template #default="{ row }">
          <el-link type="primary" @click="openBatch(row.id)">{{ row.name || row.id }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="批次 ID" width="140">
        <template #default="{ row }"><span class="mono">{{ row.id }}</span></template>
      </el-table-column>
      <el-table-column label="岗位 ID" width="140">
        <template #default="{ row }"><span class="mono">{{ row.job_id }}</span></template>
      </el-table-column>
      <el-table-column label="规则版本 ID" width="140">
        <template #default="{ row }"><span class="mono">{{ row.rule_version_id }}</span></template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="batchStatusTypes[row.status]">{{ batchStatusLabels[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openBatch(row.id)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="query.page"
      v-model:page-size="query.pageSize"
      :total="total"
      layout="total, prev, pager, next, sizes"
      style="margin-top: 16px; justify-content: flex-end"
      @current-change="load"
      @size-change="load"
    />

    <el-dialog v-model="dialogVisible" title="创建评估批次" width="640px">
      <el-form label-width="90px">
        <el-form-item label="岗位" required>
          <el-select v-model="createForm.job_id" placeholder="选择启用中的岗位" style="width: 100%" @change="onJobChange">
            <el-option
              v-for="j in activeJobs"
              :key="j.id"
              :label="`${j.name}（${j.code}）`"
              :value="j.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="规则版本" required>
          <el-select
            v-model="createForm.rule_version_id"
            placeholder="先选择岗位，再选择已发布版本"
            style="width: 100%"
            :disabled="!createForm.job_id"
          >
            <el-option
              v-for="v in versions"
              :key="v.id"
              :label="`v${v.version_no}（${v.published_at ? new Date(v.published_at).toLocaleString('zh-CN') : '-'}）`"
              :value="v.id"
            />
          </el-select>
          <div v-if="createForm.job_id && versions.length === 0" class="muted" style="margin-top: 4px">
            该岗位尚未发布任何规则版本，请先到岗位详情发布。
          </div>
        </el-form-item>
        <el-form-item label="批次名称">
          <el-input v-model="createForm.name" maxlength="200" placeholder="可选，如：3月后端批量初筛" />
        </el-form-item>
        <el-form-item label="简历 PDF" required>
          <el-upload
            v-model:file-list="createForm.files"
            multiple
            :auto-upload="false"
            accept=".pdf"
            drag
            @change="onFileChange"
          >
            <div style="padding: 20px 0">
              <p>将 PDF 文件拖到此处，或点击选择</p>
              <p class="muted">支持多选；同一文件在本批次只导入一次</p>
            </div>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">创建批次</el-button>
      </template>
    </el-dialog>
  </div>
</template>
