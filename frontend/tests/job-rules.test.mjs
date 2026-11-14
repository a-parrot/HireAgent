import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { readRules, ruleIssues, newDimension } from '../src/utils/jobRules.ts'

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
  assert(ruleIssues(rules).some(message => message.includes('评分维度')))
  rules.dimensions.push({ ...newDimension(100), name: '自定义经验', criteria: '按证据评分' })
  rules.hard_conditions.items.push({ id: 'experience', description: '相关经验' })
  assert.deepEqual(ruleIssues(rules), [])
  rules.recommend_threshold = rules.review_threshold
  assert(ruleIssues(rules).some(message => message.includes('阈值')))
})
