import client from './client'
import type { JobPosting, JDParseResult, JDAttachResult, SkillGroup } from '../types'

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
  /** from parseJdFile(): attaches the uploaded JD file to the new job */
  jd_upload_token?: string | null
  /** from parseJdFile(): structured requirements incl. nice-to-have skills */
  requirements?: Record<string, unknown> | null
  /** scoring settings: must / nice / not-scored groups with synonyms */
  skill_groups?: SkillGroup[]
  related_titles?: string[]
}

export type JobPostingUpdatePayload = Partial<Omit<JobPostingCreatePayload, 'company_id' | 'jd_upload_token'>>

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

/** Reads an uploaded JD file with AI and returns form pre-fill values.
 *  Nothing is created until createJob() is called with the upload_token. */
export async function parseJdFile(file: File): Promise<JDParseResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await client.post<JDParseResult>('/jobs/parse-jd', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180_000,
  })
  return data
}

/** Attaches/replaces the JD file of an existing job; also returns the values
 *  read from it so HR can choose to update the job's fields. */
export async function attachJdFile(jobId: string, file: File): Promise<JDAttachResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await client.put<JDAttachResult>(`/jobs/${jobId}/jd`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180_000,
  })
  return data
}

export async function updateJob(id: string, payload: JobPostingUpdatePayload): Promise<JobPosting> {
  const { data } = await client.patch<JobPosting>(`/jobs/${id}`, payload)
  return data
}

/** Opens the original JD file (PDF in a new tab, Word downloads) -- fetched
 *  as an authenticated blob, same as resumes/company documents. */
export async function viewJdFile(job: JobPosting): Promise<void> {
  const { data } = await client.get(`/jobs/${job.id}/jd`, { responseType: 'blob' })
  const name = job.jd_file_name || `${job.title.replace(/\s+/g, '_')}_JD.pdf`
  const isPdf = name.toLowerCase().endsWith('.pdf')
  const blobUrl = window.URL.createObjectURL(isPdf ? new Blob([data], { type: 'application/pdf' }) : data)
  if (isPdf) {
    window.open(blobUrl, '_blank')
  } else {
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = name
    document.body.appendChild(link)
    link.click()
    link.remove()
  }
  setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60_000)
}
