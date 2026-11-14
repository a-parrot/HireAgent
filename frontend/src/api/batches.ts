import { http } from './http'
import type { Batch, BatchDetail, Candidate, Paged, RunResult } from './types'

export async function listBatches(page: number, pageSize: number): Promise<Paged<Batch>> {
  const { data } = await http.get('/batches', { params: { page, page_size: pageSize } })
  return data
}

export interface CreateBatchParams {
  job_id: string
  rule_version_id: string
  files: File[]
  name?: string
}

export async function createBatch(params: CreateBatchParams): Promise<Batch & { imported_count: number }> {
  const form = new FormData()
  form.append('job_id', params.job_id)
  form.append('rule_version_id', params.rule_version_id)
  for (const file of params.files) {
    form.append('files', file, file.name)
  }
  if (params.name) form.append('name', params.name)
  const { data } = await http.post('/batches', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
  })
  return data
}

export async function getBatch(id: string): Promise<BatchDetail> {
  const { data } = await http.get(`/batches/${id}`)
  return data
}

export async function runBatch(id: string): Promise<RunResult> {
  const { data } = await http.post(`/batches/${id}/run`)
  return data
}

export interface CandidateQuery {
  batch_id: string
  status?: string
  recommendation?: string
  page?: number
  page_size?: number
}

export async function listCandidates(query: CandidateQuery): Promise<Paged<Candidate>> {
  const { data } = await http.get('/candidates', { params: query })
  return data
}

export function pdfUrl(fileId: string): string {
  return `/api/files/${fileId}`
}

export async function retryCandidate(id: string): Promise<{ candidate_id: string; status: string }> {
  const { data } = await http.post(`/candidates/${id}/retry`)
  return data
}
