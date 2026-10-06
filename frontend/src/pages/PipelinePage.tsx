import { useState, useRef, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJob, viewJdFile } from '../api/jobs'
import { listCandidates, getSectorCounts } from '../api/candidates'
import { getJobPipeline, startAssessment, sendToClient, aiScoreCandidates } from '../api/assessments'
import { BUCKET_LABELS, stageBadgeVariant } from '../types'
import type { AssessmentScored, AIScoreRequest, AIScoreResponse } from '../types'
import EditJobModal from '../components/EditJobModal'
import ScreeningFormModal from '../components/ScreeningFormModal'
import CandidateTrackingModal from '../components/CandidateTrackingModal'
import BulkUploadModal from '../components/BulkUploadModal'
import { RESUME_ACCEPT } from '../utils/resumeFiles'
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
  const [editingJob, setEditingJob] = useState(false)

  // --- on-demand AI scoring ---
  const [aiTopN, setAiTopN] = useState('20')
  const [aiMinScore, setAiMinScore] = useState('70')
  const [aiConfirm, setAiConfirm] = useState<{ req: AIScoreRequest; preview: AIScoreResponse } | null>(null)
  const [aiBusy, setAiBusy] = useState(false)
  const [aiMessage, setAiMessage] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)
  // candidates sent for AI scoring and not finished yet (shown as "AI scoring…")
  const [aiRunning, setAiRunning] = useState<Set<string>>(new Set())
  // If a candidate's AI scoring fails, it never turns into an AI score --
  // stop showing "AI scoring…" for it after a few minutes.
  useEffect(() => {
    if (aiRunning.size === 0) return
    const t = setTimeout(() => setAiRunning(new Set()), 4 * 60 * 1000)
    return () => clearTimeout(t)
  }, [aiRunning])

  const { data: job } = useQuery({ queryKey: ['job', jobId], queryFn: () => getJob(jobId!), enabled: !!jobId })

  const { data: pipeline, isLoading } = useQuery({
    queryKey: ['pipeline', jobId],
    queryFn: () => getJobPipeline(jobId!),
    enabled: !!jobId,
    refetchInterval: 5000, // picks up ingestion status changes without a manual refresh
  })

  // Resumes picked via "+ Add resumes for this role" -- the whole upload
  // (pre-check, duplicates, batches, AI progress, retry) runs in BulkUploadModal.
  const [uploadingFiles, setUploadingFiles] = useState<File[] | null>(null)

  const sendMutation = useMutation({
    mutationFn: () => sendToClient(Array.from(selected)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline', jobId] })
      setSelected(new Set())
    },
  })

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || [])
    if (files.length) setUploadingFiles(files)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function toggleSelect(assessmentId: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(assessmentId) ? next.delete(assessmentId) : next.add(assessmentId)
      return next
    })
  }

  const filtered = (pipeline || []).filter((a) => bucketFilter === 'all' || a.bucket === bucketFilter)
  const staleCount = (pipeline || []).filter((a) => a.ai_stale).length
  const aiScoredCount = (pipeline || []).filter((a) => a.ai_source === 'ai_pipeline').length
  const stillRunning = (pipeline || []).filter((a) => aiRunning.has(a.candidate_id) && a.ai_source !== 'ai_pipeline').length

  async function previewAiScore(req: Omit<AIScoreRequest, 'dry_run'>) {
    if (!jobId) return
    setAiBusy(true)
    setAiMessage(null)
    try {
      const preview = await aiScoreCandidates(jobId, { ...req, dry_run: true })
      setAiConfirm({ req: { ...req, dry_run: false }, preview })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setAiMessage({ tone: 'bad', text: typeof detail === 'string' ? detail : 'Could not check AI scoring.' })
    } finally {
      setAiBusy(false)
    }
  }

  async function runAiScore() {
    if (!jobId || !aiConfirm) return
    setAiBusy(true)
    try {
      const result = await aiScoreCandidates(jobId, aiConfirm.req)
      setAiRunning((prev) => new Set([...prev, ...result.candidate_ids]))
      setAiMessage({
        tone: 'ok',
        text: result.queued
          ? `AI scoring started for ${result.to_score} candidate${result.to_score === 1 ? '' : 's'} (≈ ₹${result.estimated_cost_inr.toFixed(2)}). Scores appear here as they finish.`
          : 'Nothing to score: those candidates are already AI-scored or still processing.',
      })
      setAiConfirm(null)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setAiMessage({ tone: 'bad', text: typeof detail === 'string' ? detail : 'Could not start AI scoring.' })
    } finally {
      setAiBusy(false)
    }
  }

  return (
    <div className="container pipeline-page">
      <PageHeader
        backTo="/companies"
        eyebrow={job?.title}
        title="Candidate pipeline"
        actions={
          <>
            <label className="btn btn-secondary pipeline-upload-label">
              {uploadingFiles ? 'Uploading...' : '+ Add resumes for this role'}
              <input ref={fileInputRef} type="file" accept={RESUME_ACCEPT} multiple hidden onChange={handleFileChange} disabled={uploadingFiles !== null} />
            </label>
            <Button variant="secondary" onClick={() => setEditingJob(true)} disabled={!job}>Edit job</Button>
            <Button onClick={() => setFindCandidateOpen(true)}>+ Assess one candidate</Button>
          </>
        }
      />

      {job && (
        <div className="job-skill-groups">
          {(['must', 'nice', 'soft'] as const).map((type) => {
            const groups = job.skill_groups.filter((g) => g.type === type && g.skills.length > 0)
            if (groups.length === 0) return null
            return (
              <div key={type} className={`job-skill-section job-skill-section-${type}`}>
                <div className="job-skill-section-title">
                  {type === 'must' ? 'Must-have' : type === 'nice' ? 'Nice-to-have' : 'Not scored (check in screening)'}
                </div>
                <div className="job-skill-group-list">
                  {groups.map((g) => (
                    <div key={g.name} className={`job-skill-group job-skill-group-${type}`}>
                      <div className="job-skill-group-name">
                        {g.name}
                        {type !== 'soft' && g.skills.length > 1 && <span className="muted"> · any one</span>}
                      </div>
                      <div className="job-skill-group-skills">
                        {g.skills.map((s) => <span key={s} className="skill-chip">{s}</span>)}
                      </div>
                      {g.synonyms.length > 0 && (
                        <div className="muted job-skill-synonyms">also counts: {g.synonyms.join(', ')}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
          {job.has_jd_file && (
            <button type="button" className="link-button pipeline-view-jd" onClick={() => void viewJdFile(job)}>
              📄 View JD ↗
            </button>
          )}
        </div>
      )}

      <div className="card ai-score-bar">
        <div className="ai-score-bar-text">
          <strong>Ranking uses the free smart score.</strong>{' '}
          <span className="muted">
            AI scoring is optional and paid (≈ ₹0.2 per candidate): use it on your best candidates for a deeper check with reasons.
            {aiScoredCount > 0 && ` ${aiScoredCount} AI-scored so far.`}
          </span>
        </div>
        <div className="row ai-score-actions">
          <span className="ai-score-group">
            <Button size="sm" variant="secondary" loading={aiBusy} onClick={() => void previewAiScore({ mode: 'top', count: Math.max(1, Number(aiTopN) || 20) })}>
              AI score top
            </Button>
            <input className="ai-score-num" type="number" min={1} max={200} value={aiTopN} onChange={(e) => setAiTopN(e.target.value)} aria-label="How many top candidates" />
          </span>
          <span className="ai-score-group">
            <Button size="sm" variant="secondary" loading={aiBusy} onClick={() => void previewAiScore({ mode: 'above', min_score: Math.min(100, Math.max(0, Number(aiMinScore) || 70)) })}>
              AI score all above
            </Button>
            <input className="ai-score-num" type="number" min={0} max={100} value={aiMinScore} onChange={(e) => setAiMinScore(e.target.value)} aria-label="Minimum smart score" />
          </span>
          {staleCount > 0 && (
            <Button size="sm" variant="secondary" loading={aiBusy} onClick={() => void previewAiScore({ mode: 'stale' })}>
              Re-score out-of-date ({staleCount})
            </Button>
          )}
        </div>
        {stillRunning > 0 && <p className="muted ai-score-running"><span className="spinner" aria-hidden="true" /> AI scoring {stillRunning} candidate{stillRunning === 1 ? '' : 's'}…</p>}
        {aiMessage && <p className={aiMessage.tone === 'ok' ? 'muted ai-score-msg' : 'error-text'}>{aiMessage.text}</p>}
      </div>

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
                    aiRunning={aiRunning.has(a.candidate_id) && a.ai_source !== 'ai_pipeline'}
                    onAiScore={() => void previewAiScore({ mode: 'selected', candidate_ids: [a.candidate_id] })}
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

      {editingJob && job && <EditJobModal job={job} onClose={() => setEditingJob(false)} />}

      {aiConfirm && (
        <div className="modal-overlay" onClick={() => setAiConfirm(null)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <h2>AI scoring</h2>
            {aiConfirm.preview.to_score > 0 ? (
              <p>
                AI-score <strong>{aiConfirm.preview.to_score}</strong> candidate{aiConfirm.preview.to_score === 1 ? '' : 's'} for about{' '}
                <strong>₹{aiConfirm.preview.estimated_cost_inr.toFixed(2)}</strong>{' '}
                <span className="muted">(≈ ₹{aiConfirm.preview.cost_per_candidate_inr.toFixed(2)} each)</span>.
              </p>
            ) : (
              <p>There is nothing new to AI-score.</p>
            )}
            {aiConfirm.preview.already_done > 0 && (
              <p className="muted">{aiConfirm.preview.already_done} already have an up-to-date AI score: skipped, no charge.</p>
            )}
            {aiConfirm.preview.not_ready > 0 && (
              <p className="muted">{aiConfirm.preview.not_ready} can't be scored yet (resume still processing or failed).</p>
            )}
            <div className="row-between" style={{ marginTop: 'var(--space-4)' }}>
              <Button variant="secondary" onClick={() => setAiConfirm(null)}>Cancel</Button>
              {aiConfirm.preview.to_score > 0 && (
                <Button loading={aiBusy} onClick={() => void runAiScore()}>
                  Run AI scoring (≈ ₹{aiConfirm.preview.estimated_cost_inr.toFixed(2)})
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {findCandidateOpen && jobId && (
        <FindCandidateModal
          jobId={jobId}
          onClose={() => setFindCandidateOpen(false)}
          onSelected={(a) => { setFindCandidateOpen(false); setScreeningTarget(a) }}
        />
      )}

      {uploadingFiles && jobId && (
        <BulkUploadModal
          files={uploadingFiles}
          jobId={jobId}
          onChanged={() => queryClient.invalidateQueries({ queryKey: ['pipeline', jobId] })}
          onClose={() => setUploadingFiles(null)}
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

function PipelineRow({ assessment, selected, onToggleSelect, onScreen, onTrack, aiRunning, onAiScore }: {
  assessment: AssessmentScored
  selected: boolean
  onToggleSelect: () => void
  onScreen: () => void
  onTrack: () => void
  aiRunning: boolean
  onAiScore: () => void
}) {
  const a = assessment
  const [showWhy, setShowWhy] = useState(false)
  const isPending = a.bucket === 'pending'
  // "warn"-level flags only (experience far off, hard-filter breaches, AI
  // sanity check); the rest is shown in "Why?".
  const warnFlags = a.flags.filter((f) => f.level === 'warn' && !f.text.startsWith('Awaiting recruiter screening'))
  const isProcessing = ['queued', 'extracting', 'embedding'].includes(a.candidate_status)
  const extractionFailed = ['needs_review', 'failed'].includes(a.candidate_status)
  const isAi = a.ai_source === 'ai_pipeline'
  const must = a.score_parts.find((p) => p.key === 'must')

  return (
    <>
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
                <strong>{isPending ? a.ai_score : a.final_score}</strong>
                <span className={`score-source ${isAi ? 'score-source-ai' : ''}`}>{isAi ? 'AI' : 'Smart'}</span>
                {warnFlags.length > 0 && (
                  <span className="score-flag" title={warnFlags.map((f) => f.text).join('\n')}>⚠</span>
                )}
              </div>
              <div className="muted score-caption">
                {!isPending && `Final (${isAi ? 'AI' : 'smart'} score + screening)`}
                {isPending && must && must.value !== null && `Must-have: ${must.detail}`}
              </div>
              {a.ai_stale && (
                <div className="score-caption score-stale" title="Job settings or the resume changed after this AI score.">
                  AI score {a.ai_previous_score} out of date
                </div>
              )}
              <div className="score-links">
                <button type="button" className="link-button" onClick={() => setShowWhy((v) => !v)}>{showWhy ? 'Hide' : 'Why?'}</button>
                {aiRunning ? (
                  <span className="muted score-caption"><span className="spinner" aria-hidden="true" /> AI scoring…</span>
                ) : !isAi && a.candidate_status === 'ready' ? (
                  <button type="button" className="link-button muted" onClick={onAiScore}>{a.ai_stale ? 'Re-score with AI' : 'AI score'}</button>
                ) : null}
              </div>
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
      {showWhy && (
        <tr className="pipeline-why-row">
          <td></td>
          <td colSpan={5}>
            <ScoreExplanation a={a} />
          </td>
        </tr>
      )}
    </>
  )
}

function ScoreExplanation({ a }: { a: AssessmentScored }) {
  const groups = a.skill_evidence
  const section = (type: 'must' | 'nice') => groups.filter((g) => g.type === type)
  const soft = groups.filter((g) => g.type === 'soft')
  return (
    <div className="score-why">
      {a.ai_source === 'ai_pipeline' && (
        <div className="score-why-ai">
          <strong>AI score {a.ai_score}{a.ai_recommendation ? ` (${a.ai_recommendation})` : ''}</strong>
          {a.ai_strengths.length > 0 && <ul className="score-why-list">{a.ai_strengths.map((s, i) => <li key={i}>✅ {s}</li>)}</ul>}
          {a.ai_gaps.length > 0 && <ul className="score-why-list">{a.ai_gaps.map((s, i) => <li key={i}>⚠ {s}</li>)}</ul>}
        </div>
      )}
      <div>
        <strong>Smart score {a.smart_score}</strong>
        <div className="score-parts">
          {a.score_parts.map((p) => (
            <span key={p.key} className={`score-part${p.value === null ? ' score-part-na' : ''}`} title={p.detail}>
              {p.label} <strong>{p.value === null ? 'n/a' : p.value}</strong> <span className="muted">×{p.weight}%</span>
              {p.detail && <span className="muted"> · {p.detail}</span>}
            </span>
          ))}
        </div>
      </div>
      {(['must', 'nice'] as const).map((type) => section(type).length > 0 && (
        <div key={type}>
          <span className="muted">{type === 'must' ? 'Must-have' : 'Nice-to-have'}:</span>{' '}
          {section(type).map((g) => (
            <span key={g.group} className={`evidence ${g.matched ? 'evidence-yes' : 'evidence-no'}`}>
              {g.matched ? '✅' : '❌'} {g.group}
              {g.matched && g.found && <span className="muted"> (found "{g.found}" in {g.where === 'skills' ? 'skills' : 'resume'})</span>}
            </span>
          ))}
        </div>
      ))}
      {soft.length > 0 && <div className="muted">Not scored (check in screening): {soft.map((g) => g.group).join(', ')}</div>}
      {a.flags.filter((f) => !f.text.startsWith('Awaiting recruiter screening')).map((f, i) => (
        <div key={i} className={f.level === 'warn' ? 'score-why-warn' : 'muted'}>{f.level === 'warn' ? '⚠ ' : 'ℹ '}{f.text}</div>
      ))}
    </div>
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