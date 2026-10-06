import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getTrackingRow, updateTracking, getStageHistory, listFollowUps, createFollowUp,
  updateFollowUp, deleteFollowUp, formatDateTime, formatMoney, toIsoFromLocal,
  TrackingUpdatePayload,
} from '../api/tracking'
import { PIPELINE_STAGES, FOLLOW_UP_TYPES, FOLLOW_UP_STATUSES, stageBadgeVariant, jobActiveLabel } from '../types'
import type { FollowUp, ShortlistRow } from '../types'
import Button from './ui/Button'
import Badge from './ui/Badge'
import EmptyState from './ui/EmptyState'
import AccordionSection from './ui/AccordionSection'
import './CandidateTrackingModal.css'

const SELECTION_STAGES = ['Selected', 'Joined', 'Offer Declined']

/** ISO datetime -> "YYYY-MM-DD" in the browser's local timezone (for <input type="date">). */
function isoToLocalDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function todayLocal(): string {
  return isoToLocalDate(new Date().toISOString())
}

function errorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

interface DetailsForm {
  stage: string
  stage_note: string
  submitted_to: string
  submitted_on: string
  offered_ctc: string
  joining_date: string
  invoice_raised: boolean
  invoice_date: string
}

function formFromRow(row: ShortlistRow): DetailsForm {
  return {
    stage: row.stage || 'Shortlisted',
    stage_note: '',
    submitted_to: row.submitted_to || '',
    submitted_on: isoToLocalDate(row.submitted_on),
    offered_ctc: row.offered_ctc != null ? String(row.offered_ctc) : '',
    joining_date: row.joining_date || '',
    invoice_raised: row.invoice_raised,
    invoice_date: row.invoice_date || '',
  }
}

interface CandidateTrackingModalProps {
  assessmentId: string
  onClose: () => void
}

/**
 * Everything that happens to a candidate for one job after shortlisting:
 * stage, client submission, follow-ups/interviews, selection (CTC + joining
 * date), invoice YES/NO, and the full history of each.
 */
export default function CandidateTrackingModal({ assessmentId, onClose }: CandidateTrackingModalProps) {
  const queryClient = useQueryClient()

  const { data: row, isLoading } = useQuery({
    queryKey: ['trackingRow', assessmentId],
    queryFn: () => getTrackingRow(assessmentId),
  })
  const { data: followUps } = useQuery({
    queryKey: ['followUps', assessmentId],
    queryFn: () => listFollowUps(assessmentId),
  })
  const { data: history } = useQuery({
    queryKey: ['stageHistory', assessmentId],
    queryFn: () => getStageHistory(assessmentId),
  })

  function refreshAll() {
    queryClient.invalidateQueries({ queryKey: ['trackingRow', assessmentId] })
    queryClient.invalidateQueries({ queryKey: ['followUps', assessmentId] })
    queryClient.invalidateQueries({ queryKey: ['stageHistory', assessmentId] })
    // Lists elsewhere that show this candidate's stage / follow-ups / invoice.
    queryClient.invalidateQueries({ queryKey: ['shortlisted'] })
    queryClient.invalidateQueries({ queryKey: ['dueFollowUps'] })
    queryClient.invalidateQueries({ queryKey: ['invoiceStatus'] })
    queryClient.invalidateQueries({ queryKey: ['funnel'] })
    queryClient.invalidateQueries({ queryKey: ['pipeline'] })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-panel-wide" onClick={(e) => e.stopPropagation()}>
        {isLoading && <p className="muted">Loading…</p>}
        {row && (
          <>
            <h2>{row.candidate_name}</h2>
            <p className="muted tracking-subtitle">
              {row.job_title} · {row.company_name}{' '}
              <Badge variant={row.company_active ? 'shortlist' : 'pass'}>{row.company_active ? 'Active' : 'Inactive'}</Badge>{' '}
              <span className="muted">JD:</span>{' '}
              <Badge variant={row.job_status === 'Open' ? 'shortlist' : 'pass'}>{jobActiveLabel(row.job_status)}</Badge>
            </p>
            <p className="muted tracking-subtitle tracking-subtitle-last">
              {row.candidate_email}{row.candidate_phone ? ` · ${row.candidate_phone}` : ''}
              {row.expected_ctc != null && <> · Expected CTC {formatMoney(row.expected_ctc)}</>}
            </p>

            <DetailsSection row={row} onSaved={refreshAll} />

            <AccordionSection title={`Follow-ups & interviews (${followUps?.length ?? 0})`} defaultOpen>
              <FollowUpSection assessmentId={assessmentId} followUps={followUps || []} onChanged={refreshAll} />
            </AccordionSection>

            <AccordionSection title="Stage history">
              {!history || history.length === 0 ? (
                <EmptyState message="No stage changes recorded yet." />
              ) : (
                <ul className="tracking-timeline">
                  {history.map((h) => (
                    <li key={h.id}>
                      <div>
                        {h.from_stage ? <>{h.from_stage} → </> : null}
                        <Badge variant={stageBadgeVariant(h.to_stage)}>{h.to_stage}</Badge>
                      </div>
                      <div className="muted">
                        {formatDateTime(h.changed_at)}{h.changed_by_name ? ` · ${h.changed_by_name}` : ''}
                        {h.note ? ` · ${h.note}` : ''}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </AccordionSection>
          </>
        )}

        <div className="row-between tracking-actions">
          <Button variant="secondary" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stage / submission / selection / invoice
// ---------------------------------------------------------------------------

function DetailsSection({ row, onSaved }: { row: ShortlistRow; onSaved: () => void }) {
  const [form, setForm] = useState<DetailsForm>(() => formFromRow(row))
  const [error, setError] = useState<string | null>(null)

  // Re-sync after a save refetches the row.
  useEffect(() => { setForm(formFromRow(row)) }, [row])

  const mutation = useMutation({
    mutationFn: (payload: TrackingUpdatePayload) => updateTracking(row.assessment_id, payload),
    onSuccess: () => { setError(null); onSaved() },
    onError: (err: any) => setError(errorMessage(err, 'Could not save the changes.')),
  })

  function set<K extends keyof DetailsForm>(key: K, value: DetailsForm[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  const showSelection = SELECTION_STAGES.includes(form.stage)
  const showInvoice = form.stage === 'Joined'

  function handleSave() {
    const payload: TrackingUpdatePayload = {
      stage: form.stage,
      stage_note: form.stage_note,
      submitted_to: form.submitted_to,
      submitted_on: form.submitted_on ? toIsoFromLocal(form.submitted_on, '00:00') : null,
    }
    if (showSelection) {
      payload.offered_ctc = form.offered_ctc ? Number(form.offered_ctc) : null
      payload.joining_date = form.joining_date || null
    }
    if (showInvoice) {
      payload.invoice_raised = form.invoice_raised
      if (form.invoice_raised) {
        payload.invoice_date = form.invoice_date || todayLocal()
      }
    }
    mutation.mutate(payload)
  }

  return (
    <AccordionSection title="Status & details" defaultOpen>
      <div className="grid-2">
        <div className="field">
          <label>Current stage</label>
          <select value={form.stage} onChange={(e) => set('stage', e.target.value)}>
            {PIPELINE_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Note for this change (optional)</label>
          <input value={form.stage_note} onChange={(e) => set('stage_note', e.target.value)} placeholder="e.g. Client confirmed round 2" />
        </div>
      </div>

      <div className="grid-2">
        <div className="field">
          <label>Submitted to (client contact)</label>
          <input value={form.submitted_to} onChange={(e) => set('submitted_to', e.target.value)} placeholder={row.company_name} />
        </div>
        <div className="field">
          <label>Submitted on</label>
          <input type="date" value={form.submitted_on} onChange={(e) => set('submitted_on', e.target.value)} />
        </div>
      </div>

      {showSelection && (
        <div className="grid-2">
          <div className="field">
            <label>Hiring budget / offered CTC (₹)</label>
            <input type="number" min={0} value={form.offered_ctc} onChange={(e) => set('offered_ctc', e.target.value)} />
          </div>
          <div className="field">
            <label>Joining date{form.stage === 'Joined' ? ' *' : ''}</label>
            <input type="date" value={form.joining_date} onChange={(e) => set('joining_date', e.target.value)} required={form.stage === 'Joined'} />
          </div>
        </div>
      )}

      {showInvoice && (
        <div className="tracking-invoice">
          <div className="field">
            <label>Invoice raised?</label>
            <div className="pill-radio-group" role="radiogroup" aria-label="Invoice raised">
              {[true, false].map((val) => (
                <label key={String(val)} className={`pill-radio ${form.invoice_raised === val ? 'pill-radio-selected' : ''}`}>
                  <input type="radio" name="invoice_raised" checked={form.invoice_raised === val} onChange={() => set('invoice_raised', val)} />
                  {val ? 'YES' : 'NO'}
                </label>
              ))}
            </div>
          </div>
          {form.invoice_raised && (
            <div className="field">
              <label>Invoice date</label>
              <input type="date" value={form.invoice_date} onChange={(e) => set('invoice_date', e.target.value)} />
            </div>
          )}
        </div>
      )}

      {!showInvoice && (
        <p className="muted tracking-hint">Invoice status becomes available once the stage is <strong>Joined</strong>.</p>
      )}

      {error && <p className="error-text" role="alert">{error}</p>}
      <Button onClick={handleSave} loading={mutation.isPending}>
        {mutation.isPending ? 'Saving…' : 'Save details'}
      </Button>
    </AccordionSection>
  )
}

// ---------------------------------------------------------------------------
// Follow-ups
// ---------------------------------------------------------------------------

function FollowUpSection({ assessmentId, followUps, onChanged }: {
  assessmentId: string
  followUps: FollowUp[]
  onChanged: () => void
}) {
  const [type, setType] = useState<string>('General Follow-up')
  const [date, setDate] = useState(todayLocal())
  const [time, setTime] = useState('10:00')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () => createFollowUp(assessmentId, { follow_up_type: type, scheduled_at: toIsoFromLocal(date, time), notes }),
    onSuccess: () => { setNotes(''); setError(null); onChanged() },
    onError: (err: any) => setError(errorMessage(err, 'Could not add the follow-up.')),
  })

  const now = Date.now()

  return (
    <>
      <div className="tracking-followup-form">
        <div className="grid-2">
          <div className="field">
            <label>Type</label>
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {FOLLOW_UP_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="row tracking-datetime">
            <div className="field"><label>Date</label><input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
            <div className="field"><label>Time</label><input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></div>
          </div>
        </div>
        <div className="field">
          <label>Notes</label>
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Call to confirm availability for client round" />
        </div>
        {error && <p className="error-text" role="alert">{error}</p>}
        <Button size="sm" onClick={() => createMutation.mutate()} loading={createMutation.isPending} disabled={!date}>
          + Add follow-up
        </Button>
      </div>

      {followUps.length === 0 ? (
        <EmptyState message="No follow-ups yet." />
      ) : (
        <ul className="tracking-followup-list">
          {followUps.map((f) => (
            <FollowUpItem key={f.id} followUp={f} overdue={f.status === 'Scheduled' && new Date(f.scheduled_at).getTime() < now} onChanged={onChanged} />
          ))}
        </ul>
      )}
    </>
  )
}

function followUpBadge(status: string, overdue: boolean): 'shortlist' | 'review' | 'pass' {
  if (overdue) return 'pass'
  if (status === 'Completed') return 'shortlist'
  if (status === 'Cancelled' || status === 'No Show') return 'pass'
  return 'review'
}

function FollowUpItem({ followUp: f, overdue, onChanged }: { followUp: FollowUp; overdue: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [status, setStatus] = useState<string>(f.status === 'Scheduled' ? 'Completed' : f.status)
  const [outcome, setOutcome] = useState(f.outcome)
  const [newDate, setNewDate] = useState('')
  const [newTime, setNewTime] = useState('10:00')
  const [error, setError] = useState<string | null>(null)

  const updateMutation = useMutation({
    mutationFn: () => updateFollowUp(
      f.id,
      status === 'Rescheduled'
        ? { outcome, reschedule_to: toIsoFromLocal(newDate, newTime) }
        : { status, outcome },
    ),
    onSuccess: () => { setEditing(false); setError(null); onChanged() },
    onError: (err: any) => setError(errorMessage(err, 'Could not update the follow-up.')),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteFollowUp(f.id),
    onSuccess: onChanged,
  })

  return (
    <li className="tracking-followup-item">
      <div className="row-between">
        <div>
          <strong>{f.follow_up_type}</strong>{' '}
          <Badge variant={followUpBadge(f.status, overdue)}>{overdue ? 'Overdue' : f.status}</Badge>
          <div className="muted">
            {formatDateTime(f.scheduled_at)}{f.created_by_name ? ` · by ${f.created_by_name}` : ''}
          </div>
          {f.notes && <div className="tracking-followup-text">{f.notes}</div>}
          {f.outcome && <div className="tracking-followup-text"><span className="muted">Outcome:</span> {f.outcome}</div>}
          {f.previous_schedules?.length > 0 && (
            <ul className="tracking-followup-previous">
              {f.previous_schedules.map((p, i) => (
                <li key={i}>
                  Rescheduled from <span className="tracking-followup-old-date">{formatDateTime(p.scheduled_at)}</span>
                  {p.reason ? ` · ${p.reason}` : ''}
                  {p.rescheduled_on ? <span className="muted"> (changed {formatDateTime(p.rescheduled_on)})</span> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="row">
          {!editing && (
            <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
              {f.status === 'Scheduled' ? 'Update' : 'Edit'}
            </Button>
          )}
          {!editing && (
            <button
              type="button"
              className="link-button muted"
              onClick={() => { if (window.confirm('Delete this follow-up?')) deleteMutation.mutate() }}
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {editing && (
        <div className="tracking-followup-edit">
          <div className="grid-2">
            <div className="field">
              <label>Status</label>
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                {FOLLOW_UP_STATUSES.filter((s) => f.status === 'Scheduled' || s !== 'Rescheduled').map((s) => (
                  <option key={s} value={s}>{s === 'Rescheduled' ? 'Reschedule to…' : s}</option>
                ))}
              </select>
            </div>
            {status === 'Rescheduled' && (
              <div className="row tracking-datetime">
                <div className="field"><label>New date</label><input type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} /></div>
                <div className="field"><label>New time</label><input type="time" value={newTime} onChange={(e) => setNewTime(e.target.value)} /></div>
              </div>
            )}
          </div>
          <div className="field">
            <label>{status === 'Rescheduled' ? 'Reason for rescheduling' : 'Outcome / remarks'}</label>
            <input
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
              placeholder={status === 'Rescheduled' ? 'e.g. Candidate unavailable, moved on request' : 'e.g. Cleared round 1, client wants HR round'}
            />
          </div>
          {error && <p className="error-text" role="alert">{error}</p>}
          <div className="row">
            <Button size="sm" onClick={() => updateMutation.mutate()} loading={updateMutation.isPending}
              disabled={status === 'Rescheduled' && !newDate}>
              Save
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </div>
      )}
    </li>
  )
}
