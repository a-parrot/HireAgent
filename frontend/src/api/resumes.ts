import { http } from './http'
import type { Job, Paged } from './types'
export interface WorkspaceJob extends Job { resume_count: number; parsed_count: number }
export interface EvaluationSummary { id: string; processing_status: string; total_score: number | null; recommendation: string | null; error_message?: string | null; queued?: boolean }
export interface Resume { latest_evaluation?: EvaluationSummary | null; id: string; file_id: string; display_name: string; file_type: string; sha256: string; parse_status: string; parse_error: string | null; size_bytes: number; page_count: number | null; added_at: string; parser_name?: string }
export interface ImportItem { filename: string; result: 'accepted' | 'duplicate' | 'rejected'; message: string; sha256?: string }
export interface ImportResult { items: ImportItem[]; accepted: number; duplicates: number; rejected: number }
export interface ResumeDetail extends Resume { sha256_verified: boolean; pages: { page_no: number; text: string }[]; import_task: { status: string; current_node: string | null; node_progress: { name: string; status: string; error?: string }[]; error_message: string | null } | null; evaluations: { id: string; batch_id: string; name: string; processing_status: string; recommendation: string | null; total_score: number | null; created_at: string }[] }
export async function workspaceJobs(): Promise<{ items: WorkspaceJob[] }> { return (await http.get('/resume-workspace/jobs')).data }
export async function jobResumes(jobId: string, params: { page: number; page_size: number; keyword?: string; status?: string }): Promise<Paged<Resume>> { return (await http.get(`/jobs/${jobId}/resumes`, { params })).data }
export async function uploadResumes(jobId: string, files: File[]): Promise<ImportResult> {
  const form = new FormData()
  for (const file of files) form.append('files', file, file.name)
  // HTTPS/localhost supports browser-side hashing. Server hashing and original integrity checks always run.
  if (globalThis.crypto?.subtle) {
    for (const file of files) {
      const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
      form.append('sha256s', Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join(''))
    }
  }
  return (await http.post(`/jobs/${jobId}/resumes`, form, { timeout: 300000 })).data
}
export async function resumeDetail(job: string, id: string): Promise<ResumeDetail> { return (await http.get(`/jobs/${job}/resumes/${id}`)).data }
export async function removeResume(job: string, id: string) { await http.delete(`/jobs/${job}/resumes/${id}`) }
export async function retryImport(job: string, id: string) { await http.post(`/jobs/${job}/resumes/${id}/retry`) }
export async function evaluateResumes(job: string, ids: string[], version: string, requestId: string): Promise<{ status: string; accepted: number; already_started: boolean }> {
  return (await http.post(`/jobs/${job}/evaluate`, { resume_ids: ids, rule_version_id: version, request_id: requestId })).data
}
