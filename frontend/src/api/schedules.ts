import { http } from './http'
import type {
  ActionApproval,
  ActionPreviewResult,
  PreviewInput,
  ScheduleResult,
  Slot,
  SlotInput,
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
