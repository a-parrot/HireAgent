<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, RouterView } from 'vue-router'
import { Briefcase, FolderOpened, Calendar, Document, Fold, Expand, UserFilled } from '@element-plus/icons-vue'

const route = useRoute()
const collapsed = ref(window.innerWidth <= 720)
const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/jobs')) return '/jobs'
  if (path.startsWith('/batches') || path.startsWith('/candidates')) return '/batches'
  if (path.startsWith('/schedules')) return '/schedules'
  if (path.startsWith('/events')) return `/events/${route.params.batchId}`
  return path
})
const pageTitle = computed(() => (route.meta.title as string) ?? '')
const activeBatchId = computed(() => route.params.batchId as string | undefined)
</script>

<template>
  <div class="layout">
    <aside class="aside" :class="{ 'is-collapsed': collapsed }" aria-label="主导航">
      <div class="brand"><span class="brand-mark">H</span><span v-if="!collapsed" class="brand-name">HireAgent 招聘系统</span></div>
      <el-menu :default-active="activeMenu" :collapse="collapsed" :collapse-transition="false" router class="menu">
        <el-menu-item index="/jobs" ><el-icon><Briefcase /></el-icon><template #title>岗位管理</template></el-menu-item>
        <el-menu-item index="/batches" ><el-icon><FolderOpened /></el-icon><template #title>评估批次</template></el-menu-item>
        <el-menu-item index="/schedules" ><el-icon><Calendar /></el-icon><template #title>面试排期</template></el-menu-item>
        <el-menu-item v-if="activeBatchId" :index="`/events/${activeBatchId}`" ><el-icon><Document /></el-icon><template #title>执行日志</template></el-menu-item>
      </el-menu>
      <div class="aside-footer"><span v-if="!collapsed">简历评估 · 人工审核 · 统一排期</span><span v-else>HA</span></div>
    </aside>
    <div class="layout-right">
      <header class="header">
        <div class="header-left">
          <button class="collapse-button" type="button" :aria-label="collapsed ? '展开侧栏' : '收起侧栏'" :aria-expanded="!collapsed" @click="collapsed = !collapsed"><el-icon :size="20"><Expand v-if="collapsed" /><Fold v-else /></el-icon></button>
          <span class="header-title">{{ pageTitle }}</span>
        </div>
        <span class="header-context"><el-icon :size="16"><UserFilled /></el-icon>招聘工作台</span>
      </header>
      <main class="main"><RouterView /></main>
    </div>
  </div>
</template>

<style scoped>
.layout { display: flex; height: 100%; overflow: hidden; }
.aside { width: 220px; flex-shrink: 0; display: flex; flex-direction: column; background: var(--ha-sidebar-bg); transition: width .2s ease; overflow: hidden; }
.aside.is-collapsed { width: 64px; }
.brand { display: flex; align-items: center; gap: 10px; height: 56px; padding: 0 16px; flex-shrink: 0; border-bottom: 1px solid rgba(255,255,255,.06); }
.brand-mark { width: 32px; height: 32px; flex-shrink: 0; border-radius: 6px; background: var(--ha-primary); color: white; font-weight: 700; display: grid; place-items: center; }
.brand-name { color: white; font-size: 15px; font-weight: 600; white-space: nowrap; }
.menu { border: 0; background: transparent; flex: 1; width: 100%; padding: 12px 8px; overflow-y: auto; --el-menu-bg-color: transparent; --el-menu-text-color: var(--ha-sidebar-text); --el-menu-hover-bg-color: var(--ha-sidebar-hover); --el-menu-active-color: white; }
.menu :deep(.el-menu-item) { height: 44px; margin-bottom: 4px; border-radius: var(--ha-radius); font-size: 15px; }
.menu :deep(.el-menu-item:hover) { color: white; }
.menu :deep(.el-menu-item.is-active) { background: var(--ha-primary); color: white; }
.menu.el-menu--collapse :deep(.el-menu-item) { padding: 0 12px !important; }
.menu.el-menu--collapse :deep(.el-menu-tooltip__trigger) { padding: 0 12px; }
.aside-footer { padding: 12px 16px; color: rgba(163,177,194,.5); font-size: 12px; border-top: 1px solid rgba(255,255,255,.06); white-space: nowrap; }
.layout-right { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.header { height: 56px; flex-shrink: 0; padding: 0 20px; background: white; border-bottom: 1px solid var(--ha-border); box-shadow: var(--ha-shadow); display: flex; align-items: center; justify-content: space-between; z-index: 10; }
.header-left { display: flex; align-items: center; gap: 14px; min-width: 0; }
.collapse-button { border: 0; padding: 4px; background: transparent; color: var(--ha-text-secondary); cursor: pointer; display: grid; place-items: center; border-radius: 4px; }
.collapse-button:hover { color: var(--ha-primary); background: var(--el-color-primary-light-9); }
.header-title { font-size: 16px; font-weight: 600; color: var(--ha-text); }
.header-context { display: flex; align-items: center; gap: 6px; color: var(--ha-text-secondary); font-size: 15px; white-space: nowrap; }
.main { flex: 1; min-height: 0; padding: 20px; overflow: auto; background: var(--ha-page-bg); }
@media (max-width: 720px) { .aside:not(.is-collapsed) { position: absolute; inset: 0 auto 0 0; z-index: 20; box-shadow: 4px 0 16px #00152922; } .layout:has(.aside:not(.is-collapsed)) .layout-right { margin-left: 220px; } .main { padding: 14px; } .header { padding: 0 14px; } .header-context { display: none; } }
</style>
