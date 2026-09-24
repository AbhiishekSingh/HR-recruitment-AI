export interface User {
  id: string
  name: string
  email: string
  role: string
}

export interface Company {
  id: string
  name: string
  industry: string
  contact_name: string
  contact_email: string
  gst_number: string
  tier: string
  document_path: string | null
  onboarded_on: string
}

export interface JobPosting {
  id: string
  company_id: string
  title: string
  locations: string[]
  budget_min: number
  budget_max: number
  experience_min: number
  experience_max: number
  max_notice_days: number
  required_skills: string[]
  status: string
  opened_on: string
}

export interface Candidate {
  id: string
  name: string
  email: string
  phone: string
  current_company: string
  experience_years: number
  resume_skills: string[]
  resume_summary: string
  file_path: string | null
  status: string // queued | extracting | embedding | ready | failed | needs_review
  added_on: string
}

export interface AssessmentScored {
  id: string
  candidate_id: string
  // Joined in from the Candidate record by the backend's pipeline query,
  // so the frontend never has to fetch the candidate list separately
  // just to label a row.
  candidate_name: string
  candidate_email: string
  candidate_phone: string
  candidate_experience_years: number
  candidate_current_company: string
  candidate_file_path: string | null
  candidate_status: string // queued | extracting | embedding | ready | failed | needs_review
  job_id: string
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
  final_status: string // Pending Screening | Share to Client | Hold | Reject
  recruiter_remarks: string
  approved_by: string
  submitted_to: string
  screened: boolean
  sent_to_client: boolean
  client_feedback: string | null
  created_at: string
  // computed, not stored input:
  ai_score: number | null
  // "ai_pipeline" = real GPT-5 match score; "estimate" = matching hasn't
  // run yet for this candidate/job pair, this is the keyword-overlap
  // fallback. null only for the legacy case where no ai score exists at all.
  ai_source: 'ai_pipeline' | 'estimate' | null
  matched_skills: string[]
  missing_skills: string[]
  assessment_score: number | null
  final_score: number | null
  bucket: 'strong' | 'good' | 'weak' | 'notrec' | 'rejected' | 'pending'
  flags: Array<{ level: string; text: string }>
  adjustments: Array<{ text: string; value: number | null }>
}

export const BUCKET_LABELS: Record<string, string> = {
  strong: 'Strong Match',
  good: 'Good Match',
  weak: 'Weak Match',
  notrec: 'Not Recommended',
  rejected: 'Rejected',
  pending: 'Pending Screening',
}