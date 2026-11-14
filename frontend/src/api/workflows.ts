import { http, downloadFile } from './http'
import type { EventPage } from './types'

export async function listBatchEvents(
  batchId: string,
  afterId?: string,
  limit?: number,
): Promise<EventPage> {
  const { data } = await http.get(`/batches/${batchId}/events`, {
    params: { after_id: afterId, limit },
  })
  return data
}

export function exportBatch(batchId: string, format: 'json' | 'csv'): void {
  downloadFile(`/api/batches/${batchId}/export?format=${format}`)
}

export function exportCandidate(id: string, format: 'json' | 'csv'): void {
  downloadFile(`/api/candidates/${id}/export?format=${format}`)
}
