<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import { conditionContent, conditionWithContent, newCondition, newDimension, readEditorRules, ruleIssues, scoreWithContent } from '@/utils/jobRules'
const props = withDefaults(defineProps<{ modelValue: Record<string, unknown> | null; readOnly?: boolean }>(), { readOnly: false })
const emit = defineEmits<{ (e: 'update:modelValue', value: Record<string, unknown>): void }>()
const rules = ref(readEditorRules(props.modelValue))
const showErrors = ref(false)
const editorElement = ref<HTMLElement>()
watch(() => props.modelValue, value => { rules.value = readEditorRules(value); showErrors.value = false })
const conditions = computed(() => rules.value.hard_conditions.items!)
const total = computed(() => rules.value.dimensions.reduce((sum, item) => sum + (item.max_score || 0), 0))
const issues = computed(() => ruleIssues(rules.value))
function updateCondition(index: number, content: string) { conditions.value[index] = conditionWithContent(conditions.value[index]!, content) }
function updateScore(index: number, content: string) { rules.value.dimensions[index] = scoreWithContent(rules.value.dimensions[index]!, content) }
function removeScore(index: number) {
  const removed = rules.value.dimensions.splice(index, 1)[0]
  if (removed) rules.value.sort_priority = rules.value.sort_priority.filter(item => item.field !== removed.id)
}
function getValid(forPublish = false): Record<string, unknown> | undefined {
  showErrors.value = forPublish
  if (forPublish && issues.value.length) {
    nextTick(() => editorElement.value?.querySelector('.el-alert')?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
    return undefined
  }
  const value = JSON.parse(JSON.stringify(rules.value)) as Record<string, unknown>
  emit('update:modelValue', value)
  return value
}
defineExpose({ getValid, getIssues: () => issues.value })
</script>
<template>
  <div ref="editorElement" class="rule-editor">
    <section class="rule-section" aria-label="硬条件">
      <header class="section-header"><h3>硬条件</h3><el-button v-if="!readOnly" text type="primary" :icon="Plus" @click="conditions.push(newCondition())">添加硬条件</el-button></header>
      <div class="conditions-list">
        <div v-for="(condition, index) in conditions" :key="condition.id || index" class="condition-row">
          <span class="row-number">{{ index + 1 }}</span>
          <span v-if="readOnly" class="row-content">{{ conditionContent(condition) || '未填写' }}</span>
          <el-input v-else :model-value="conditionContent(condition)" :aria-label="`硬条件内容 ${index + 1}`" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" placeholder="输入硬条件，例如：具备项目管理经验" @update:model-value="updateCondition(index, $event)" />
          <el-button v-if="!readOnly" text type="danger" :icon="Delete" :aria-label="`删除硬条件 ${index + 1}`" @click="conditions.splice(index, 1)">删除</el-button>
        </div>
        <div v-if="!conditions.length" class="empty-row">暂无硬条件</div>
      </div>
    </section>
    <section class="rule-section" aria-label="匹配评分">
      <header class="section-header"><h3>匹配评分 <span class="total-score" :class="{ incomplete: total !== 100 }">合计 {{ total }} / 100 分</span></h3><el-button v-if="!readOnly" text type="primary" :icon="Plus" @click="rules.dimensions.push(newDimension(Math.max(1, 100 - total)))">添加评分项</el-button></header>
      <div class="score-table">
        <div class="score-row table-heading"><span>序号</span><span>评分内容</span><span>分值</span><span v-if="!readOnly">操作</span></div>
        <div v-for="(item, index) in rules.dimensions" :key="item.id" class="score-row" :class="{ 'is-readonly': readOnly }">
          <span class="row-number">{{ index + 1 }}</span>
          <span v-if="readOnly" class="row-content">{{ item.name || '未填写' }}</span>
          <el-input v-else :model-value="item.name" :aria-label="`评分内容 ${index + 1}`" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" placeholder="输入评分内容，例如：海外项目经验" @update:model-value="updateScore(index, $event)" />
          <span v-if="readOnly" class="score-value">{{ item.max_score }} 分</span>
          <el-input-number v-else v-model="item.max_score" :min="1" :max="100" :precision="0" :aria-label="`评分分值 ${index + 1}`" controls-position="right" />
          <el-button v-if="!readOnly" text type="danger" :icon="Delete" :aria-label="`删除评分项 ${index + 1}`" @click="removeScore(index)">删除</el-button>
        </div>
        <div v-if="!rules.dimensions.length" class="empty-row">暂无评分项</div>
      </div>
      <div class="score-thresholds">
        <div class="threshold-item"><label>推荐面试最低分</label><strong v-if="readOnly">{{ rules.recommend_threshold }} 分</strong><el-input-number v-else v-model="rules.recommend_threshold" :min="1" :max="100" :precision="0" aria-label="推荐面试最低分" controls-position="right" /></div>
        <div class="threshold-item"><label>人工复核最低分</label><strong v-if="readOnly">{{ rules.review_threshold }} 分</strong><el-input-number v-else v-model="rules.review_threshold" :min="0" :max="99" :precision="0" aria-label="人工复核最低分" controls-position="right" /></div>
      </div>
    </section>
    <el-alert v-if="showErrors && issues.length" type="warning" :closable="false" show-icon title="发布前还需完善以下内容"><ul class="issues"><li v-for="issue in issues" :key="issue">{{ issue }}</li></ul></el-alert>
  </div>
</template>
<style scoped>
.rule-editor { width: 100%; min-width: 0; }
.rule-section + .rule-section { margin-top: 24px; }
.section-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; min-height: 32px; }
h3 { font-size: 16px; font-weight: 600; color: var(--ha-text); margin: 0; display: flex; align-items: center; flex-wrap: wrap; gap: 14px; }
.total-score { color: var(--ha-text-secondary); font-size: 13px; font-weight: 400; }
.total-score.incomplete { color: #b88230; }
.conditions-list,.score-table { border: 1px solid var(--ha-border); border-radius: 6px; overflow: hidden; }
.condition-row { display: grid; grid-template-columns: 38px minmax(0, 1fr) 76px; align-items: center; gap: 12px; padding: 10px 14px; }
.condition-row:has(.row-content) { grid-template-columns: 38px minmax(0,1fr); }
.condition-row + .condition-row,.score-row + .score-row { border-top: 1px solid #ebeef5; }
.row-number { font-size: 13px; color: var(--ha-text-muted); text-align: center; }
.row-content { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; font-size: 14px; }
.score-row { display: grid; grid-template-columns: 38px minmax(0,1fr) 110px 76px; align-items: center; gap: 12px; padding: 10px 14px; }
.score-row.is-readonly { grid-template-columns: 38px minmax(0,1fr) 110px; }
.score-table:has(.is-readonly) .table-heading { grid-template-columns: 38px minmax(0,1fr) 110px; }
.table-heading { background: #f5f7fa; color: var(--ha-text-secondary); font-size: 13px; padding-top: 8px; padding-bottom: 8px; }
.table-heading > :first-child { text-align: center; }
.score-row .el-input-number { width: 110px; }
.score-value { font-size: 14px; }
.score-thresholds { display: flex; flex-wrap: wrap; gap: 16px 30px; margin-top: 16px; padding: 14px 16px; background: #f5f7fa; border-radius: 6px; }
.threshold-item { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--ha-text-secondary); }
.threshold-item .el-input-number { width: 110px; }
.empty-row { padding: 20px; text-align: center; color: var(--ha-text-muted); font-size: 13px; }
.el-alert { margin-top: 16px; }
.issues { margin: 6px 0; padding-left: 18px; font-size: 12px; }
@media(max-width:600px) { .condition-row { grid-template-columns: 24px minmax(0,1fr) 48px; gap: 6px; padding: 10px 8px; }.score-row { grid-template-columns: 24px minmax(0,1fr) 85px 48px; gap: 6px; padding: 10px 8px; }.score-row .el-input-number { width: 85px; }.score-row :deep(.el-button) { padding: 4px; }.score-row :deep(.el-button .el-icon),.condition-row :deep(.el-button .el-icon) { display: none; }.score-thresholds { padding: 12px; }.section-header .el-button { padding: 4px; } }
</style>
