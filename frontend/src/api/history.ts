import { http } from './http'
import type { Batch, Paged } from './types'

export interface ParseNode { name: string; status: string; started_at?: string; finished_at?: string; error?: string }
export interface ImportHistory {
  id: string; task_id: string; file_id: string; filename: string; status: string
  current_node: string | null; node_progress: ParseNode[] | null; error_message: string | null
  created_at: string; started_at: string | null; finished_at: string | null; has_snapshot: boolean
}
export interface ImportHistoryDetail extends ImportHistory {
  markdown: string | null; artifact_error: string | null; source_sha256: string
  artifact: { parser_name: string; parser_version: string; text_sha256: string; char_count: number } | null
}
export interface EvaluationHistory extends Batch { job_name: string; total: number; progress: Record<string, number> }
export async function listImportHistory(params: Record<string, unknown>, signal?: AbortSignal): Promise<Paged<ImportHistory>> { return (await http.get('/history/imports', { params, signal })).data }
export async function getImportHistory(id: string): Promise<ImportHistoryDetail> { return (await http.get(`/history/imports/${id}`)).data }
export async function listEvaluationHistory(params: Record<string, unknown>, signal?: AbortSignal): Promise<Paged<EvaluationHistory>> { return (await http.get('/history/evaluations', { params, signal })).data }
