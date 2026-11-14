import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { readRules, ruleIssues, newDimension, readEditorRules, conditionContent, conditionWithContent, scoreWithContent } from '../src/utils/jobRules.ts'

test('existing nested conditions, stable IDs and extra rule data survive form loading', () => {
  const source = JSON.parse(readFileSync(new URL('../../backend/app/conf/initial_job.json', import.meta.url), 'utf-8'))
  source.extra_config = { preserved: true }
  const rules = readRules(source)
  assert.deepEqual(ruleIssues(rules), [])
  assert.deepEqual(rules.hard_conditions, source.hard_conditions)
  assert.deepEqual(rules.extra_config, source.extra_config)
  rules.dimensions[0].name = 'edited'
  assert.notEqual(source.dimensions[0].name, 'edited')
})

test('a valid single condition is wrapped without changing its ID or meaning', () => {
  const leaf = { id: 'original-condition', description: '相关经验', evidence_requirement: '工作经历' }
  const rules = readRules({ hard_conditions: leaf })
  assert.equal(rules.hard_conditions.operator, 'all')
  assert.deepEqual(rules.hard_conditions.items, [leaf])
})

test('incomplete drafts stay editable but cannot pass publish validation', () => {
  const rules = readRules(null)
  assert(ruleIssues(rules).some(message => message.includes('硬条件')))
  assert(ruleIssues(rules).some(message => message.includes('评分')))
  rules.dimensions.push({ ...newDimension(100), name: '自定义经验', criteria: '按证据评分' })
  rules.hard_conditions.items.push({ id: 'experience', description: '相关经验' })
  assert.deepEqual(ruleIssues(rules), [])
  rules.recommend_threshold = rules.review_threshold
  assert(ruleIssues(rules).some(message => message.includes('阈值')))
})


test('compact condition rows preserve legacy OR semantics and IDs until edited', () => {
  const source = JSON.parse(readFileSync(new URL('../../backend/app/conf/initial_job.json', import.meta.url), 'utf-8'))
  const rules = readEditorRules(source)
  assert.deepEqual(rules.hard_conditions, source.hard_conditions)
  const group = rules.hard_conditions.items.find(node => node.operator === 'any')
  assert.equal(conditionContent(group), '8 年以上工作经验 或 5 年以上直接相关经验')
  const changed = conditionWithContent(group, '五年以上相关经验')
  assert.equal(changed.description, '五年以上相关经验')
  assert.equal(changed.items, undefined)
  assert.notEqual(changed.id, group.id)
  assert.deepEqual(group, source.hard_conditions.items[1])
  const rootOr = readEditorRules({ hard_conditions: group })
  assert.equal(rootOr.hard_conditions.operator, 'all')
  assert.deepEqual(rootOr.hard_conditions.items, [group])
})

test('editing scoring content updates the actual prompt criterion and preserves stable IDs', () => {
  const before = { ...newDimension(30), name: '旧名称', criteria: '旧标准', evidence_requirement: '旧证据要求' }
  const after = scoreWithContent(before, '主导三个海外项目')
  assert.equal(after.name, '主导三个海外项目')
  assert.equal(after.criteria, after.name)
  assert.equal(after.id, before.id)
  assert.equal(after.evidence_requirement, before.evidence_requirement)
  assert.equal(after.max_score, 30)
  assert.equal(before.criteria, '旧标准')
})
