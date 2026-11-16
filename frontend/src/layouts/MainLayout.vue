<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import { Briefcase, Calendar, Document, Fold, Expand, UserFilled, Checked, Clock } from '@element-plus/icons-vue'
import { auth, can, logout } from '@/stores/auth'
import RecruitmentFlow from '@/components/RecruitmentFlow.vue'

const route = useRoute()
const router = useRouter()
async function exit() { try { await logout() } finally { await router.replace('/login') } }
const compactScreen = window.matchMedia('(max-width: 1000px)')
const collapsed = ref(compactScreen.matches)
function collapseOnNarrowScreen(event: MediaQueryListEvent) { if (event.matches) collapsed.value = true }
onMounted(() => compactScreen.addEventListener('change', collapseOnNarrowScreen))
onBeforeUnmount(() => compactScreen.removeEventListener('change', collapseOnNarrowScreen))
const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/resumes')) return '/resumes'
  if (path.startsWith('/jobs')) return '/jobs'
  if (path.startsWith('/candidates')) return '/evaluations'
  if (path.startsWith('/schedules')) return '/schedules'
  if (path.startsWith('/events')) return '/history'
  return path
})
const pageTitle = computed(() => (route.meta.title as string) ?? '')
</script>

<template>
  <div class="layout">
    <aside class="aside" :class="{ 'is-collapsed': collapsed }" aria-label="主导航">
      <div class="brand"><span class="brand-mark">H</span><span v-if="!collapsed" class="brand-name">HireAgent 招聘系统</span></div>
      <el-menu :default-active="activeMenu" :collapse="collapsed" :collapse-transition="false" router class="menu">
        <el-menu-item v-if="can('jobs.read')" index="/jobs" ><el-icon><Briefcase /></el-icon><template #title>岗位管理</template></el-menu-item>
        <el-menu-item v-if="can('resumes.read')" index="/resumes"><el-icon><Document /></el-icon><template #title>简历评估</template></el-menu-item>
        <el-menu-item v-if="can('evaluations.read')" index="/evaluations"><el-icon><Checked /></el-icon><template #title>评估管理</template></el-menu-item>
        <el-menu-item v-if="can('schedules.read')" index="/schedules" ><el-icon><Calendar /></el-icon><template #title>面试排期</template></el-menu-item>
        <el-menu-item v-if="can('history.read')" index="/history"><el-icon><Clock /></el-icon><template #title>记录日志</template></el-menu-item>
        <el-menu-item v-if="can('users.manage')" index="/users"><el-icon><UserFilled /></el-icon><template #title>用户管理</template></el-menu-item>
      </el-menu>
      <div class="aside-footer"><span v-if="!collapsed">简历评估 · 人工审核 · 统一排期</span><span v-else>HA</span></div>
    </aside>
    <div class="layout-right">
      <header class="header">
        <div class="header-left">
          <button class="collapse-button" type="button" :aria-label="collapsed ? '展开侧栏' : '收起侧栏'" :aria-expanded="!collapsed" @click="collapsed = !collapsed"><el-icon :size="20"><Expand v-if="collapsed" /><Fold v-else /></el-icon></button>
          <span class="header-title">{{ pageTitle }}</span>
        </div>
        <el-dropdown @command="(command: string) => command === 'logout' ? exit() : router.push('/change-password')"><button class="account-button"><el-icon><UserFilled /></el-icon>{{ auth.user?.display_name }} · {{ auth.user?.role_name }}</button><template #dropdown><el-dropdown-menu><el-dropdown-item command="password">修改密码</el-dropdown-item><el-dropdown-item command="logout">退出登录</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
      </header>
      <main class="main"><RecruitmentFlow /><RouterView /></main>
    </div>
  </div>
</template>

<style scoped>
.account-button { border: 0; background: transparent; display: flex; gap: 6px; align-items: center; cursor: pointer; color: var(--ha-text-secondary); font-size: 13px; }

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
