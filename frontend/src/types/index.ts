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
  // Active/Inactive label only -- an inactive company still works normally.
  is_active: boolean
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
  raw_text: string
  // Original JD file (PDF/DOCX) uploaded by HR, viewable via "View JD".
  has_jd_file: boolean
  jd_file_name: string | null
  // Scoring settings in use (saved ones, or the automatic default).
  skill_groups: SkillGroup[]
  related_titles: string[]
  /** false = automatic groups built from required skills (not yet edited) */
  has_custom_groups: boolean
}

/** One scoring group: any one of its skills (or synonyms) in a resume counts
 *  as the whole group matched. "soft" groups are not scored. */
export interface SkillGroup {
  name: string
  type: 'must' | 'nice' | 'soft'
  skills: string[]
  synonyms: string[]
}

/** Values the AI read from an uploaded JD file. null / [] = not in the JD. */
export interface JDFormFields {
  title: string | null
  locations: string[]
  budget_min: number | null
  budget_max: number | null
  experience_min: number | null
  experience_max: number | null
  max_notice_days: number | null
  required_skills: string[]
  nice_to_have_skills: string[]
  skill_groups: SkillGroup[]
  related_titles: string[]
}

export interface JDParseResult {
  upload_token: string | null
  file_name: string
  fields: JDFormFields
  /** form fields the JD didn't provide -- highlighted for HR to fill */
  missing: string[]
  requirements: Record<string, unknown>
  raw_text: string
  /** set when the AI couldn't read the file -- fill the form manually */
  error: string | null
}

export interface JDAttachResult {
  job: JobPosting
  parse: JDParseResult
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
  // Plain-language reason when status is needs_review / failed.
  status_detail: string
  added_on: string
  // Auto-classified from the candidate's most recent resume job during
  // ingestion (or set manually via PATCH /candidates/{id}). Null until a
  // resume has been processed, or if extraction hasn't run yet.
  sector: string | null
  position_role: string | null
  // Set when this candidate's email/phone (or exact file) matches an
  // earlier candidate -- shown as "Possible duplicate of <name>".
  possible_duplicate_of: string | null
  possible_duplicate_of_name: string | null
  // In progress for 15+ minutes (worker/Redis probably down).
  stuck: boolean
}

/** GET /candidates/overview -- classified + needs_attention + processing +
 *  unclassified always add up to total. */
export interface CandidateOverview {
  total: number
  classified: number
  needs_attention: number
  processing: number
  unclassified: number
  duplicates: number
}

export type CandidateStatusFilter = 'attention' | 'processing' | 'unclassified' | 'duplicates'

export interface FingerprintMatch {
  hash: string
  candidate_id: string
  name: string
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

// --- Bulk resume upload (batched, with per-file results) ---

/** Mirrors the backend limit in candidates.py (MAX_RESUME_MB). */
export const MAX_RESUME_MB = 4

export interface UploadFailure {
  filename: string
  reason: string
}

export interface UploadBatchResult {
  created: Candidate[]
  failed: UploadFailure[]
}

export interface IngestionStatusRow {
  id: string
  name: string
  status: string // queued | extracting | embedding | ready | needs_review | failed
  status_detail: string
  stuck: boolean
  has_resume_file: boolean
}

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
  // Post-shortlist tracking (see PIPELINE_STAGES)
  stage: PipelineStage | ''
  submitted_on: string | null
  offered_ctc: number | null
  joining_date: string | null // YYYY-MM-DD
  invoice_raised: boolean
  invoice_date: string | null // YYYY-MM-DD
  created_at: string
  // computed, not stored input:
  ai_score: number | null
  // "ai_pipeline" = up-to-date AI score; "smart" = free smart score (no AI
  // call); "processing" = resume not processed yet.
  ai_source: 'ai_pipeline' | 'smart' | 'processing' | null
  matched_skills: string[]
  missing_skills: string[]
  // Free smart score -- always present -- with its breakdown and evidence.
  smart_score: number | null
  score_parts: ScorePart[]
  skill_evidence: SkillEvidence[]
  /** an AI score exists but the job settings or resume changed since */
  ai_stale: boolean
  ai_previous_score: number | null
  ai_strengths: string[]
  ai_gaps: string[]
  ai_recommendation: string | null
  assessment_score: number | null
  final_score: number | null
  bucket: 'strong' | 'good' | 'weak' | 'notrec' | 'rejected' | 'pending'
  flags: Array<{ level: string; text: string }>
  adjustments: Array<{ text: string; value: number | null }>
}

export interface ScorePart {
  key: string
  label: string
  weight: number
  /** 0-100, or null when there's no data for this part (left out of the score) */
  value: number | null
  detail: string
}

export interface SkillEvidence {
  group: string
  type: 'must' | 'nice' | 'soft'
  /** null for soft groups (not scored) */
  matched: boolean | null
  found: string | null
  where: 'skills' | 'resume' | null
}

export interface AIScoreRequest {
  mode: 'top' | 'above' | 'selected' | 'stale'
  count?: number
  min_score?: number
  candidate_ids?: string[]
  dry_run: boolean
}

export interface AIScoreResponse {
  to_score: number
  already_done: number
  not_ready: number
  candidate_ids: string[]
  cost_per_candidate_inr: number
  estimated_cost_inr: number
  estimated_cost_usd: number
  queued: boolean
}

export interface AIUsageReport {
  days: number
  usd_to_inr: number
  calls: number
  unpriced_calls: number
  total_usd: number
  total_inr: number
  by_task: { task: string; label: string; calls: number; cost_usd: number; cost_inr: number; input_tokens: number; output_tokens: number }[]
  by_job: { job_id: string; title: string; company: string; calls: number; cost_inr: number }[]
  by_day: { date: string; cost_inr: number }[]
}

export const BUCKET_LABELS: Record<string, string> = {
  strong: 'Strong Match',
  good: 'Good Match',
  weak: 'Weak Match',
  notrec: 'Not Recommended',
  rejected: 'Rejected',
  pending: 'Pending Screening',
}

// ---------------------------------------------------------------------------
// Recruitment tracking (shortlist -> submission -> interview -> selection ->
// joining -> invoice). Mirrors backend models/assessment.py PIPELINE_STAGES
// and models/follow_up.py FOLLOW_UP_TYPES / FOLLOW_UP_STATUSES.
// ---------------------------------------------------------------------------

export const PIPELINE_STAGES = [
  'Shortlisted', 'Submitted', 'Interview', 'Selected', 'Joined',
  'On Hold', 'Rejected', 'Offer Declined',
] as const
export type PipelineStage = typeof PIPELINE_STAGES[number]

/** Maps a stage to one of the three existing badge colours. */
export function stageBadgeVariant(stage: string): 'shortlist' | 'review' | 'pass' {
  if (stage === 'Selected' || stage === 'Joined') return 'shortlist'
  if (stage === 'Rejected' || stage === 'Offer Declined') return 'pass'
  return 'review'
}

export const FOLLOW_UP_TYPES = [
  'Screening Call', 'Interview - Round 1', 'Interview - Round 2',
  'Interview - HR', 'Client Interview', 'Offer Discussion',
  'Joining Confirmation', 'General Follow-up',
] as const

export const FOLLOW_UP_STATUSES = ['Scheduled', 'Completed', 'Rescheduled', 'Cancelled', 'No Show'] as const
export type FollowUpStatus = typeof FOLLOW_UP_STATUSES[number]

export interface ShortlistRow {
  assessment_id: string
  candidate_id: string
  candidate_name: string
  candidate_email: string
  candidate_phone: string
  job_id: string
  job_title: string
  job_status: string // Open (Active) | Closed (Inactive)
  company_id: string | null
  company_name: string
  company_active: boolean
  final_status: string
  stage: PipelineStage | ''
  submitted_to: string
  submitted_on: string | null
  current_ctc: number | null
  expected_ctc: number | null
  offered_ctc: number | null
  joining_date: string | null
  invoice_raised: boolean
  invoice_date: string | null
  next_follow_up_at: string | null
  next_follow_up_type: string | null
  overdue_follow_ups: number
  updated_at: string | null
}

export interface FollowUp {
  id: string
  assessment_id: string
  candidate_id: string
  job_id: string
  follow_up_type: string
  scheduled_at: string
  status: FollowUpStatus
  notes: string
  outcome: string
  created_by_name: string | null
  created_at: string
  completed_at: string | null
  // Earlier dates of this follow-up, newest first (empty if never rescheduled).
  previous_schedules: PreviousSchedule[]
  candidate_name: string
  job_title: string
  company_name: string
}

export interface PreviousSchedule {
  scheduled_at: string
  rescheduled_on: string | null
  reason: string
  by_name: string | null
}

export interface StageHistoryEntry {
  id: string
  assessment_id: string
  from_stage: string
  to_stage: string
  note: string
  changed_by_name: string | null
  changed_at: string
}

/** Display label for a JD's stored status ("Open"/"Closed"). */
export function jobActiveLabel(status: string): 'Active' | 'Inactive' {
  return status === 'Open' ? 'Active' : 'Inactive'
}
