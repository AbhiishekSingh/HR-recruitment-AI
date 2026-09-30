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
  // Auto-classified from the candidate's most recent resume job during
  // ingestion (or set manually via PATCH /candidates/{id}). Null until a
  // resume has been processed, or if extraction hasn't run yet.
  sector: string | null
  position_role: string | null
}

// Mirrors the backend's fixed sector allow-list (validation.py's
// VALID_SECTORS, also mirrored in prompts/resume_extraction.py's
// SECTOR_LIST) -- used for the sector-cards landing page and the manual
// override dropdown. Update all three together whenever a sector is added
// or renamed.
export const SECTOR_LIST = [
  'IT', 'HR', 'Sales', 'Marketing', 'Finance', 'Operations',
  'Customer Support', 'Legal', 'Design', 'Healthcare', 'Education',
  'Engineering', 'Manufacturing', 'Banking & Insurance',
  'Retail & E-commerce', 'Hospitality & Travel',
  'Construction & Real Estate', 'Logistics & Supply Chain',
  'Media & Entertainment', 'Government & Public Sector', 'Agriculture',
  'Other',
] as const

export interface SectorCount {
  sector: string
  count: number
}

// POST /candidates/check-duplicate -- run before an actual upload, so the
// recruiter can be asked what to do about a likely-same person already on
// file rather than silently getting a duplicate candidate row.
export interface DuplicateMatch {
  candidate_id: string
  name: string
  email: string
  phone: string
  status: string
  added_on: string
  matched_on: ('email' | 'phone')[]
}

export interface DuplicateCheckResult {
  // false when no pre-check was possible at all (e.g. a scanned PDF with no
  // text layer) -- distinct from checked=true with an empty matches list,
  // which means the check ran and genuinely found nothing.
  checked: boolean
  matches: DuplicateMatch[]
}

// GET /candidates/search-resumes -- full-text search across resume raw
// text (not just the structured fields the directory's regular filters
// search). `highlights` are [start, end) character offsets of each match
// within `text`, computed server-side so the frontend just wraps those
// spans rather than re-implementing the (case-insensitive) matching.
export interface ResumeSearchMatch {
  line_number: number
  text: string
  highlights: [number, number][]
}

export interface ResumeSearchResult {
  candidate_id: string
  candidate_name: string
  sector: string | null
  position_role: string | null
  status: string
  has_resume_file: boolean
  matches: ResumeSearchMatch[]
  has_more_matches: boolean
}

export interface AssessmentScored {
  id: string
  candidate_id: string
  // Joined in from the Candidate record by the backend's pipeline query,
  // so the frontend never has to fetch the candidate list separately
  // just to label a row.
  candidate_name: string
  candidate_email: string
  candidate_experience_years: number
  candidate_current_company: string
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