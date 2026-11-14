import { http } from './http'
import type {
  Job,
  JobCreateRequest,
  JobDetail,
  JobPatchRequest,
  JobRuleVersion,
  Paged,
  PublishRequest,
} from './types'

export async function listJobs(page: number, pageSize: number, filters: { keyword?: string; status?: string } = {}): Promise<Paged<Job>> {
  const { data } = await http.get('/jobs', { params: { page, page_size: pageSize, ...filters } })
  return data
}

export async function createJob(body: JobCreateRequest): Promise<Job> {
  const { data } = await http.post('/jobs', body)
  return data
}

export async function getJob(id: string): Promise<JobDetail> {
  const { data } = await http.get(`/jobs/${id}`)
  return data
}

export async function patchJob(id: string, body: JobPatchRequest): Promise<Job> {
  const { data } = await http.patch(`/jobs/${id}`, body)
  return data
}

export async function publishJob(id: string, body: PublishRequest): Promise<JobRuleVersion> {
  const { data } = await http.post(`/jobs/${id}/publish`, body)
  return data
}

export async function disableJob(id: string): Promise<Job> {
  const { data } = await http.post(`/jobs/${id}/disable`)
  return data
}

export async function enableJob(id: string): Promise<Job> {
  const { data } = await http.post(`/jobs/${id}/enable`)
  return data
}

export async function deleteJob(id: string): Promise<void> {
  await http.delete(`/jobs/${id}`)
}
