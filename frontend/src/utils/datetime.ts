/** 本地时间与 ISO 8601（带时区偏移）转换工具 */

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** 把 Date 转成带本地时区偏移的 ISO 字符串，如 2030-01-01T09:00:00+08:00 */
export function toLocalIso(date: Date): string {
  const offsetMinutes = -date.getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const absOffset = Math.abs(offsetMinutes)
  const offsetStr = `${sign}${pad(Math.floor(absOffset / 60))}:${pad(absOffset % 60)}`
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}${offsetStr}`
  )
}

/** 把 Date 转成 datetime-local 输入框需要的字符串 yyyy-MM-ddTHH:mm */
export function toLocalInput(date: Date): string {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** datetime-local 字符串解析为 Date */
export function fromLocalInput(value: string): Date {
  return new Date(value)
}

/** 格式化时段显示 */
export function formatRange(startsAt: string, endsAt: string): string {
  return `${formatTimeStr(startsAt)} ~ ${formatTimeStr(endsAt)}`
}

function formatTimeStr(value: string): string {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { hour12: false })
}
