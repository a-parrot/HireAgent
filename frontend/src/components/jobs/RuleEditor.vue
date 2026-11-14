<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import ConditionEditor from './ConditionEditor.vue'
import { newDimension, readRules, ruleIssues } from '@/utils/jobRules'
const props = withDefaults(defineProps<{ modelValue: Record<string, unknown> | null; readOnly?: boolean }>(), { readOnly: false })
const emit = defineEmits<{ (e: 'update:modelValue', value: Record<string, unknown>): void }>()
const rules = ref(readRules(props.modelValue))
const showErrors = ref(false)
const editorElement = ref<HTMLElement>()
watch(() => props.modelValue, value => { rules.value = readRules(value); showErrors.value = false })
const total = computed(() => rules.value.dimensions.reduce((sum, d) => sum + (d.max_score || 0), 0))
const issues = computed(() => ruleIssues(rules.value))
const sortDimensions = computed({
  get: () => rules.value.sort_priority.filter(s => s.field !== 'total_score').map(s => s.field),
  set: fields => { rules.value.sort_priority = [{ field: 'total_score', direction: 'desc' }, ...fields.map(field => ({ field, direction: 'desc' as const }))] },
})
function removeDimension(index: number) {
  const removed = rules.value.dimensions.splice(index, 1)[0]
  if (removed) sortDimensions.value = sortDimensions.value.filter(id => id !== removed.id)
}
function move(index: number, direction: number) {
  const target = index + direction
  if (target < 0 || target >= rules.value.dimensions.length) return
  const items = rules.value.dimensions
  ;[items[index], items[target]] = [items[target]!, items[index]!]
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
    <section class="rule-section">
      <div class="section-heading"><div><h3>01 · 必须满足的条件</h3><p>信息不足会转人工复核，不会直接淘汰候选人。</p></div></div>
      <ConditionEditor v-model="rules.hard_conditions" :read-only="readOnly" />
    </section>
    <section class="rule-section">
      <div class="section-heading"><div><h3>02 · 评分维度与得分标准</h3><p>为每一项写清楚如何给分，AI 将按这些标准评分并引用证据。</p></div><el-tag :type="total === 100 ? 'success' : 'warning'" size="large">满分合计 {{ total }} / 100</el-tag></div>
      <el-progress :percentage="Math.min(total, 100)" :show-text="false" :status="total === 100 ? 'success' : total > 100 ? 'exception' : undefined" :stroke-width="6" />
      <el-empty v-if="!rules.dimensions.length" :image-size="55" description="添加第一个评分维度，定义这个岗位看重的能力" />
      <article v-for="(dimension, index) in rules.dimensions" :key="dimension.id" class="dimension-card">
        <div class="dimension-header"><span class="number">{{ index + 1 }}</span><strong v-if="readOnly">{{ dimension.name }}</strong><el-input v-else v-model="dimension.name" :aria-label="`维度 ${index + 1} 名称`" placeholder="维度名称，例如：海外项目经验" maxlength="100" /><span class="score-label">满分</span><strong v-if="readOnly">{{ dimension.max_score }} 分</strong><el-input-number v-else v-model="dimension.max_score" :min="1" :max="100" :precision="0" :aria-label="`维度 ${index + 1} 满分`" controls-position="right" style="width: 108px; flex-shrink: 0" /></div>
        <div class="dimension-fields"><label>得分标准<span v-if="!readOnly">必填</span></label><p v-if="readOnly" class="pre-wrap">{{ dimension.criteria || '尚未填写' }}</p><el-input v-else v-model="dimension.criteria" type="textarea" :rows="3" :aria-label="`维度 ${index + 1} 得分标准`" placeholder="例如：参与项目得 1–5 分；独立负责关键阶段得 6–10 分；主导完整交付得 11–15 分。请根据本维度满分填写。" /><label>证据要求</label><p v-if="readOnly" class="pre-wrap muted">{{ dimension.evidence_requirement || '依据岗位相关原文证据' }}</p><el-input v-else v-model="dimension.evidence_requirement" :aria-label="`维度 ${index + 1} 证据要求`" placeholder="例如：项目名称、个人职责、交付阶段与成果（选填）" /></div>
        <div v-if="!readOnly" class="dimension-actions"><el-button text size="small" :disabled="index === 0" @click="move(index, -1)">上移</el-button><el-button text size="small" :disabled="index === rules.dimensions.length - 1" @click="move(index, 1)">下移</el-button><span class="grow" /><el-button text type="danger" size="small" @click="removeDimension(index)">删除维度</el-button></div>
      </article>
      <el-button v-if="!readOnly" class="add-dimension" plain @click="rules.dimensions.push(newDimension(Math.max(1, 100 - total)))">＋ 添加评分维度</el-button>
    </section>
    <section class="rule-section">
      <div class="section-heading"><div><h3>03 · 总分筛选阈值</h3><p>分数由服务端求和，阈值决定推荐、人工复核或暂缓。</p></div></div>
      <div class="threshold-fields"><div><label>推荐面试最低分</label><strong v-if="readOnly">{{ rules.recommend_threshold }} 分</strong><el-input-number v-else v-model="rules.recommend_threshold" :min="1" :max="100" :precision="0" aria-label="推荐面试最低分" /></div><div><label>人工复核最低分</label><strong v-if="readOnly">{{ rules.review_threshold }} 分</strong><el-input-number v-else v-model="rules.review_threshold" :min="0" :max="99" :precision="0" aria-label="人工复核最低分" /></div></div>
      <div class="routing-preview"><span class="recommend">≥ {{ rules.recommend_threshold }} 分：推荐面试</span><span class="review">{{ rules.review_threshold }} 至低于 {{ rules.recommend_threshold }} 分：人工复核</span><span>低于 {{ rules.review_threshold }} 分：暂缓</span></div>
      <p class="hint">硬条件明确不满足时不直接推荐；关键信息缺失转人工。推荐后仍需人工批准。</p>
    </section>
    <section class="rule-section">
      <div class="section-heading"><div><h3>04 · 排期优先级</h3><p>先按总分排序，同分时按下方选择顺序比较；最后按候选人编号稳定排序。</p></div></div>
      <div v-if="readOnly" class="priority-preview">总分 <span v-for="id in sortDimensions" :key="id"> → {{ rules.dimensions.find(d => d.id === id)?.name || id }}</span> → 候选人编号</div>
      <el-select v-else v-model="sortDimensions" multiple placeholder="选择同分时优先比较的维度（可选）" style="width: 100%"><el-option v-for="(d, index) in rules.dimensions" :key="d.id" :label="d.name || `维度 ${index + 1}`" :value="d.id" /></el-select>
    </section>
    <el-alert v-if="showErrors && issues.length" type="warning" :closable="false" show-icon title="发布前还需完善以下内容"><ul class="issues"><li v-for="issue in issues" :key="issue">{{ issue }}</li></ul></el-alert>
    <p v-if="!readOnly" class="hint">可以先保存未完成的草稿。发布后，新评估批次自动使用这套标准；修改不影响历史批次。</p>
  </div>
</template>
<style scoped>
.rule-editor { width: 100%; min-width: 0; }.rule-section + .rule-section { margin-top: 26px; padding-top: 24px; border-top: 1px solid var(--ha-border); }.section-heading { display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 14px; }h3 { font-size: 15px; margin: 0 0 5px; color: var(--ha-text); }.section-heading p,.hint { color: var(--ha-text-muted); font-size: 12px; line-height: 1.7; margin: 0; }.dimension-card { border: 1px solid var(--ha-border); border-radius: 10px; margin-top: 14px; overflow: hidden; }.dimension-header { display: flex; gap: 10px; align-items: center; padding: 12px 14px; background: #f5f7fa; }.number { display: inline-flex; align-items: center; justify-content: center; border-radius: 50%; width: 26px; height: 26px; background: var(--el-color-primary-light-9); color: var(--ha-primary); font-size: 12px; flex-shrink: 0; }.score-label { white-space: nowrap; font-size: 12px; color: var(--ha-text-secondary); }.dimension-fields { padding: 4px 16px 14px; }.dimension-fields label { display: flex; gap: 8px; align-items: center; font-size: 12px; font-weight: 600; margin: 12px 0 6px; }.dimension-fields label span { color: var(--ha-text-muted); font-weight: 400; }.dimension-actions { display: flex; padding: 0 10px 8px; }.grow { flex: 1; }.add-dimension { width: 100%; margin-top: 12px; border-style: dashed; }.threshold-fields { display: flex; gap: 30px; flex-wrap: wrap; }.threshold-fields > div { display: flex; flex-direction: column; gap: 10px; }.threshold-fields label { font-size: 13px; color: var(--ha-text-secondary); }.routing-preview { display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0 10px; }.routing-preview span { background: #f1f3f5; color: #757e79; padding: 6px 10px; border-radius: 6px; font-size: 12px; }.routing-preview .recommend { background: #eaf5ee; color: #317454; }.routing-preview .review { background: #fff5e2; color: #a17122; }.pre-wrap { white-space: pre-wrap; margin: 0; line-height: 1.7; }.priority-preview { font-size: 13px; line-height: 1.8; }.issues { margin: 6px 0; padding-left: 18px; font-size: 12px; }.rule-editor > .hint { margin-top: 16px; }@media (max-width: 600px) { .dimension-header { flex-wrap: wrap; }.section-heading { align-items: flex-start; } }
</style>
