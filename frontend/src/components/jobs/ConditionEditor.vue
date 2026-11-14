<script setup lang="ts">
import { newCondition, newId, type ConditionNode } from '@/utils/jobRules'
const props = withDefaults(defineProps<{ modelValue: ConditionNode; root?: boolean; readOnly?: boolean }>(), { root: true, readOnly: false })
const emit = defineEmits<{ (e: 'update:modelValue', value: ConditionNode): void; (e: 'remove'): void }>()
function update(key: string, value: unknown) { emit('update:modelValue', { ...props.modelValue, [key]: value }) }
function replaceChild(index: number, value: ConditionNode) {
  const items = [...(props.modelValue.items ?? [])]; items[index] = value; update('items', items)
}
function add(group = false) { update('items', [...(props.modelValue.items ?? []), group ? { id: newId('group'), operator: 'any', items: [newCondition()] } : newCondition()]) }
function removeChild(index: number) { update('items', props.modelValue.items?.filter((_, i) => i !== index)) }
</script>
<template>
  <div v-if="modelValue.items" class="condition-group">
    <div class="group-header">
      <span class="group-label">{{ root ? '条件关系' : '条件组' }}</span>
      <span v-if="readOnly">{{ modelValue.operator === 'any' ? '满足任意一条' : '满足全部条件' }}</span>
      <el-select v-else :model-value="modelValue.operator" style="width: 160px" @update:model-value="update('operator', $event)"><el-option label="满足全部条件" value="all" /><el-option label="满足任意一条" value="any" /></el-select>
      <div class="grow" /><el-button v-if="!root && !readOnly" type="danger" text size="small" @click="emit('remove')">删除条件组</el-button>
    </div>
    <div v-if="!modelValue.items.length" class="condition-empty">{{ readOnly ? '暂无硬条件' : '添加岗位必须满足的条件；“或”关系可以使用条件组。' }}</div>
    <ConditionEditor v-for="(child, index) in modelValue.items" :key="child.id || index" :model-value="child" :root="false" :read-only="readOnly" @update:model-value="replaceChild(index, $event)" @remove="removeChild(index)" />
    <div v-if="!readOnly" class="group-actions"><el-button plain size="small" @click="add()">＋ 添加条件</el-button><el-button text size="small" @click="add(true)">＋ 添加“或”条件组</el-button></div>
  </div>
  <div v-else class="condition-leaf">
    <div v-if="readOnly"><strong>{{ modelValue.description || '未填写条件' }}</strong><p v-if="modelValue.evidence_requirement" class="evidence-hint">证据要求：{{ modelValue.evidence_requirement }}</p></div>
    <template v-else><div class="leaf-main"><el-input :model-value="modelValue.description" aria-label="硬条件内容" placeholder="例如：具备项目或团队管理经历" @update:model-value="update('description', $event)" /><el-button type="danger" text @click="emit('remove')">删除</el-button></div><el-input :model-value="modelValue.evidence_requirement" aria-label="硬条件证据要求" placeholder="需要哪些简历证据（选填）" @update:model-value="update('evidence_requirement', $event)" /></template>
  </div>
</template>
<style scoped>
.condition-group { border: 1px solid var(--ha-border); border-radius: var(--ha-radius); padding: 14px; background: #f5f7fa; min-width: 0; }.condition-group .condition-group { margin-top: 10px; background: #fff; }.group-header,.leaf-main,.group-actions { display: flex; gap: 10px; align-items: center; }.grow { flex: 1; }.group-label { font-size: 13px; color: #606266; }.condition-leaf { margin-top: 10px; padding: 12px; border-radius: var(--ha-radius); background: #fff; border: 1px solid #ebeef5; }.leaf-main { margin-bottom: 8px; }.group-actions { margin-top: 12px; flex-wrap: wrap; }.condition-empty,.evidence-hint { font-size: 13px; color: #909399; margin: 12px 0 0; line-height: 1.6; }
</style>
