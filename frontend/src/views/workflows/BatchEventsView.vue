<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { listBatchEvents } from '@/api/workflows'
import { ApiError } from '@/api/http'
import { eventTypeLabels, eventLevelTypes, formatTime } from '@/utils/format'
import type { BatchEvent } from '@/api/types'

const route = useRoute()
const batchId = route.params.batchId as string

const loading = ref(false)
const items = ref<BatchEvent[]>([])
const totalLoaded = ref(0)
const hasMore = ref(false)
const cursor = ref<string | undefined>(undefined)

const autoRefresh = ref(false)
let timer: number | undefined

async function load(reset: boolean) {
  loading.value = true
  try {
    const data = await listBatchEvents(batchId, reset ? undefined : cursor.value, 100)
    if (reset) {
      items.value = data.items
      totalLoaded.value = data.items.length
    } else {
      items.value = [...items.value, ...data.items]
      totalLoaded.value += data.items.length
    }
    cursor.value = data.next_cursor
    hasMore.value = data.items.length >= 100
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    loading.value = false
  }
}

onMounted(() => load(true))

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})

function toggleAuto(value: boolean) {
  if (value) {
    timer = window.setInterval(() => {
      if (!loading.value) load(false)
    }, 5000)
  } else if (timer) {
    window.clearInterval(timer)
    timer = undefined
  }
}

function eventTypeText(type: string): string {
  return eventTypeLabels[type] ?? type
}
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button :icon="Refresh" @click="load(true)">重新加载</el-button>
      <el-switch
        v-model="autoRefresh"
        active-text="自动刷新（5 秒）"
        @change="toggleAuto"
      />
      <div class="spacer" />
      <span class="muted">已加载 {{ totalLoaded }} 条{{ hasMore ? '，可继续加载' : '' }}</span>
      <el-button :disabled="!hasMore || loading" @click="load(false)">加载更多</el-button>
    </div>

    <el-table :data="items" v-loading="loading" border stripe size="small">
      <el-table-column label="ID" width="120">
        <template #default="{ row }"><span class="mono">{{ row.id }}</span></template>
      </el-table-column>
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="级别" width="90">
        <template #default="{ row }">
          <el-tag :type="eventLevelTypes[row.level]">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="事件类型" width="150">
        <template #default="{ row }">{{ eventTypeText(row.event_type) }}</template>
      </el-table-column>
      <el-table-column label="节点" width="150">
        <template #default="{ row }">
          <span class="mono">{{ row.node_name ?? '-' }}</span>
          <el-tag v-if="row.attempt_count > 1" size="small" type="warning" style="margin-left: 4px">
            第{{ row.attempt_count }}次
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="候选人" width="120">
        <template #default="{ row }">
          <span class="mono">{{ row.candidate_id ?? '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="消息" min-width="280" show-overflow-tooltip>
        <template #default="{ row }">{{ row.message }}</template>
      </el-table-column>
      <el-table-column label="详情" width="100">
        <template #default="{ row }">
          <el-popover v-if="row.details" width="480" trigger="click">
            <template #reference>
              <el-button size="small" link type="primary">查看</el-button>
            </template>
            <div class="json-view">{{ JSON.stringify(row.details, null, 2) }}</div>
          </el-popover>
          <span v-else class="muted">-</span>
        </template>
      </el-table-column>
    </el-table>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="日志使用 after_id 游标分页：点击“加载更多”获取后续事件；评估执行中可开启自动刷新增量拉取。"
      style="margin-top: 16px"
    />
  </div>
</template>
