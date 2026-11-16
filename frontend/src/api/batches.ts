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

export async function listCandidates(query: CandidateQuery, signal?: AbortSignal): Promise<Paged<Candidate>> {
  const { data } = await http.get('/candidates', { params: query, signal })
  return data
}

/** Load a batch without exceeding the API's 200-row page limit. */
export async function listBatchCandidates(batchId: string, signal?: AbortSignal): Promise<Candidate[]> {
  const items: Candidate[] = []
  for (let page = 1; ; page++) {
    const result = await listCandidates({ batch_id: batchId, page, page_size: 200 }, signal)
    items.push(...result.items)
    if (!result.items.length || page * 200 >= result.total) return items
  }
}

export function pdfUrl(fileId: string): string {
  return `/api/files/${fileId}/preview`
}

export async function retryCandidate(id: string): Promise<{ candidate_id: string; status: string }> {
  const { data } = await http.post(`/candidates/${id}/retry`)
  return data
}

export async function restoreCandidateReview(id: string): Promise<{ candidate_id: string; status: string }> {
  return (await http.post(`/candidates/${id}/restore-review`)).data
}
