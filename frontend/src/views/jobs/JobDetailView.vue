<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import RuleEditor from '@/components/jobs/RuleEditor.vue'
import { getJob, patchJob, publishJob } from '@/api/jobs'
import { ApiError } from '@/api/http'
import { formatTime } from '@/utils/format'
import type { JobDetail, JobRuleVersion } from '@/api/types'

const route = useRoute()
const jobId = route.params.id as string

const loading = ref(false)
const job = ref<JobDetail | null>(null)

const editing = ref(false)
const saving = ref(false)
const publishDialogVisible = ref(false)
const publishing = ref(false)
const snapshotVisible = ref(false)
const snapshotContent = ref('')
const snapshotTitle = ref('')

const editForm = reactive({
  name: '',
  responsibilities: '',
  requirements: '',
  draft_rules: null as Record<string, unknown> | null,
})

const ruleEditorRef = ref<InstanceType<typeof RuleEditor>>()
const publishForm = reactive({ operator_name: '' })

async function load() {
  loading.value = true
  try {
    job.value = await getJob(jobId)
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    loading.value = false
  }
}

onMounted(load)

function startEdit() {
  const j = job.value
  if (!j) return
  editForm.name = j.name
  editForm.responsibilities = j.responsibilities ?? ''
  editForm.requirements = j.requirements ?? ''
  editForm.draft_rules = j.draft_rules
  editing.value = true
}

async function saveEdit() {
  if (!job.value) return
  const parsed = ruleEditorRef.value?.getValid()
  if (parsed === undefined) {
    ElMessage.error('评估规则 JSON 格式错误，请先修正')
    return
  }
  saving.value = true
  try {
    await patchJob(jobId, {
      draft_version: job.value.draft_version,
      name: editForm.name,
      responsibilities: editForm.responsibilities || null,
      requirements: editForm.requirements || null,
      draft_rules: parsed,
    })
    ElMessage.success('草稿已保存')
    editing.value = false
    await load()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    saving.value = false
  }
}

async function confirmPublish() {
  if (!publishForm.operator_name.trim()) {
    ElMessage.warning('请填写操作人姓名')
    return
  }
  if (!job.value) return
  publishing.value = true
  try {
    await publishJob(jobId, {
      draft_version: job.value.draft_version,
      operator_name: publishForm.operator_name.trim(),
    })
    ElMessage.success('规则版本已发布')
    publishDialogVisible.value = false
    publishForm.operator_name = ''
    await load()
  } catch (err) {
    if (err instanceof ApiError) ElMessage.error(err.message)
  } finally {
    publishing.value = false
  }
}

function viewSnapshot(version: JobRuleVersion) {
  snapshotTitle.value = `规则版本 v${version.version_no} 快照`
  snapshotContent.value = JSON.stringify(version.rule_snapshot, null, 2)
  snapshotVisible.value = true
}
</script>

<template>
  <div v-loading="loading">
    <template v-if="job">
      <el-card class="page-card">
        <template #header>
          <div class="toolbar" style="margin-bottom: 0">
            <span class="section-title" style="margin: 0">岗位信息</span>
            <div class="spacer" />
            <el-tag :type="job.status === 'active' ? 'success' : 'info'">
              {{ job.status === 'active' ? '启用' : '已停用' }}
            </el-tag>
            <el-tag type="primary" effect="plain">草稿版本 v{{ job.draft_version }}</el-tag>
            <el-button v-if="!editing && job.status === 'active'" size="small" @click="startEdit">
              编辑草稿
            </el-button>
            <el-button
              v-if="job.status === 'active'"
              size="small"
              type="primary"
              @click="publishDialogVisible = true"
            >发布规则</el-button>
          </div>
        </template>

        <el-descriptions v-if="!editing" :column="1" border>
          <el-descriptions-item label="岗位名称">{{ job.name }}</el-descriptions-item>
          <el-descriptions-item label="岗位职责">
            <span style="white-space: pre-wrap">{{ job.responsibilities ?? '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="任职要求">
            <span style="white-space: pre-wrap">{{ job.requirements ?? '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="草稿规则">
            <div v-if="job.draft_rules" class="json-view">{{ JSON.stringify(job.draft_rules, null, 2) }}</div>
            <span v-else class="muted">未定义（发布前必须先定义规则）</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-form v-else label-width="90px">
          <el-form-item label="岗位名称">
            <el-input v-model="editForm.name" maxlength="200" />
          </el-form-item>
          <el-form-item label="岗位职责">
            <el-input v-model="editForm.responsibilities" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="任职要求">
            <el-input v-model="editForm.requirements" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="评估规则">
            <RuleEditor ref="ruleEditorRef" v-model="editForm.draft_rules" />
          </el-form-item>
          <el-form-item>
            <el-button :loading="saving" type="primary" @click="saveEdit">保存草稿</el-button>
            <el-button @click="editing = false; load()">取消</el-button>
            <span class="muted">保存成功后草稿版本自动 +1</span>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card>
        <template #header><span class="section-title" style="margin: 0">已发布规则版本</span></template>
        <el-table :data="job.versions" border>
          <el-table-column label="版本号" width="90">
            <template #default="{ row }">v{{ row.version_no }}</template>
          </el-table-column>
          <el-table-column label="发布人" prop="published_by" width="140">
            <template #default="{ row }">{{ row.published_by ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="发布时间" width="180">
            <template #default="{ row }">{{ formatTime(row.published_at) }}</template>
          </el-table-column>
          <el-table-column label="版本 ID" width="140">
            <template #default="{ row }"><span class="mono">{{ row.id }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" @click="viewSnapshot(row)">查看快照</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-dialog v-model="publishDialogVisible" title="发布规则版本" width="480px">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="发布时会校验规则结构：维度上限合计 100、ID 唯一、阈值合法；发布成功后草稿版本自动推进。"
          style="margin-bottom: 16px"
        />
        <el-form label-width="90px">
          <el-form-item label="草稿版本">
            <el-tag>v{{ job?.draft_version }}</el-tag>
          </el-form-item>
          <el-form-item label="操作人" required>
            <el-input v-model="publishForm.operator_name" maxlength="128" placeholder="招聘人员姓名" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="publishDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="publishing" @click="confirmPublish">确认发布</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="snapshotVisible" :title="snapshotTitle" width="760px">
        <div class="json-view">{{ snapshotContent }}</div>
      </el-dialog>
    </template>
  </div>
</template>
