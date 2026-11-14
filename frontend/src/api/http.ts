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

http.interceptors.response.use(
  (response) => response,
  (error) => {
    let status = 0
    let message = '网络请求失败，请检查后端服务是否可用'
    if (error.response) {
      status = error.response.status
      message = extractDetail(error.response.data) ?? `请求失败（HTTP ${status}）`
    } else if (error.request) {
      message = '无法连接后端服务'
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
