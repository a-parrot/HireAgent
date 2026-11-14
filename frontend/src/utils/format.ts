/** 通用格式化与展示工具 */

/** ISO 时间转本地可读字符串 */
export function formatTime(value: string | null | undefined): string {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { hour12: false })
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return '-'
  return Number(score).toFixed(1)
}

export const processingStatusLabels: Record<string, string> = {
  pending: '待处理',
  running: '评估中',
  waiting_review: '待人工审核',
  completed: '已完成',
  failed: '失败',
}

export const processingStatusTypes: Record<string, 'info' | 'warning' | 'success' | 'danger' | 'primary'> = {
  pending: 'info',
  running: 'primary',
  waiting_review: 'warning',
  completed: 'success',
  failed: 'danger',
}

export const recommendationLabels: Record<string, string> = {
  recommended: '推荐',
  needs_review: '需复核',
  deferred: '暂缓',
}

export const recommendationTypes: Record<string, 'success' | 'warning' | 'info'> = {
  recommended: 'success',
  needs_review: 'warning',
  deferred: 'info',
}

export const batchStatusLabels: Record<string, string> = {
  pending: '待启动',
  running: '执行中',
  evaluation_done: '评估完成',
}

export const batchStatusTypes: Record<string, 'info' | 'primary' | 'success'> = {
  pending: 'info',
  running: 'primary',
  evaluation_done: 'success',
}

export const conditionResultLabels: Record<string, string> = {
  satisfied: '满足',
  unsatisfied: '不满足',
  unknown: '无法判定',
}

export const conditionResultTypes: Record<string, 'success' | 'danger' | 'info'> = {
  satisfied: 'success',
  unsatisfied: 'danger',
  unknown: 'info',
}

export const reviewOperationLabels: Record<string, string> = {
  supplement: '补充说明',
  approve: '批准',
  defer: '暂缓',
}

export const reviewStatusLabels: Record<string, string> = {
  pending: '待审核',
  approved: '已批准',
  deferred: '已暂缓',
}

export const scheduleStatusLabels: Record<string, string> = {
  unscheduled: '未排期',
  scheduled: '已排期',
  waitlisted: '候补',
}

export const actionStatusLabels: Record<string, string> = {
  not_configured: '平台未配置',
  not_executed: '未执行',
  running: '执行中',
  succeeded: '成功',
  failed: '失败',
  uncertain: '待核实',
}

export const actionStatusTypes: Record<string, 'info' | 'primary' | 'success' | 'danger' | 'warning'> = {
  not_configured: 'info',
  not_executed: 'info',
  running: 'primary',
  succeeded: 'success',
  failed: 'danger',
  uncertain: 'warning',
}

export const eventTypeLabels: Record<string, string> = {
  batch_started: '评估启动',
  node_started: '节点开始',
  node_succeeded: '节点成功',
  node_failed: '节点失败',
  node_retrying: '节点重试',
  candidate_resumed: '候选人恢复',
  review_saved: '审核保存',
  resume_queued: '恢复排队',
  resume_succeeded: '恢复成功',
  resume_failed: '恢复失败',
  slot_created: '时段创建',
  slot_updated: '时段修改',
  slot_deleted: '时段删除',
  schedule_planned: '排期完成',
  action_started: '动作开始',
  action_succeeded: '动作成功',
  action_failed: '动作失败',
  action_not_configured: '动作未配置',
  action_retry: '动作重试',
  action_reconciled: '动作核实',
  job_published: '岗位发布',
}

export const eventLevelTypes: Record<string, 'info' | 'warning' | 'danger'> = {
  info: 'info',
  warning: 'warning',
  error: 'danger',
}
