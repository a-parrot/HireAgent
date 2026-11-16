import { http } from './http'
import type {
  Batch,
  Paged,
  ActionApproval,
  ActionPreviewResult,
  PreviewInput,
  ScheduleResult,
  Slot,
  SlotInput,
  Candidate,
  Reservation,
} from './types'

export async function listSlots(batchId: string): Promise<Slot[]> {
  const { data } = await http.get(`/batches/${batchId}/slots`)
  return data
}

export async function createSlot(batchId: string, body: SlotInput): Promise<Slot> {
  const { data } = await http.post(`/batches/${batchId}/slots`, body)
  return data
}

export async function patchSlot(slotId: string, body: SlotInput): Promise<Slot> {
  const { data } = await http.patch(`/slots/${slotId}`, body)
  return data
}

export async function deleteSlot(slotId: string): Promise<void> {
  await http.delete(`/slots/${slotId}`)
}

export async function generateSchedule(batchId: string): Promise<ScheduleResult> {
  const { data } = await http.post(`/batches/${batchId}/schedule`)
  return data
}

export async function getSchedule(batchId: string): Promise<ScheduleResult> {
  const { data } = await http.get(`/batches/${batchId}/schedule`)
  return data
}

export async function getActionPreview(reservationId: string): Promise<ActionPreviewResult> {
  const { data } = await http.get(`/reservations/${reservationId}/action-preview`)
  return data
}

export async function putActionPreview(
  reservationId: string,
  body: PreviewInput,
): Promise<unknown> {
  const { data } = await http.put(`/reservations/${reservationId}/action-preview`, body)
  return data
}

export async function approveActions(reservationId: string, body: ActionApproval): Promise<ActionPreviewResult> {
  const { data } = await http.post(`/reservations/${reservationId}/approve-actions`, body)
  return data
}

export async function retryActions(reservationId: string): Promise<ActionPreviewResult> {
  const { data } = await http.post(`/reservations/${reservationId}/retry-actions`)
  return data
}

export async function reconcileActions(reservationId: string): Promise<ActionPreviewResult> {
  const { data } = await http.post(`/reservations/${reservationId}/reconcile-actions`)
  return data
}

export interface SchedulingRecord extends Batch { job_name: string; interview_count: number; scheduled_count: number }
export async function listSchedulingRecords(page: number, pageSize: number): Promise<Paged<SchedulingRecord>> {
  return (await http.get('/scheduling-records', { params: { page, page_size: pageSize } })).data
}

export interface InterviewRow {
  candidate: Candidate
  job_name: string
  reservation: Reservation | null
  slot: Slot | null
  editable: boolean
}
export interface InterviewPage extends Paged<InterviewRow> {
  counts: { all: number; pending: number; scheduled: number }
}
export async function listInterviews(params: Record<string, unknown>, signal?: AbortSignal): Promise<InterviewPage> {
  return (await http.get('/interviews', { params, signal })).data
}
export async function bookInterviews(body: SlotInput & { candidate_ids: string[]; gap_minutes: number }): Promise<{ scheduled: number }> {
  return (await http.post('/interviews', body)).data
}
export async function rescheduleInterview(id: string, body: SlotInput & { preview_version: number }): Promise<void> {
  await http.patch(`/interviews/${id}`, body)
}
export async function cancelInterview(id: string, previewVersion: number): Promise<void> {
  await http.delete(`/interviews/${id}`, { params: { preview_version: previewVersion } })
}
