<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, RouterView } from 'vue-router'
import {
  Briefcase,
  FolderOpened,
  Calendar,
  Document,
} from '@element-plus/icons-vue'

const route = useRoute()

const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/jobs')) return '/jobs'
  if (path.startsWith('/batches') || path.startsWith('/candidates')) return '/batches'
  if (path.startsWith('/schedules')) return '/schedules'
  if (path.startsWith('/events')) return '/events'
  return path
})

const pageTitle = computed(() => (route.meta.title as string) ?? '')
const activeBatchId = computed(() => route.params.batchId as string | undefined)
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">
        <span class="brand-mark">H</span>
        <span class="brand-name">HireAgent</span>
      </div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/jobs" :icon="Briefcase">岗位管理</el-menu-item>
        <el-menu-item index="/batches" :icon="FolderOpened">评估批次</el-menu-item>
        <el-menu-item index="/schedules" :icon="Calendar">面试排期</el-menu-item>
        <el-menu-item
          v-if="activeBatchId"
          :index="`/events/${activeBatchId}`"
          :icon="Document"
        >执行日志</el-menu-item>
      </el-menu>
      <div class="aside-footer muted">简历评估 · 人工审核 · 统一排期</div>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="header-title">{{ pageTitle }}</span>
      </el-header>
      <el-main class="main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100%;
}

.aside {
  background: #001529;
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 20px 16px;
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: #409eff;
  color: #fff;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-name {
  color: #fff;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.menu {
  border-right: none;
  background: transparent;
  flex: 1;
}

.menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.72);
}

.menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.menu :deep(.el-menu-item.is-active) {
  background: #409eff;
  color: #fff;
}

.aside-footer {
  padding: 16px 20px;
  color: rgba(255, 255, 255, 0.45);
  font-size: 12px;
}

.header {
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.main {
  padding: 20px;
  overflow: auto;
}
</style>
