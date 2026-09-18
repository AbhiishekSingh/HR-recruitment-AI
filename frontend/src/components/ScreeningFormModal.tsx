import { useState, FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { submitScreening, ScreeningFormValues } from '../api/assessments'
import Button from './ui/Button'
import './ScreeningFormModal.css'

const DEFAULTS: ScreeningFormValues = {
  current_ctc: null, expected_ctc: null, notice_period_days: null,
  current_location: '', preferred_location: '',
  cv_relevance: 'Yes', experience_match: 'Strong', skills_match: 'Strong',
  industry_alignment: 'Yes', job_stability: 'Stable', communication: 'Good',
  interest_level: 'High', notice_fit: 'Yes', salary_alignment: 'Yes',
  role_notes: '', skills_notes: '', achievements: '', reason_for_change: '', red_flags: '',
  final_status: 'Share to Client', recruiter_remarks: '',
}

export default function ScreeningFormModal({ assessmentId, onClose, onSaved }: {
  assessmentId: string
  onClose: () => void
  onSaved: () => void
}) {
  const [form, setForm] = useState<ScreeningFormValues>(DEFAULTS)

  const mutation = useMutation({
    mutationFn: () => submitScreening(assessmentId, form),
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

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-panel-wide" onClick={(e) => e.stopPropagation()}>
        <h2>Screening call</h2>
        <form className="screening-form" onSubmit={handleSubmit}>
          <h3>Compensation &amp; logistics</h3>
          <div className="grid-2">
            <div className="field"><label>Current CTC (₹)</label><input type="number" value={form.current_ctc ?? ''} onChange={(e) => set('current_ctc', e.target.value ? Number(e.target.value) : null)} /></div>
            <div className="field"><label>Expected CTC (₹)</label><input type="number" value={form.expected_ctc ?? ''} onChange={(e) => set('expected_ctc', e.target.value ? Number(e.target.value) : null)} /></div>
          </div>
          <div className="grid-2">
            <div className="field"><label>Notice period (days)</label><input type="number" value={form.notice_period_days ?? ''} onChange={(e) => set('notice_period_days', e.target.value ? Number(e.target.value) : null)} /></div>
            <div className="field"><label>Current location</label><input value={form.current_location} onChange={(e) => set('current_location', e.target.value)} /></div>
          </div>
          <div className="field"><label>Preferred location</label><input value={form.preferred_location} onChange={(e) => set('preferred_location', e.target.value)} /></div>

          <h3>Profile screening</h3>
          <div className="grid-2">
            {selectField('CV relevance', 'cv_relevance', ['Yes', 'No'])}
            {selectField('Experience match', 'experience_match', ['Strong', 'Partial', 'Low'])}
          </div>
          <div className="grid-2">
            {selectField('Skills match', 'skills_match', ['Strong', 'Partial', 'Low'])}
            {selectField('Industry alignment', 'industry_alignment', ['Yes', 'No'])}
          </div>
          <div className="grid-2">
            {selectField('Job stability', 'job_stability', ['Stable', 'Moderate', 'Frequent Changes'])}
            {selectField('Communication', 'communication', ['Good', 'Average', 'Poor'])}
          </div>
          <div className="grid-2">
            {selectField('Interest level', 'interest_level', ['High', 'Moderate', 'Low'])}
            {selectField('Notice fit', 'notice_fit', ['Yes', 'No'])}
          </div>
          {selectField('Salary alignment', 'salary_alignment', ['Yes', 'No'])}

          <h3>Screening call highlights</h3>
          <div className="field"><label>Role &amp; responsibilities</label><textarea rows={2} value={form.role_notes} onChange={(e) => set('role_notes', e.target.value)} /></div>
          <div className="field"><label>Key skills / tools</label><textarea rows={2} value={form.skills_notes} onChange={(e) => set('skills_notes', e.target.value)} /></div>
          <div className="field"><label>Achievements</label><textarea rows={2} value={form.achievements} onChange={(e) => set('achievements', e.target.value)} /></div>
          <div className="field"><label>Reason for job change</label><textarea rows={2} value={form.reason_for_change} onChange={(e) => set('reason_for_change', e.target.value)} /></div>
          <div className="field"><label>Red flags (if any)</label><textarea rows={2} value={form.red_flags} onChange={(e) => set('red_flags', e.target.value)} /></div>

          <h3>Final status</h3>
          {selectField('Status', 'final_status', ['Share to Client', 'Hold', 'Reject'])}
          <div className="field"><label>Recruiter remarks</label><textarea rows={2} value={form.recruiter_remarks} onChange={(e) => set('recruiter_remarks', e.target.value)} /></div>

          {mutation.isError && <p className="error-text" role="alert">Could not save the screening.</p>}
          <div className="row-between screening-form-actions">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={mutation.isPending}>
              {mutation.isPending ? 'Saving...' : 'Save screening & score'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
