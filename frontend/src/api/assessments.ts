import client from './client'
import type { AssessmentScored } from '../types'

export async function getJobPipeline(jobId: string): Promise<AssessmentScored[]> {
  const { data } = await client.get<AssessmentScored[]>(`/jobs/${jobId}/pipeline`)
  return data
}

export async function getCandidateAssessments(candidateId: string): Promise<AssessmentScored[]> {
  const { data } = await client.get<AssessmentScored[]>(`/candidates/${candidateId}/assessments`)
  return data
}

export async function startAssessment(candidateId: string, jobId: string): Promise<AssessmentScored> {
  const { data } = await client.post<AssessmentScored>('/assessments/start', { candidate_id: candidateId, job_id: jobId })
  return data
}

export interface ScreeningFormValues {
  current_ctc: number | null
  expected_ctc: number | null
  notice_period_days: number | null
  current_location: string
  preferred_location: string
  cv_relevance: string
  experience_match: string
  skills_match: string
  industry_alignment: string
  job_stability: string
  communication: string
  interest_level: string
  notice_fit: string
  salary_alignment: string
  role_notes: string
  skills_notes: string
  achievements: string
  reason_for_change: string
  red_flags: string
  final_status: string
  recruiter_remarks: string
  approved_by: string
  submitted_to: string
}

export async function submitScreening(assessmentId: string, payload: ScreeningFormValues): Promise<AssessmentScored> {
  const { data } = await client.patch<AssessmentScored>(`/assessments/${assessmentId}`, payload)
  return data
}

export async function setAssessmentStatus(assessmentId: string, status: string): Promise<AssessmentScored> {
  const { data } = await client.post<AssessmentScored>(`/assessments/${assessmentId}/status`, { status })
  return data
}

export async function sendToClient(assessmentIds: string[]): Promise<{ sent: number }> {
  const { data } = await client.post('/assessments/send-to-client', { assessment_ids: assessmentIds })
  return data
}

export async function submitClientFeedback(assessmentId: string, feedback: string): Promise<AssessmentScored> {
  const { data } = await client.post<AssessmentScored>(`/assessments/${assessmentId}/client-feedback`, { feedback })
  return data
}