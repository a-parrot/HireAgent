import { http } from './http'
import type { CandidateDetail, Review, ReviewRequest } from './types'

export async function getCandidate(id: string): Promise<CandidateDetail> {
  const { data } = await http.get(`/candidates/${id}`)
  return data
}

export async function submitReview(id: string, body: ReviewRequest): Promise<Review> {
  const { data } = await http.post(`/candidates/${id}/review`, body)
  return data
}
