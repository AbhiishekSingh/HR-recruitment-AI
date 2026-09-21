import { useState, FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { submitScreening, ScreeningFormValues } from '../api/assessments'
import type { AssessmentScored } from '../types'
import Button from './ui/Button'
import AccordionSection from './ui/AccordionSection'
import './ScreeningFormModal.css'

const BLANK_DEFAULTS: ScreeningFormValues = {
  current_ctc: null, expected_ctc: null, notice_period_days: null,
  current_location: '', preferred_location: '',
  cv_relevance: 'Yes', experience_match: 'Strong', skills_match: 'Strong',
  industry_alignment: 'Yes', job_stability: 'Stable', communication: 'Good',
  interest_level: 'High', notice_fit: 'Yes', salary_alignment: 'Yes',
  role_notes: '', skills_notes: '', achievements: '', reason_for_change: '', red_flags: '',
  final_status: 'Share to Client', recruiter_remarks: '', approved_by: '', submitted_to: '',
}

/** Builds the form's starting values from an already-screened assessment
 *  (edit flow) or falls back to sensible blanks (first-time screening). No
 *  extra fetch needed — the caller already has this row loaded. */
function initialValuesFrom(assessment: AssessmentScored): ScreeningFormValues {
  if (!assessment.screened) return BLANK_DEFAULTS
  return {
    current_ctc: assessment.current_ctc,
    expected_ctc: assessment.expected_ctc,
    notice_period_days: assessment.notice_period_days,
    current_location: assessment.current_location,
    preferred_location: assessment.preferred_location,
    cv_relevance: assessment.cv_relevance || BLANK_DEFAULTS.cv_relevance,
    experience_match: assessment.experience_match || BLANK_DEFAULTS.experience_match,
    skills_match: assessment.skills_match || BLANK_DEFAULTS.skills_match,
    industry_alignment: assessment.industry_alignment || BLANK_DEFAULTS.industry_alignment,
    job_stability: assessment.job_stability || BLANK_DEFAULTS.job_stability,
    communication: assessment.communication || BLANK_DEFAULTS.communication,
    interest_level: assessment.interest_level || BLANK_DEFAULTS.interest_level,
    notice_fit: assessment.notice_fit || BLANK_DEFAULTS.notice_fit,
    salary_alignment: assessment.salary_alignment || BLANK_DEFAULTS.salary_alignment,
    role_notes: assessment.role_notes,
    skills_notes: assessment.skills_notes,
    achievements: assessment.achievements,
    reason_for_change: assessment.reason_for_change,
    red_flags: assessment.red_flags,
    final_status: assessment.final_status === 'Pending Screening' ? 'Share to Client' : assessment.final_status,
    recruiter_remarks: assessment.recruiter_remarks,
    approved_by: assessment.approved_by || '',
    submitted_to: assessment.submitted_to || '',
  }
}

interface ScreeningFormModalProps {
  /** The full pipeline/assessment row the caller already has loaded — used
   *  both to prefill the form and to display candidate details, so this
   *  modal never has to fetch anything on its own. */
  assessment: AssessmentScored
  jobTitle: string
  onClose: () => void
  onSaved: () => void
}

export default function ScreeningFormModal({ assessment, jobTitle, onClose, onSaved }: ScreeningFormModalProps) {
  const [form, setForm] = useState<ScreeningFormValues>(() => initialValuesFrom(assessment))

  const mutation = useMutation({
    mutationFn: () => submitScreening(assessment.id, form),
    onSuccess: onSaved,
  })

  function set<K extends keyof ScreeningFormValues>(key: K, value: ScreeningFormValues[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    mutation.mutate()
  }

  const selectField = (label: string, key: keyof ScreeningFormValues, options: string[]) => (
    <div className="field">
      <label>{label}</label>
      <select value={form[key] as string} onChange={(e) => set(key, e.target.value as any)}>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )

  const radioGroup = (label: string, key: keyof ScreeningFormValues, options: string[]) => (
    <div className="field">
      <label>{label}</label>
      <div className="pill-radio-group" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <label key={o} className={`pill-radio ${form[key] === o ? 'pill-radio-selected' : ''}`}>
            <input
              type="radio"
              name={key}
              value={o}
              checked={form[key] === o}
              onChange={() => set(key, o as any)}
            />
            {o}
          </label>
        ))}
      </div>
    </div>
  )

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-panel-wide" onClick={(e) => e.stopPropagation()}>
        <h2>Candidate Assessment</h2>
        <p className="muted screening-form-subtitle">Fill in the details from the screening call below.</p>

        <form className="screening-form" onSubmit={handleSubmit}>
          <AccordionSection title="Basic Details" defaultOpen>
            <div className="field">
              <label>Candidate Name</label>
              <input value={assessment.candidate_name} disabled />
            </div>
            <div className="field">
              <label>Position Applied For</label>
              <input value={jobTitle} disabled />
            </div>
            <div className="grid-2">
              <div className="field">
                <label>Total Experience</label>
                <input value={`${assessment.candidate_experience_years} years`} disabled />
              </div>
              <div className="field">
                <label>Current Company</label>
                <input value={assessment.candidate_current_company || '—'} disabled />
              </div>
            </div>
            <div className="grid-2">
              <div className="field">
                <label>Current CTC (₹)</label>
                <input type="number" value={form.current_ctc ?? ''} onChange={(e) => set('current_ctc', e.target.value ? Number(e.target.value) : null)} />
              </div>
              <div className="field">
                <label>Expected CTC (₹)</label>
                <input type="number" value={form.expected_ctc ?? ''} onChange={(e) => set('expected_ctc', e.target.value ? Number(e.target.value) : null)} />
              </div>
            </div>
            <div className="field">
              <label>Notice Period (days)</label>
              <input type="number" value={form.notice_period_days ?? ''} onChange={(e) => set('notice_period_days', e.target.value ? Number(e.target.value) : null)} />
            </div>
            <div className="grid-2">
              <div className="field">
                <label>Current Location</label>
                <input value={form.current_location} onChange={(e) => set('current_location', e.target.value)} />
              </div>
              <div className="field">
                <label>Preferred Location</label>
                <input value={form.preferred_location} onChange={(e) => set('preferred_location', e.target.value)} />
              </div>
            </div>
            <p className="muted screening-form-note">
              Resume / CV is managed from the Candidates directory — click {assessment.candidate_name} there to view, replace, or remove it.
            </p>
          </AccordionSection>

          <AccordionSection title="Profile Screening">
            {radioGroup('CV Relevance to Role', 'cv_relevance', ['Yes', 'No'])}
            {radioGroup('Experience Match (Years & Domain)', 'experience_match', ['Strong', 'Partial', 'Low'])}
            {radioGroup('Key Skills Match', 'skills_match', ['Strong', 'Partial', 'Low'])}
            {radioGroup('Industry Alignment', 'industry_alignment', ['Yes', 'No'])}
            {radioGroup('Job Stability', 'job_stability', ['Stable', 'Moderate', 'Frequent Changes'])}
            {radioGroup('Communication (Basic Screening Call)', 'communication', ['Good', 'Average', 'Poor'])}
            {radioGroup('Candidate Interest Level', 'interest_level', ['High', 'Moderate', 'Low'])}
            {radioGroup('Availability / Notice Period Fit', 'notice_fit', ['Yes', 'No'])}
            {radioGroup('Salary Alignment with Client Budget', 'salary_alignment', ['Yes', 'No'])}
          </AccordionSection>

          <AccordionSection title="Key Highlights from Screening Call">
            <div className="field"><label>Current Role &amp; Responsibilities</label><textarea rows={2} value={form.role_notes} onChange={(e) => set('role_notes', e.target.value)} /></div>
            <div className="field"><label>Key Skills / Tools</label><textarea rows={2} value={form.skills_notes} onChange={(e) => set('skills_notes', e.target.value)} /></div>
            <div className="field"><label>Achievements (if any)</label><textarea rows={2} value={form.achievements} onChange={(e) => set('achievements', e.target.value)} /></div>
            <div className="field"><label>Reason for Job Change</label><textarea rows={2} value={form.reason_for_change} onChange={(e) => set('reason_for_change', e.target.value)} /></div>
          </AccordionSection>

          <AccordionSection title="Red Flags">
            <div className="field">
              <label>Red Flags (if any)</label>
              <textarea rows={3} placeholder="Leave blank if none" value={form.red_flags} onChange={(e) => set('red_flags', e.target.value)} />
            </div>
          </AccordionSection>

          <AccordionSection title="Recruiter Sign-off">
            {selectField('Final Status', 'final_status', ['Share to Client', 'Hold', 'Reject'])}
            <div className="field"><label>Recruiter Remarks</label><textarea rows={2} value={form.recruiter_remarks} onChange={(e) => set('recruiter_remarks', e.target.value)} /></div>
            <div className="grid-2">
              <div className="field"><label>Approved By</label><input value={form.approved_by} onChange={(e) => set('approved_by', e.target.value)} /></div>
              <div className="field"><label>Submitted To</label><input value={form.submitted_to} onChange={(e) => set('submitted_to', e.target.value)} /></div>
            </div>
          </AccordionSection>

          {mutation.isError && <p className="error-text" role="alert">Could not save the screening.</p>}
          <div className="row-between screening-form-actions">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={mutation.isPending} className="btn-teal">
              {mutation.isPending ? 'Saving...' : 'Submit Assessment'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}