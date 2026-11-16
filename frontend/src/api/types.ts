/** 后端 API 响应与请求类型定义（ID 均为十进制字符串） */

export interface Job {
  id: string
  code: string
  name: string
  responsibilities: string | null
  requirements: string | null
  draft_rules: Record<string, unknown> | null
  status: 'active' | 'disabled'
  draft_version: number
  deleted_at?: string | null
  latest_published_version?: number | null
  created_at: string
  updated_at: string
}

export interface JobRuleVersion {
  id: string
  job_id: string
  version_no: number
  rule_snapshot: Record<string, unknown>
  published_by: string | null
  published_at: string
}

export interface JobDetail extends Job {
  versions: JobRuleVersion[]
}

export interface Batch {
  id: string
  name: string
  job_id: string
  rule_version_id: string
  rule_snapshot: Record<string, unknown>
  status: 'pending' | 'running' | 'evaluation_done'
  started_at: string | null
  evaluation_completed_at: string | null
  created_at: string
  updated_at: string
}

export interface BatchProgress {
  pending: number
  running: number
  waiting_review: number
  completed: number
  failed: number
}

export interface BatchDetail extends Batch {
  progress: BatchProgress
  total: number
}

export interface Fact {
  fact_id: string
  type: string
  description: string
  evidence_ids: string[]
}

export interface Evidence {
  evidence_id: string
  file_id: string
  page_no: number | null
  block_id?: string | null
  quote: string
}

export interface ConditionResult {
  basis?: 'evidence' | 'not_found' | 'uncertain'
  blocking?: boolean
  condition_name?: string
  condition_id: string
  result: 'satisfied' | 'unsatisfied' | 'unknown'
  reason: string
  evidence_ids: string[]
}

export interface DimensionScore {
  dimension_name?: string
  max_score?: number
  matched?: boolean
  dimension_id: string
  score: number
  reason: string
  evidence_ids: string[]
}

export interface Candidate {
  id: string
  batch_id: string
  file_id: string
  original_filename: string
  workflow_id: string
  name: string | null
  contact_info: Record<string, unknown> | null
  processing_status: 'pending' | 'running' | 'waiting_review' | 'completed' | 'failed'
  current_node: string | null
  checkpoint_id: string | null
  extracted_facts: Fact[] | null
  evidence: Evidence[] | null
  hard_conditions: ConditionResult[] | null
  dimension_scores: DimensionScore[] | null
  total_score: number | null
  recommendation: 'recommended' | 'needs_review' | 'deferred' | null
  missing_fields: string[] | null
  risks: string[] | null
  review_notes: string[] | null
  needs_human_review: boolean
  model_id: string | null
  prompt_versions: Record<string, string> | null
  review_status: 'pending' | 'approved' | 'deferred'
  review_version: number
  schedule_status: 'unscheduled' | 'scheduled' | 'waitlisted'
  waitlist_reason: string | null
  retry_count: number
  error_node: string | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface Review {
  id: string
  candidate_id: string
  operation: 'supplement' | 'approve' | 'defer'
  review_version: number
  reason: string
  supplements: { source: string; description: string }[] | null
  operator_name: string
  resume_status: 'not_required' | 'pending' | 'succeeded' | 'failed'
  resume_error: string | null
  created_at: string
}

export interface Slot {
  id: string
  batch_id: string
  starts_at: string
  ends_at: string
  timezone: string
  interviewer: string | null
  created_at: string
  updated_at: string
}

export interface ActionRecord {
  id: string
  reservation_id: string
  action_type: 'meeting' | 'notification'
  idempotency_key: string
  status:
    | 'not_configured'
    | 'not_executed'
    | 'running'
    | 'succeeded'
    | 'failed'
    | 'uncertain'
  provider: string | null
  approved_preview_version: number | null
  request_snapshot: Record<string, unknown> | null
  response_data: Record<string, unknown> | null
  external_id: string | null
  meeting_url: string | null
  attempt_count: number
  last_error: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface ActionPreview {
  candidate_name: string | null
  recipient: string
  content: string
  starts_at: string
  ends_at: string
  timezone: string
  interviewer: string | null
}

export interface Reservation {
  id: string
  batch_id: string
  candidate_id: string
  slot_id: string
  priority_snapshot: { fields: string[]; key: (number | string)[] }
  preview_version: number
  action_preview: ActionPreview | null
  approved_preview_version: number | null
  approved_preview: Record<string, unknown> | null
  approved_by: string | null
  approved_at: string | null
  created_at: string
  updated_at: string
}

export interface RuleCondition {
  operator?: 'all' | 'any'
  id?: string
  description?: string
  items?: RuleCondition[]
}

export interface RuleSnapshot {
  evaluation_flow?: string
  hard_conditions?: RuleCondition
  dimensions?: { id: string; name: string; max_score: number }[]
}

export interface CandidateDetail extends Candidate {
  rule_snapshot?: RuleSnapshot
  deleted?: boolean
  job_id: string
  rule_version_id: string
  review_history: Review[]
  reservation: Reservation | null
  actions: ActionRecord[]
}

export interface BatchEvent {
  id: string
  batch_id: string
  candidate_id: string | null
  node_name: string | null
  event_type: string
  level: 'info' | 'warning' | 'error'
  attempt_count: number
  message: string
  details: Record<string, unknown> | null
  created_at: string
}

export interface ScheduleResult {
  reservations: Reservation[]
  waitlist: Candidate[]
}

export interface ActionPreviewResult {
  reservation: Reservation
  candidate_name: string | null
  slot: Slot
  actions: ActionRecord[]
  meeting_configured: boolean
  notification_configured: boolean
}

export interface RunResult {
  batch_id: string
  status: string
  already_started: boolean
}

export interface Paged<T> {
  items: T[]
  total: number
}

export interface EventPage {
  items: BatchEvent[]
  next_cursor: string
}

/* 请求类型 */

export interface JobCreateRequest {
  name: string
  responsibilities?: string | null
  requirements?: string | null
  draft_rules?: Record<string, unknown> | null
}

export interface JobPatchRequest {
  draft_version: number
  name?: string
  responsibilities?: string | null
  requirements?: string | null
  draft_rules?: Record<string, unknown> | null
}

export interface PublishRequest {
  draft_version: number
  operator_name: string
}

export interface ReviewRequest {
  operation: 'supplement' | 'approve' | 'defer'
  review_version: number
  reason?: string
  operator_name: string
  supplements?: { source: string; description: string }[] | null
}

export interface SlotInput {
  starts_at: string
  ends_at: string
  timezone?: string
  interviewer?: string | null
}

export interface PreviewInput {
  preview_version: number
  recipient: string
  content: string
}

export interface ActionApproval {
  preview_version: number
  operator_name: string
}
