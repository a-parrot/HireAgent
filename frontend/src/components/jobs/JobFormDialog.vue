<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import RuleEditor from './RuleEditor.vue'
import { createJob } from '@/api/jobs'
import { ApiError } from '@/api/http'

const emit = defineEmits<{ (e: 'saved', jobId: string): void }>()

const visible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  responsibilities: '',
  requirements: '',
  draft_rules: null as Record<string, unknown> | null,
})

const ruleEditorRef = ref<InstanceType<typeof RuleEditor>>()

const rules: FormRules = {
  name: [{ required: true, message: '请输入岗位名称', trigger: 'blur' }],
}

function open() {
  form.name = ''
  form.responsibilities = ''
  form.requirements = ''
  form.draft_rules = null
  visible.value = true
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const parsed = ruleEditorRef.value?.getValid()
  if (parsed === undefined) {
    ElMessage.error('评估规则 JSON 格式错误，请先修正')
    return
  }
  submitting.value = true
  try {
    const job = await createJob({
      name: form.name,
      responsibilities: form.responsibilities || null,
      requirements: form.requirements || null,
      draft_rules: parsed,
    })
    ElMessage.success('岗位草稿已创建')
    visible.value = false
    emit('saved', job.id)
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <el-dialog v-model="visible" title="新建岗位草稿" width="720px" destroy-on-close>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
      <el-form-item label="岗位名称" prop="name">
        <el-input v-model="form.name" maxlength="200" placeholder="如：高级后端工程师" />
      </el-form-item>
      <el-form-item label="岗位职责">
        <el-input v-model="form.responsibilities" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="任职要求">
        <el-input v-model="form.requirements" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="评估规则">
        <RuleEditor ref="ruleEditorRef" v-model="form.draft_rules" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">创建草稿</el-button>
    </template>
  </el-dialog>
</template>
