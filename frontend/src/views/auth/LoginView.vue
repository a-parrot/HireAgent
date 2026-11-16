<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, safeNext } from '@/stores/auth'
import { ApiError } from '@/api/http'
const username = ref(''), password = ref(''), busy = ref(false), error = ref('')
const route = useRoute(), router = useRouter()
async function submit() {
  if (!username.value.trim() || !password.value || busy.value) return
  busy.value = true; error.value = ''
  try { const user = await login(username.value.trim(), password.value); password.value = ''; await router.replace(user.must_change_password ? '/change-password' : safeNext(route.query.next)) }
  catch (err) { error.value = err instanceof ApiError ? err.message : '登录失败，请重试'; password.value = '' }
  finally { busy.value = false }
}
</script>
<template><main class="auth-page"><form class="auth-card" @submit.prevent="submit"><span class="auth-brand">H</span><h1>登录 HireAgent</h1><p>招聘评估与面试管理工作台</p><el-alert v-if="error" type="error" :title="error" :closable="false" /><label>用户名<el-input v-model="username" aria-label="用户名" autocomplete="username" maxlength="64" :disabled="busy" /></label><label>密码<el-input v-model="password" aria-label="密码" type="password" show-password autocomplete="current-password" maxlength="128" :disabled="busy" /></label><el-button type="primary" native-type="submit" :loading="busy" :disabled="!username.trim() || !password">登录</el-button><small>账号由管理员创建。如忘记密码，请联系管理员重置。</small></form></main></template>
<style scoped>.auth-page { min-height: 100%; display: grid; place-items: center; padding: 24px; background: #f3f6fb; box-sizing: border-box; }.auth-card { width: min(100%, 400px); padding: 36px; background: white; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 12px 40px #183b6510; box-sizing: border-box; }.auth-brand { display: grid; place-items: center; width: 42px; height: 42px; background: #2563eb; color: white; border-radius: 8px; font-size: 24px; font-weight: 700; }h1 { font-size: 24px; margin-bottom: 10px; }p,small { color: #8792a2; font-size: 13px; line-height: 1.8; }label { display: block; margin: 20px 0; font-size: 14px; }.el-input { margin-top: 8px; }.el-button { width: 100%; margin: 8px 0 16px; }small { display: block; }</style>
