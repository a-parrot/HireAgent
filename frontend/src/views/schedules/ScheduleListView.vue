<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listBatches } from '@/api/batches'
import { ApiError } from '@/api/http'
import { batchStatusLabels, batchStatusTypes, formatTime } from '@/utils/format'
import type { Batch } from '@/api/types'

const router = useRouter()
const loading = ref(false)
const items = ref<Batch[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

async function load() {
  loading.value = true
  try {
    const data = await listBatches(page.value, pageSize.value)
    items.value = data.items
    total.value = data.total
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span class="muted">选择评估完成的批次进行时段管理与统一排期</span>
    </div>
    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column label="批次" min-width="200">
        <template #default="{ row }">{{ row.name || row.id }}</template>
      </el-table-column>
      <el-table-column label="批次 ID" width="140">
        <template #default="{ row }"><span class="mono">{{ row.id }}</span></template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="batchStatusTypes[row.status]">{{ batchStatusLabels[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="评估完成时间" width="180">
        <template #default="{ row }">{{ formatTime(row.evaluation_completed_at) }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" plain @click="router.push(`/schedules/${row.id}`)">
            排期管理
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 16px; justify-content: flex-end"
      @current-change="load"
    />
  </div>
</template>
