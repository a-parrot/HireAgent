<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { http, ApiError } from '@/api/http'
import { auth, clearAuth, logout } from '@/stores/auth'
const old = ref(''), password = ref(''), confirm = ref(''), busy = ref(false), error = ref('')
const router = useRouter()
async function submit() {
  if (busy.value) return
  if (password.value.length < 1 || password.value !== confirm.value) { error.value = '新密码不能为空，且两次输入须一致'; return }
  busy.value = true
  try { await http.post('/auth/change-password', { old_password: old.value, new_password: password.value }); clearAuth(); await router.replace('/login') }
  catch (err) { error.value = err instanceof ApiError ? err.message : '修改失败' }
  finally { busy.value = false }
}
async function exit() { await logout(); await router.replace('/login') }
</script>
<template><main class="password-page"><el-card><h1>修改密码</h1><p>{{ auth.user?.must_change_password ? '首次登录或密码重置后，请设置自己的密码再进入系统。' : '修改后所有设备将退出登录，请使用新密码重新登录。' }}</p><el-alert v-if="error" :title="error" type="error" :closable="false" /><el-form label-position="top" :disabled="busy" @submit.prevent="submit"><el-form-item label="原密码"><el-input v-model="old" aria-label="原密码" type="password" show-password autocomplete="current-password" maxlength="128" /></el-form-item><el-form-item label="新密码（1–128 位）"><el-input v-model="password" aria-label="新密码" type="password" show-password autocomplete="new-password" maxlength="128" /></el-form-item><el-form-item label="确认新密码"><el-input v-model="confirm" aria-label="确认新密码" type="password" show-password autocomplete="new-password" maxlength="128" /></el-form-item><el-button type="primary" native-type="submit" :loading="busy">修改并重新登录</el-button><el-button @click="exit">退出登录</el-button></el-form></el-card></main></template>
<style scoped>.password-page { min-height: 100%; display: grid; place-items: center; padding: 24px; box-sizing: border-box; }.el-card { width: min(100%, 460px); }h1 { font-size: 22px; }p { color: #8792a2; font-size: 13px; line-height: 1.8; }.el-form { margin-top: 20px; }</style>
