import { reactive } from 'vue'
import { http, ApiError } from '@/api/http'

export interface AuthUser { id: string; username: string; display_name: string; role: string; role_id: string; role_name: string; status: string; must_change_password: boolean; permissions: string[] }
export const auth = reactive({ user: null as AuthUser | null })
let pending: Promise<AuthUser | null> | undefined
export function can(permission: string) { return !!auth.user?.permissions.includes(permission) && !auth.user.must_change_password }
export function clearAuth() { auth.user = null }
export async function loadAuth(force = false): Promise<AuthUser | null> {
  if (auth.user && !force) return auth.user
  if (!pending) pending = http.get<AuthUser>('/auth/me').then(r => (auth.user = r.data)).catch(err => {
    auth.user = null
    if (err instanceof ApiError && err.status === 401) return null
    throw err
  }).finally(() => { pending = undefined })
  return pending
}
export async function login(username: string, password: string) { auth.user = (await http.post<AuthUser>('/auth/login', { username, password })).data; return auth.user }
export async function logout() { try { await http.post('/auth/logout') } finally { clearAuth() } }
export function safeNext(value: unknown) { return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') && !value.includes('\\') && !/^\/(login|change-password)/.test(value) ? value : '/jobs' }
