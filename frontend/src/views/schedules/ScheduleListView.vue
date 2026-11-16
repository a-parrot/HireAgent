<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listSchedulingRecords } from '@/api/schedules'
import type { SchedulingRecord } from '@/api/schedules'
import { ApiError } from '@/api/http'
import { formatTime } from '@/utils/format'
import { Calendar } from '@element-plus/icons-vue'

const router = useRouter()
const loading = ref(false)
const items = ref<SchedulingRecord[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const error = ref('')

async function load() {
  loading.value = true
  try {
    const data = await listSchedulingRecords(page.value, pageSize.value)
    items.value = data.items
    total.value = data.total
    error.value = ''
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '无法读取面试安排，请重试'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="schedule-heading">
      <div><h1>面试排期</h1><p>查看已准入的候选人，补充面试时间并管理预约。批量生成时间可前往评估管理。</p></div>
      <div class="schedule-actions"><el-button @click="router.push({ path: '/evaluations', query: { workflow: 'awaiting_schedule' } })">待安排面试</el-button><el-button :loading="loading" @click="load">刷新安排</el-button></div>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" style="margin-bottom: 16px" />
    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column label="招聘岗位" min-width="200">
        <template #default="{ row }">{{ row.job_name }}</template>
      </el-table-column>
      <el-table-column label="面试人数" width="110"><template #default="{ row }">{{ row.interview_count }} 人</template></el-table-column><el-table-column label="已排期" width="110"><template #default="{ row }">{{ row.scheduled_count }} 人</template></el-table-column>
      <el-table-column label="待安排" width="110"><template #default="{ row }">{{ Math.max(0, row.interview_count - row.scheduled_count) }} 人</template></el-table-column>
      <el-table-column label="安排状态" width="130">
        <template #default="{ row }">
          <el-tag :type="row.interview_count > row.scheduled_count ? 'warning' : 'success'">{{ row.interview_count > row.scheduled_count ? '待安排时间' : '已完成排期' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="评估完成时间" width="180">
        <template #default="{ row }">{{ formatTime(row.evaluation_completed_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-tooltip content="排期管理"><el-button circle text type="primary" :icon="Calendar" aria-label="排期管理" @click="router.push(`/schedules/${row.id}`)" /></el-tooltip>
        </template>
      </el-table-column>
      <template #empty><el-empty :description="error ? '面试安排暂时无法加载' : '还没有已准入面试的候选人'" :image-size="70"><el-button @click="error ? load() : router.push('/evaluations')">{{ error ? '重新加载' : '前往处理评估结果' }}</el-button></el-empty></template>
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

<style scoped>
.schedule-heading { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }.schedule-heading h1 { font-size: 22px; margin: 8px 0; }.schedule-heading p { color: var(--ha-text-muted); font-size: 13px; line-height: 1.7; margin: 0; }.schedule-actions { display: flex; gap: 12px; flex-wrap: wrap; }
</style>
