<script setup lang="ts">
import { auth } from '@/stores/auth'
import { reactive, ref, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import RuleEditor from './RuleEditor.vue'
import { createJob, patchJob, publishJob } from '@/api/jobs'
import { ApiError } from '@/api/http'
import type { Job } from '@/api/types'
const emit = defineEmits<{ (e: 'saved', jobId: string): void }>()
const visible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const createdJob = ref<Job | null>(null)
const form = reactive({ name: '', responsibilities: '', requirements: '', draft_rules: null as Record<string, unknown> | null, operator_name: auth.user?.display_name || '' })
const ruleEditorRef = ref<InstanceType<typeof RuleEditor>>()
const rules: FormRules = { name: [{ required: true, whitespace: true, message: '请输入岗位名称', trigger: 'blur' }] }
async function open() {
  createdJob.value = null
  Object.assign(form, { name: '', responsibilities: '', requirements: '', draft_rules: null, operator_name: auth.user?.display_name || '' })
  visible.value = true
  await nextTick()
  formRef.value?.clearValidate()
}
async function close() {
  if (submitting.value) return
  if (form.name.trim() || createdJob.value) {
    try { await ElMessageBox.confirm(createdJob.value ? '已保存的草稿会保留，是否关闭编辑？' : '关闭后将放弃尚未保存的内容。', '关闭新建岗位', { confirmButtonText: '关闭', cancelButtonText: '继续填写' }) } catch { return }
  }
  visible.value = false
  if (createdJob.value) emit('saved', createdJob.value.id)
}
async function submit(publish: boolean) {
  if (!await formRef.value?.validate().catch(() => false)) return
  const parsed = ruleEditorRef.value?.getValid(publish)
  if (!parsed) { ElMessage.warning('请完善评分规则后发布，也可以先保存草稿'); return }
  if (publish && !form.operator_name.trim()) { ElMessage.warning('请填写发布人姓名'); return }
  submitting.value = true
  try {
    const body = { name: form.name.trim(), responsibilities: form.responsibilities.trim() || null, requirements: form.requirements.trim() || null, draft_rules: parsed }
    const saved = createdJob.value
      ? await patchJob(createdJob.value.id, { ...body, draft_version: createdJob.value.draft_version })
      : await createJob(body)
    createdJob.value = saved
    if (publish) await publishJob(saved.id, { draft_version: saved.draft_version, operator_name: form.operator_name.trim() })
    ElMessage.success(publish ? '岗位已创建并发布，可用于简历评估' : '岗位草稿已保存')
    visible.value = false
    emit('saved', saved.id)
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(`${createdJob.value ? '草稿已保留。' : ''}${err.message}`)
  } finally { submitting.value = false }
}
defineExpose({ open })
</script>
<template>
  <el-dialog v-model="visible" title="新建岗位与评分规则" width="min(1040px, calc(100vw - 32px))" top="4vh" destroy-on-close :before-close="close" :close-on-click-modal="false" class="job-form-dialog">
    <el-alert v-if="createdJob" type="info" :closable="false" title="岗位草稿已保存，继续修改或重试发布不会重复创建。" style="margin-bottom: 18px" />
    <el-form ref="formRef" :model="form" :rules="rules" :disabled="submitting" label-position="top" scroll-to-error>
      <div class="basic-fields"><el-form-item label="岗位名称" prop="name"><el-input v-model="form.name" maxlength="200" show-word-limit placeholder="例如：高级后端工程师" /></el-form-item><div class="two-columns"><el-form-item label="岗位职责"><el-input v-model="form.responsibilities" type="textarea" :rows="3" placeholder="这个岗位主要负责什么？" /></el-form-item><el-form-item label="任职要求"><el-input v-model="form.requirements" type="textarea" :rows="3" placeholder="需要哪些工作经历和专业能力？" /></el-form-item></div></div>
      <RuleEditor ref="ruleEditorRef" v-model="form.draft_rules" />
      <el-form-item label="发布人" style="margin-top: 24px"><el-input v-model="form.operator_name" disabled maxlength="128" placeholder="创建并发布时填写；仅保存草稿无需填写" style="max-width: 360px" /></el-form-item>
    </el-form>
    <template #footer><div class="dialog-footer"><span class="muted">发布后，新的评估自动带入这套规则。</span><div><el-button :disabled="submitting" @click="close">取消</el-button><el-button :loading="submitting" @click="submit(false)">保存草稿</el-button><el-button type="primary" :loading="submitting" @click="submit(true)">创建并发布</el-button></div></div></template>
  </el-dialog>
</template>
<style scoped>
.basic-fields { margin-bottom: 20px; }.two-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }.dialog-footer { display: flex; justify-content: space-between; align-items: center; gap: 16px; text-align: left; }.dialog-footer > div { white-space: nowrap; }@media (max-width: 700px) { .two-columns { grid-template-columns: 1fr; gap: 0; }.dialog-footer { flex-wrap: wrap; } }
</style>
<style>.job-form-dialog .el-dialog__body { max-height: 70vh; overflow-y: auto; padding-right: 24px; }</style>
