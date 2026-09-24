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

/** Attaches a resume to a candidate who has none, or replaces the existing
 *  one — same endpoint handles both "attach" and "reupload". */
export async function uploadCandidateResume(candidateId: string, file: File): Promise<Candidate> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await client.put<Candidate>(`/candidates/${candidateId}/resume`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function deleteCandidateResume(candidateId: string): Promise<Candidate> {
  const { data } = await client.delete<Candidate>(`/candidates/${candidateId}/resume`)
  return data
}

/** Downloads the resume as a Blob and triggers the browser's normal
 *  save/open behavior — done as an authenticated fetch (not a plain <a
 *  href>) because the endpoint requires the JWT bearer token like every
 *  other API call. */
export async function viewCandidateResume(candidate: Candidate): Promise<void> {
  const { data } = await client.get(`/candidates/${candidate.id}/resume`, { responseType: 'blob' })
  const ext = candidate.file_path?.split('.').pop() || 'pdf'
  const filename = `${candidate.name.replace(/\s+/g, '_')}.${ext}`

  const blobUrl = window.URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = blobUrl
  // PDFs open in a new tab (browsers render them inline); anything else downloads.
  if (ext.toLowerCase() === 'pdf') {
    window.open(blobUrl, '_blank')
  } else {
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
  }
  setTimeout(() => window.URL.revokeObjectURL(blobUrl), 30_000)
}