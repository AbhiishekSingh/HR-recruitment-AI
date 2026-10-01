import { useState, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJob } from '../api/jobs'
import { bulkUploadResumes, listCandidates, getSectorCounts } from '../api/candidates'
import { getJobPipeline, startAssessment, sendToClient } from '../api/assessments'
import { BUCKET_LABELS, stageBadgeVariant } from '../types'
import type { AssessmentScored } from '../types'
import ScreeningFormModal from '../components/ScreeningFormModal'
import CandidateTrackingModal from '../components/CandidateTrackingModal'
import PageHeader from '../components/ui/PageHeader'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import Badge from '../components/ui/Badge'
import './PipelinePage.css'

export default function PipelinePage() {
  const { jobId } = useParams<{ jobId: string }>()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [bucketFilter, setBucketFilter] = useState('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [findCandidateOpen, setFindCandidateOpen] = useState(false)
  // Store the full row (already fetched, no extra call needed) so the
  // screening modal can prefill from it and display candidate/job details.
  const [screeningTarget, setScreeningTarget] = useState<AssessmentScored | null>(null)
  const [trackingTargetId, setTrackingTargetId] = useState<string | null>(null)

  const { data: job } = useQuery({ queryKey: ['job', jobId], queryFn: () => getJob(jobId!), enabled: !!jobId })

  const { data: pipeline, isLoading } = useQuery({
    queryKey: ['pipeline', jobId],
    queryFn: () => getJobPipeline(jobId!),
    enabled: !!jobId,
    refetchInterval: 5000, // picks up ingestion status changes without a manual refresh
  })

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => bulkUploadResumes(files, jobId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline', jobId] })
      if (fileInputRef.current) fileInputRef.current.value = ''
    },
  })

  const sendMutation = useMutation({
    mutationFn: () => sendToClient(Array.from(selected)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline', jobId] })
      setSelected(new Set())
    },
  })

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || [])
    if (files.length) uploadMutation.mutate(files)
  }

  function toggleSelect(assessmentId: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(assessmentId) ? next.delete(assessmentId) : next.add(assessmentId)
      return next
    })
  }

  const filtered = (pipeline || []).filter((a) => bucketFilter === 'all' || a.bucket === bucketFilter)

  return (
    <div className="container pipeline-page">
      <PageHeader
        backTo="/companies"
        eyebrow={job?.title}
        title="Candidate pipeline"
        actions={
          <>
            <label className="btn btn-secondary pipeline-upload-label">
              {uploadMutation.isPending ? 'Uploading...' : '+ Add resumes for this role'}
              <input ref={fileInputRef} type="file" accept=".pdf,.docx" multiple hidden onChange={handleFileChange} disabled={uploadMutation.isPending} />
            </label>
            <Button onClick={() => setFindCandidateOpen(true)}>+ Assess one candidate</Button>
          </>
        }
      />

      {job && (
        <div className="skill-chips">
          {job.required_skills.map((s) => <span key={s} className="skill-chip">{s}</span>)}
        </div>
      )}

      <div className="row filter-row">
        <select value={bucketFilter} onChange={(e) => setBucketFilter(e.target.value)}>
          <option value="all">All</option>
          <option value="pending">Pending screening</option>
          <option value="strong">Strong match</option>
          <option value="good">Good match</option>
          <option value="weak">Weak match</option>
          <option value="notrec">Not recommended</option>
          <option value="rejected">Rejected</option>
        </select>
        <span className="muted">{filtered.length} record{filtered.length === 1 ? '' : 's'}</span>
      </div>

      <div className="card">
        {isLoading && <p className="muted">Loading pipeline...</p>}
        {!isLoading && filtered.length === 0 && (
          <EmptyState message="No resumes yet for this role. Add resumes above or assess one candidate directly." />
        )}
        {filtered.length > 0 && (
          <div className="table-responsive">
            <table className="table pipeline-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Candidate</th>
                  <th>Score</th>
                  <th>Experience</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <PipelineRow
                    key={a.id}
                    assessment={a}
                    selected={selected.has(a.id)}
                    onToggleSelect={() => toggleSelect(a.id)}
                    onScreen={() => setScreeningTarget(a)}
                    onTrack={() => setTrackingTargetId(a.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected.size > 0 && (
        <div className="bulk-bar">
          <span>{selected.size} selected</span>
          <Button onClick={() => sendMutation.mutate()} loading={sendMutation.isPending}>
            {sendMutation.isPending ? 'Sending...' : 'Send selected to client'}
          </Button>
        </div>
      )}

      {findCandidateOpen && jobId && (
        <FindCandidateModal
          jobId={jobId}
          onClose={() => setFindCandidateOpen(false)}
          onSelected={(a) => { setFindCandidateOpen(false); setScreeningTarget(a) }}
        />
      )}

      {trackingTargetId && (
        <CandidateTrackingModal assessmentId={trackingTargetId} onClose={() => setTrackingTargetId(null)} />
      )}

      {screeningTarget && (
        <ScreeningFormModal
          assessment={screeningTarget}
          jobTitle={job?.title || ''}
          onClose={() => setScreeningTarget(null)}
          onSaved={() => { setScreeningTarget(null); queryClient.invalidateQueries({ queryKey: ['pipeline', jobId] }) }}
        />
      )}
    </div>
  )
}

function PipelineRow({ assessment, selected, onToggleSelect, onScreen, onTrack }: {
  assessment: AssessmentScored
  selected: boolean
  onToggleSelect: () => void
  onScreen: () => void
  onTrack: () => void
}) {
  const a = assessment
  const isPending = a.bucket === 'pending'
  // "warn"-level flags only (the sanity-check mismatch, hard-filter
  // breaches) -- "info" (the estimate notice) is already conveyed by the
  // score caption below, so surfacing it again in the icon would be noise.
  const warnFlags = a.flags.filter((f) => f.level === 'warn')
  const isProcessing = ['queued', 'extracting', 'embedding'].includes(a.candidate_status)
  const extractionFailed = ['needs_review', 'failed'].includes(a.candidate_status)

  return (
    <tr>
      <td>
        <input type="checkbox" checked={selected} onChange={onToggleSelect} disabled={isPending || a.bucket === 'rejected'} />
      </td>
      <td>
        <strong>{a.candidate_name}</strong>
        <div className="muted">{a.candidate_email}</div>
      </td>
      <td>
        {isProcessing ? (
          <div className="muted score-caption">Resume processing ({a.candidate_status})…</div>
        ) : extractionFailed ? (
          <div className="score-cell">
            <span className="score-flag" title="Resume text couldn't be extracted — check the file and re-upload, or fill in manually.">⚠</span>
            <span className="muted score-caption">Needs review — extraction failed</span>
          </div>
        ) : (
          <>
            <div className="score-cell">
              {isPending ? (
                <strong>{a.ai_score}</strong>
              ) : (
                <strong>{a.final_score}</strong>
              )}
              {warnFlags.length > 0 && (
                <span className="score-flag" title={warnFlags.map((f) => f.text).join('\n')}>⚠</span>
              )}
            </div>
            <div className="muted score-caption">
              {isPending
                ? a.ai_source === 'estimate' ? 'AI fit — estimate only' : 'AI fit only'
                : 'Final (AI + assessment)'}
            </div>
            {(a.matched_skills.length > 0 || a.missing_skills.length > 0) && (
              <div
                className="muted score-caption"
                title={
                  `Matched: ${a.matched_skills.join(', ') || '—'}\n` +
                  `Missing: ${a.missing_skills.join(', ') || '—'}`
                }
              >
                {a.matched_skills.length}/{a.matched_skills.length + a.missing_skills.length} skills matched
              </div>
            )}
          </>
        )}
      </td>
      <td className="muted">{a.candidate_experience_years} yrs</td>
      <td>
        <Badge variant={
          a.bucket === 'strong' || a.bucket === 'good' ? 'shortlist' :
          a.bucket === 'rejected' || a.bucket === 'notrec' ? 'pass' : 'review'
        }>
          {BUCKET_LABELS[a.bucket]}
        </Badge>
        {a.stage && (
          <div className="pipeline-stage">
            <Badge variant={stageBadgeVariant(a.stage)}>{a.stage}</Badge>
          </div>
        )}
      </td>
      <td>
        <div className="row pipeline-row-actions">
          <Button variant="secondary" size="sm" onClick={onScreen}>
            {isPending ? 'Complete screening →' : 'Edit screening'}
          </Button>
          {a.stage && (
            <Button variant="secondary" size="sm" onClick={onTrack}>Track →</Button>
          )}
        </div>
      </td>
    </tr>
  )
}

function FindCandidateModal({ jobId, onClose, onSelected }: { jobId: string; onClose: () => void; onSelected: (assessment: AssessmentScored) => void }) {
  const [search, setSearch] = useState('')
  const [sector, setSector] = useState('')

  // Sector options come from real data (candidates that actually exist),
  // not a hardcoded list -- so a custom sector a recruiter typed via
  // SectorPicker on the upload form shows up here too, not just the
  // built-in suggested ones.
  const { data: sectorCounts } = useQuery({ queryKey: ['candidateSectorCounts'], queryFn: getSectorCounts })

  // BUG FIX: this used to call `listCandidates(search)` -- passing a plain
  // string where listCandidates(filters: CandidateFilters) expects an
  // object. Since every string has a built-in `.search` method
  // (String.prototype.search), `filters.search` was reading that function
  // reference instead of undefined, which is truthy -- so the backend
  // always received a garbled, unmatchable `search` param regardless of
  // what was actually typed, and the modal could never find any existing
  // candidate no matter how many were on file. Fixed by passing the actual
  // filters object, and a `sector` filter added alongside it (see below).
  const { data: candidates, isLoading } = useQuery({
    queryKey: ['candidates', search, sector],
    queryFn: () => listCandidates({ search: search || undefined, sector: sector || undefined }),
  })

  const startMutation = useMutation({
    mutationFn: (candidateId: string) => startAssessment(candidateId, jobId),
    onSuccess: (assessment) => onSelected(assessment),
  })

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <h2>Assess a candidate</h2>
        <p className="muted">Pick a sector to browse its candidates, search by name/email/phone, or both together.</p>
        <div className="find-candidate-filters">
          <select value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="">All sectors</option>
            {(sectorCounts || []).map((sc) => (
              <option key={sc.sector} value={sc.sector}>{sc.sector} ({sc.count})</option>
            ))}
          </select>
          <input className="text-input-wide" placeholder="Search name, email or phone…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="find-candidate-results">
          {isLoading && <p className="muted">Loading…</p>}
          {candidates?.map((c) => (
            <div key={c.id} className="find-candidate-row">
              <div>
                <strong>{c.name}</strong>
                <div className="muted">{c.email} · {c.experience_years} yrs{c.sector ? ` · ${c.sector}` : ''}</div>
              </div>
              <Button variant="secondary" size="sm" onClick={() => startMutation.mutate(c.id)} loading={startMutation.isPending}>
                Select &amp; screen
              </Button>
            </div>
          ))}
          {!isLoading && candidates?.length === 0 && (
            <EmptyState message="No candidates match. Try a different sector or search term, or add one from the Candidates directory first." />
          )}
        </div>
        <div className="row-between" style={{ marginTop: 'var(--space-4)' }}>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  )
}