export interface ConditionNode extends Record<string, unknown> {
  id?: string
  description?: string
  evidence_requirement?: string
  operator?: 'all' | 'any'
  items?: ConditionNode[]
}
export interface ScoreDimension extends Record<string, unknown> {
  id: string
  name: string
  max_score: number
  criteria: string
  evidence_requirement: string
}
export interface JobRules extends Record<string, unknown> {
  hard_conditions: ConditionNode
  dimensions: ScoreDimension[]
  review_threshold: number
  recommend_threshold: number
  sort_priority: { field: string; direction: 'desc' }[]
}
export function newId(prefix: string): string {
  const value = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}_${Math.random().toString(36).slice(2)}`
  return `${prefix}_${value.replaceAll('-', '')}`
}
export function newCondition(): ConditionNode {
  return { id: newId('condition'), description: '', evidence_requirement: '' }
}
export function newDimension(max = 10): ScoreDimension {
  return { id: newId('dimension'), name: '', max_score: max, criteria: '', evidence_requirement: '' }
}
export function readRules(value: Record<string, unknown> | null): JobRules {
  const copy = JSON.parse(JSON.stringify(value ?? {})) as Record<string, unknown>
  const condition = (node: unknown): ConditionNode => {
    if (!node || typeof node !== 'object') return { operator: 'all', items: [] }
    const item = node as ConditionNode
    if (Array.isArray(item.items)) return { ...item, operator: item.operator === 'any' ? 'any' : 'all', items: item.items.map(condition) }
    return { ...item, id: item.id || newId('condition'), description: item.description || '', evidence_requirement: item.evidence_requirement || '' }
  }
  const dimensions = Array.isArray(copy.dimensions) ? copy.dimensions.map((value) => {
    const d = value as Partial<ScoreDimension>
    return { ...d, id: d.id || newId('dimension'), name: d.name || '', max_score: Number(d.max_score ?? 0), criteria: d.criteria || '', evidence_requirement: d.evidence_requirement || '' }
  }) : []
  const root = condition(copy.hard_conditions)
  return {
    ...copy, hard_conditions: root.items ? root : { operator: 'all', items: [root] }, dimensions,
    review_threshold: typeof copy.review_threshold === 'number' ? copy.review_threshold : 60,
    recommend_threshold: typeof copy.recommend_threshold === 'number' ? copy.recommend_threshold : 75,
    sort_priority: Array.isArray(copy.sort_priority) ? copy.sort_priority as JobRules['sort_priority'] : [{ field: 'total_score', direction: 'desc' }],
  }
}
export function ruleIssues(rules: JobRules): string[] {
  const issues: string[] = []
  const ids: string[] = []
  const visit = (node: ConditionNode) => {
    if (node.items) {
      if (!node.items.length) issues.push('请添加至少一条硬条件，或删除空的条件组')
      node.items.forEach(visit)
    } else {
      if (!node.description?.trim()) issues.push('请填写硬条件内容')
      if (node.id) ids.push(node.id)
    }
  }
  visit(rules.hard_conditions)
  if (new Set(ids).size !== ids.length) issues.push('硬条件标识重复')
  if (!rules.dimensions.length) issues.push('请添加至少一个评分维度')
  if (new Set(rules.dimensions.map(d => d.id)).size !== rules.dimensions.length) issues.push('评分维度标识重复')
  rules.dimensions.forEach((d, i) => {
    if (!d.name.trim()) issues.push(`请填写第 ${i + 1} 个评分维度的名称`)
    if (!Number.isInteger(d.max_score) || d.max_score <= 0) issues.push(`第 ${i + 1} 个维度的满分须为正整数`)
    if (!d.criteria.trim()) issues.push(`请填写「${d.name || `维度 ${i + 1}`}」的得分标准`)
  })
  if (rules.dimensions.reduce((sum, d) => sum + (d.max_score || 0), 0) !== 100) issues.push('评分维度满分合计须为 100 分')
  if (!(rules.review_threshold >= 0 && rules.review_threshold < rules.recommend_threshold && rules.recommend_threshold <= 100)) issues.push('阈值须满足：0 ≤ 人工复核最低分 < 推荐面试最低分 ≤ 100')
  const fields = rules.sort_priority.map(s => s.field)
  if (fields[0] !== 'total_score' || new Set(fields).size !== fields.length || fields.some(f => f !== 'total_score' && !rules.dimensions.some(d => d.id === f))) issues.push('排期优先级引用了无效或重复的维度')
  return [...new Set(issues)]
}
