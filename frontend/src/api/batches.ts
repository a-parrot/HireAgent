import { http } from './http'
import type { Batch, BatchDetail, Candidate, Paged } from './types'

export async function listBatches(page: number, pageSize: number): Promise<Paged<Batch>> {
  const { data } = await http.get('/batches', { params: { page, page_size: pageSize } })
  return data
}

export async function getBatch(id: string): Promise<BatchDetail> {
  const { data } = await http.get(`/batches/${id}`)
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
  return `/api/files/${fileId}/preview`
}

export async function retryCandidate(id: string): Promise<{ candidate_id: string; status: string }> {
  const { data } = await http.post(`/candidates/${id}/retry`)
  return data
}
