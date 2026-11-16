import axios from 'axios'
import { ElMessage } from 'element-plus'

/** 统一 axios 实例：/api 前缀由 vite 代理到后端 */
export const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function extractDetail(data: unknown): string | undefined {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      // FastAPI 校验错误
      return detail
        .map((item) => {
          const d = item as { loc?: (string | number)[]; msg?: string }
          return `${(d.loc ?? []).join('.')}: ${d.msg ?? ''}`
        })
        .join('; ')
    }
    return JSON.stringify(detail)
  }
  return undefined
}

http.interceptors.request.use(config => {
  const csrf = document.cookie.split('; ').find(c => c.startsWith('hireagent_csrf='))?.split('=').slice(1).join('=')
  if (csrf && !['get', 'head', 'options'].includes(config.method || 'get')) config.headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    let status = 0
    let message = '网络请求失败，请检查后端服务是否可用'
    if (error.response) {
      status = error.response.status
      if (status === 401 && !String(error.config?.url).startsWith('/auth/')) window.dispatchEvent(new Event('auth-expired'))
      message = extractDetail(error.response.data) ?? `请求失败（HTTP ${status}）`
    } else if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      message = '请求超时，暂时无法确认最新状态，请稍后刷新'
    } else if (error.code === 'ERR_CANCELED') {
      message = '请求已取消'
    } else if (error.request) {
      message = '无法连接后端服务，请检查后端是否启动或网络是否正常'
    }
    return Promise.reject(new ApiError(status, message))
  },
)

/** 在页面中统一弹出错误提示并抛出，避免每处重复 try/catch 提示 */
export async function withToast<T>(action: () => Promise<T>): Promise<T> {
  try {
    return await action()
  } catch (err) {
    if (err instanceof ApiError) {
      ElMessage.error(err.message)
    } else {
      ElMessage.error('操作失败')
    }
    throw err
  }
}

/** 触发浏览器下载文件（导出 / PDF 原件） */
export function downloadFile(url: string, filename?: string): void {
  const a = document.createElement('a')
  a.href = url
  if (filename) a.download = filename
  a.target = '_blank'
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}
