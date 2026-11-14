<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import JobFormDialog from '@/components/jobs/JobFormDialog.vue'
import { disableJob, listJobs } from '@/api/jobs'
import { ApiError } from '@/api/http'
import { formatTime } from '@/utils/format'
import type { Job } from '@/api/types'

const router = useRouter()
const formDialogRef = ref<InstanceType<typeof JobFormDialog>>()

const loading = ref(false)
const items = ref<Job[]>([])
const total = ref(0)
const query = reactive({ page: 1, pageSize: 10 })

async function load() {
  loading.value = true
  try {
    const data = await listJobs(query.page, query.pageSize)
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openJob(id: string) {
  router.push(`/jobs/${id}`)
}

async function disable(job: Job) {
  try {
    await ElMessageBox.confirm(
      `停用后不可再创建新批次，历史评估结果仍可查看。确认停用岗位「${job.name}」？`,
      '停用岗位',
      { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await disableJob(job.id)
    ElMessage.success('已停用')
    await load()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  }
}

function onSaved(jobId: string) {
  openJob(jobId)
}
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="formDialogRef?.open()">新建岗位</el-button>
      <div class="spacer" />
      <span class="muted">共 {{ total }} 个岗位</span>
      <el-button :icon="Refresh" circle @click="load" />
    </div>

    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column label="编号" prop="code" width="140" />
      <el-table-column label="岗位名称" min-width="180">
        <template #default="{ row }">
          <el-link type="primary" @click="openJob(row.id)">{{ row.name }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'">
            {{ row.status === 'active' ? '启用' : '已停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="草稿版本" prop="draft_version" width="100" />
      <el-table-column label="已定义规则" width="110">
        <template #default="{ row }">
          <el-tag :type="row.draft_rules ? 'success' : 'info'" effect="plain">
            {{ row.draft_rules ? '有' : '无' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="180">
        <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openJob(row.id)">详情</el-button>
          <el-button
            v-if="row.status === 'active'"
            size="small"
            type="danger"
            plain
            @click="disable(row)"
          >停用</el-button>
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

    <JobFormDialog ref="formDialogRef" @saved="onSaved" />
  </div>
</template>
