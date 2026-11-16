import { http } from './http'
import type { Candidate, Review } from './types'

export interface EvaluationRow extends Candidate {
  manual_review?: Review | null
  job_id: string; job_name: string; score_bucket: string
  recommend_threshold: number; review_threshold: number
}
export interface EvaluationResults {
  items: EvaluationRow[]; total: number
  counts: Record<string, number>
  thresholds: { recommend: number; review: number }[]
}
export async function listEvaluations(params: Record<string, unknown>, signal?: AbortSignal): Promise<EvaluationResults> {
  return (await http.get('/evaluations', { params, signal })).data
}

export async function deleteEvaluations(ids: string[]): Promise<{ deleted: string[]; already_deleted: string[] }> {
  return (await http.post('/evaluations/delete', { candidate_ids: ids })).data
}
export async function autoScheduleEvaluations(body: { job_id?: string; candidate_ids?: string[]; starts_at?: string; interviewer?: string; timezone?: string }): Promise<{ eligible: number; scheduled: number; waitlisted: number; created_slots?: number; new_reservations?: number }> {
  return (await http.post('/evaluations/auto-schedule', body, { timeout: 120000 })).data
}
