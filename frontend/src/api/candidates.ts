import client from './client'
import type { Candidate } from '../types'

export async function listCandidates(search?: string): Promise<Candidate[]> {
  const { data } = await client.get<Candidate[]>('/candidates', { params: search ? { search } : {} })
  return data
}

export async function getCandidate(id: string): Promise<Candidate> {
  const { data } = await client.get<Candidate>(`/candidates/${id}`)
  return data
}

export async function createCandidate(payload: {
  name: string; email: string; phone: string; current_company: string
  experience_years: number; resume_skills: string[]; resume_summary: string
}): Promise<Candidate> {
  const { data } = await client.post<Candidate>('/candidates', payload)
  return data
}

export async function bulkUploadResumes(files: File[], jobId?: string): Promise<Candidate[]> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  if (jobId) formData.append('job_id', jobId)

  const { data } = await client.post<Candidate[]>('/candidates/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}
