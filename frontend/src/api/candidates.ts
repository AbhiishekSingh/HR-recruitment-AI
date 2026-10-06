import client from './client'
import type { UploadBatchResult, IngestionStatusRow, CandidateOverview, FingerprintMatch, Candidate, SectorCount, ResumeSearchResult, DuplicateCheckResult } from '../types'

export interface CandidateFilters {
  search?: string
  sector?: string
  skills?: string          // comma-separated; backend matches ANY of these
  min_experience?: number
  max_experience?: number
  qualification?: string   // free-text match against degree/institution
  /** attention | processing | unclassified | duplicates */
  status?: string
}

export async function listCandidates(filters: CandidateFilters = {}): Promise<Candidate[]> {
  const params: Record<string, string> = {}
  if (filters.search) params.search = filters.search
  if (filters.sector) params.sector = filters.sector
  if (filters.skills) params.skills = filters.skills
  if (filters.min_experience !== undefined && filters.min_experience !== null) params.min_experience = String(filters.min_experience)
  if (filters.max_experience !== undefined && filters.max_experience !== null) params.max_experience = String(filters.max_experience)
  if (filters.qualification) params.qualification = filters.qualification
  if (filters.status) params.status = filters.status
  const { data } = await client.get<Candidate[]>('/candidates', { params })
  return data
}

export async function getCandidate(id: string): Promise<Candidate> {
  const { data } = await client.get<Candidate>(`/candidates/${id}`)
  return data
}

export async function createCandidate(payload: {
  name: string; email: string; phone: string; current_company: string
  experience_years: number; resume_skills: string[]; resume_summary: string
  sector?: string | null; position_role?: string | null
}): Promise<Candidate> {
  const { data } = await client.post<Candidate>('/candidates', payload)
  return data
}

/** Live counts per sector, for the sector-cards landing page. Sectors with
 *  zero classified candidates simply aren't in the response. */
export async function getSectorCounts(): Promise<SectorCount[]> {
  const { data } = await client.get<SectorCount[]>('/candidates/sectors/counts')
  return data
}

/** Manually sets/corrects a candidate's sector and/or position_role,
 *  overriding whatever the AI extraction classified (or filling it in for a
 *  candidate that has none). Guarded server-side against being clobbered by
 *  a later re-ingestion. */
export async function updateCandidateClassification(
  id: string,
  payload: { sector?: string | null; position_role?: string | null }
): Promise<Candidate> {
  const { data } = await client.patch<Candidate>(`/candidates/${id}`, payload)
  return data
}

/** Full-text search across every candidate's resume (see the backend
 *  endpoint's docstring for what it does and doesn't match against). Empty
 *  query returns no results rather than the whole database. */
export async function searchResumes(query: string): Promise<ResumeSearchResult[]> {
  const q = query.trim()
  if (!q) return []
  const { data } = await client.get<ResumeSearchResult[]>('/candidates/search-resumes', { params: { q } })
  return data
}

/** Run before actually uploading `file`, so the caller can ask the
 *  recruiter what to do when a likely-same candidate is already on file
 *  (see the endpoint's docstring for the email/phone matching logic).
 *  Read-only -- creates/changes nothing. */
export async function checkDuplicateResume(file: File): Promise<DuplicateCheckResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await client.post<DuplicateCheckResult>('/candidates/check-duplicate', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** `sector`, when given, pins every candidate created by this call to that
 *  sector (bypassing AI auto-classification for it) -- either one of the
 *  suggested built-in sectors or a brand-new name the recruiter typed via
 *  SectorPicker; see the backend endpoint's docstring for why this is safe
 *  against a later re-ingestion overwriting it. */
export async function bulkUploadResumes(files: File[], jobId?: string, sector?: string): Promise<Candidate[]> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  if (jobId) formData.append('job_id', jobId)
  if (sector) formData.append('sector', sector)

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
  const ext = candidate.file_path?.split('.').pop() || 'pdf'
  await openResumeBlob(candidate.id, candidate.name, ext)
}

/** Same "open the resume file" behavior as viewCandidateResume, but for a
 *  ResumeSearchResult row, which doesn't carry file_path (search results
 *  only need enough to render a match line, not the full Candidate shape)
 *  -- so the extension is read from the response's Content-Type instead of
 *  guessed from a filename. Used by clicking a matched line in the resume
 *  full-text search panel. */
export async function openCandidateResumeById(candidateId: string, candidateName: string): Promise<void> {
  const { data, headers } = await client.get(`/candidates/${candidateId}/resume`, { responseType: 'blob' })
  const contentType = String(headers['content-type'] || '')
  const ext = contentType.includes('pdf') ? 'pdf' : contentType.includes('wordprocessingml') ? 'docx' : 'pdf'
  await openResumeBlob(candidateId, candidateName, ext, data)
}

async function openResumeBlob(candidateId: string, candidateName: string, ext: string, preloaded?: Blob): Promise<void> {
  const data = preloaded ?? (await client.get(`/candidates/${candidateId}/resume`, { responseType: 'blob' })).data
  const filename = `${candidateName.replace(/\s+/g, '_')}.${ext}`

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
/** One small batch (about 10 files) of a large bulk upload. Invalid files
 *  come back in `failed` with a reason instead of failing the request. */
export async function uploadResumeBatch(files: File[], jobId?: string, sector?: string): Promise<UploadBatchResult> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  if (jobId) formData.append('job_id', jobId)
  if (sector) formData.append('sector', sector)
  const { data } = await client.post<UploadBatchResult>('/candidates/upload-batch', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

/** Live AI-processing status for the given candidate ids. */
export async function getIngestionStatus(ids: string[]): Promise<IngestionStatusRow[]> {
  if (ids.length === 0) return []
  const { data } = await client.post<IngestionStatusRow[]>('/candidates/ingestion-status', { ids })
  return data
}

/** Re-run AI processing on already-saved resumes (failed / needs review / stuck). */
export async function reprocessCandidates(ids: string[]): Promise<{ queued: number; skipped: string[] }> {
  const { data } = await client.post('/candidates/reprocess', { ids })
  return data
}

/** Totals for the Candidates landing page (sector cards + status cards). */
export async function getCandidateOverview(): Promise<CandidateOverview> {
  const { data } = await client.get<CandidateOverview>('/candidates/overview')
  return data
}

/** Soft-deletes a candidate (their history stays in the database). */
export async function deleteCandidate(id: string): Promise<void> {
  await client.delete(`/candidates/${id}`)
}

/** Recruiter confirmed this is not a duplicate -- clears the flag. */
export async function clearDuplicateFlag(id: string): Promise<Candidate> {
  const { data } = await client.patch<Candidate>(`/candidates/${id}`, { clear_duplicate: true })
  return data
}

/** Which of these SHA-256 file fingerprints are already on file. */
export async function checkFingerprints(hashes: string[]): Promise<FingerprintMatch[]> {
  if (hashes.length === 0) return []
  const { data } = await client.post<FingerprintMatch[]>('/candidates/check-fingerprints', { hashes })
  return data
}
