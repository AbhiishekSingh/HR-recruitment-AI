import client from './client'
import type { Candidate, CandidateProfile } from '../types'

export async function uploadResumes(files: File[]): Promise<Candidate[]> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))

  const { data } = await client.post<Candidate[]>('/resumes/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function listCandidates(): Promise<Candidate[]> {
  const { data } = await client.get<Candidate[]>('/resumes')
  return data
}

export async function getCandidate(id: string): Promise<Candidate> {
  const { data } = await client.get<Candidate>(`/resumes/${id}`)
  return data
}

export async function getCandidateProfile(id: string): Promise<CandidateProfile> {
  const { data } = await client.get<CandidateProfile>(`/resumes/${id}/profile`)
  return data
}
