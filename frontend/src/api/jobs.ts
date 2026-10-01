import client from './client'
import type { JobPosting } from '../types'

export interface JobPostingCreatePayload {
  company_id: string
  title: string
  locations: string[]
  budget_min: number
  budget_max: number
  experience_min: number
  experience_max: number
  max_notice_days: number
  required_skills: string[]
  raw_text?: string
}

export async function listJobs(companyId?: string): Promise<JobPosting[]> {
  const { data } = await client.get<JobPosting[]>('/jobs', { params: companyId ? { company_id: companyId } : {} })
  return data
}

export async function getJob(id: string): Promise<JobPosting> {
  const { data } = await client.get<JobPosting>(`/jobs/${id}`)
  return data
}

export async function createJob(payload: JobPostingCreatePayload): Promise<JobPosting> {
  const { data } = await client.post<JobPosting>('/jobs', payload)
  return data
}

/** JD Active/Inactive toggle -- "Open" = Active, "Closed" = Inactive. */
export async function setJobStatus(id: string, status: 'Open' | 'Closed'): Promise<JobPosting> {
  const { data } = await client.patch<JobPosting>(`/jobs/${id}/status`, { status })
  return data
}