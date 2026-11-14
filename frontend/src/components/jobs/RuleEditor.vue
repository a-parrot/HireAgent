<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  modelValue: Record<string, unknown> | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, unknown> | null): void
}>()

const text = ref(props.modelValue ? JSON.stringify(props.modelValue, null, 2) : '')
const errorMessage = ref('')

watch(
  () => props.modelValue,
  (value) => {
    const current = text.value.trim() ? tryParse(text.value).value : null
    if (JSON.stringify(value ?? null) !== JSON.stringify(current)) {
      text.value = value ? JSON.stringify(value, null, 2) : ''
      errorMessage.value = ''
    }
  },
)

function tryParse(raw: string): { value: Record<string, unknown> | null; error?: string } {
  try {
    const parsed = JSON.parse(raw)
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { value: null, error: '规则必须是 JSON 对象' }
    }
    return { value: parsed as Record<string, unknown> }
  } catch (e) {
    return { value: null, error: (e as Error).message }
  }
}

function validate(): boolean {
  if (!text.value.trim()) {
    errorMessage.value = ''
    emit('update:modelValue', null)
    return true
  }
  const { value, error } = tryParse(text.value)
  if (error) {
    errorMessage.value = error
    return false
  }
  errorMessage.value = ''
  emit('update:modelValue', value)
  return true
}

function format() {
  const { value, error } = tryParse(text.value)
  if (error) {
    errorMessage.value = error
    return
  }
  text.value = JSON.stringify(value, null, 2)
  errorMessage.value = ''
}

defineExpose({
  /** 校验并返回规则对象；非法时返回 undefined 并提示错误 */
  getValid(): Record<string, unknown> | null | undefined {
    if (!text.value.trim()) return null
    const { value, error } = tryParse(text.value)
    if (error) {
      errorMessage.value = error
      return undefined
    }
    return value
  },
})
</script>

<template>
  <div>
    <div class="rule-editor-toolbar">
      <el-button size="small" @click="format">格式化</el-button>
      <el-button size="small" type="primary" plain @click="validate">校验 JSON</el-button>
      <span v-if="errorMessage" class="rule-error">{{ errorMessage }}</span>
    </div>
    <el-input
      v-model="text"
      type="textarea"
      :rows="18"
      class="mono"
      placeholder='粘贴岗位评估规则 JSON，例如：{"hard_conditions": {...}, "dimensions": [...], "review_threshold": 70, "recommend_threshold": 80, "sort_priority": [{"field": "total_score", "direction": "desc"}]}'
    />
    <div class="muted" style="margin-top: 6px">
      规则结构：hard_conditions（all/any 树，叶子含 id/description/evidence_requirement）、dimensions（id/name/max_score/criteria/evidence_requirement，上限合计 100）、review_threshold、recommend_threshold、sort_priority（以 total_score 开始，引用有效维度，全部 desc）。
    </div>
  </div>
</template>

<style scoped>
.rule-editor-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.rule-error {
  color: var(--el-color-danger);
  font-size: 12px;
}
</style>
