import { useState, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJob } from '../api/jobs'
import { bulkUploadResumes, listCandidates } from '../api/candidates'
import { getJobPipeline, startAssessment, sendToClient } from '../api/assessments'
import { BUCKET_LABELS } from '../types'
import type { AssessmentScored } from '../types'
import ScreeningFormModal from '../components/ScreeningFormModal'
import './PipelinePage.css'

export default function PipelinePage() {
  const { jobId } = useParams<{ jobId: string }>()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [bucketFilter, setBucketFilter] = useState('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [findCandidateOpen, setFindCandidateOpen] = useState(false)
  const [screeningTarget, setScreeningTarget] = useState<{ assessmentId: string } | null>(null)

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
      <div className="row-between">
        <div>
          <p className="muted">{job?.title}</p>
          <h1>Candidate pipeline</h1>
        </div>
        <div className="row">
          <label className="btn btn-secondary">
            {uploadMutation.isPending ? 'Uploading...' : '+ Add resumes for this role'}
            <input ref={fileInputRef} type="file" accept=".pdf,.docx" multiple hidden onChange={handleFileChange} disabled={uploadMutation.isPending} />
          </label>
          <button className="btn btn-primary" onClick={() => setFindCandidateOpen(true)}>+ Assess one candidate</button>
        </div>
      </div>

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
          <p className="muted">No resumes yet for this role. Add resumes above or assess one candidate directly.</p>
        )}
        {filtered.length > 0 && (
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
                  onScreen={() => setScreeningTarget({ assessmentId: a.id })}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected.size > 0 && (
        <div className="bulk-bar">
          <span>{selected.size} selected</span>
          <button className="btn btn-primary" onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
            {sendMutation.isPending ? 'Sending...' : 'Send selected to client'}
          </button>
        </div>
      )}

      {findCandidateOpen && jobId && (
        <FindCandidateModal
          jobId={jobId}
          onClose={() => setFindCandidateOpen(false)}
          onSelected={(assessmentId) => { setFindCandidateOpen(false); setScreeningTarget({ assessmentId }) }}
        />
      )}

      {screeningTarget && (
        <ScreeningFormModal
          assessmentId={screeningTarget.assessmentId}
          onClose={() => setScreeningTarget(null)}
          onSaved={() => { setScreeningTarget(null); queryClient.invalidateQueries({ queryKey: ['pipeline', jobId] }) }}
        />
      )}
    </div>
  )
}

function PipelineRow({ assessment, selected, onToggleSelect, onScreen }: {
  assessment: AssessmentScored
  selected: boolean
  onToggleSelect: () => void
  onScreen: () => void
}) {
  const a = assessment
  const isPending = a.bucket === 'pending'

  return (
    <tr>
      <td>
        <input type="checkbox" checked={selected} onChange={onToggleSelect} disabled={isPending || a.bucket === 'rejected'} />
      </td>
      <td>Candidate {a.candidate_id.slice(0, 8)}</td>
      <td>
        {isPending ? (
          <><strong>{a.ai_score}</strong><div className="muted" style={{ fontSize: 11 }}>AI fit only</div></>
        ) : (
          <strong>{a.final_score}</strong>
        )}
      </td>
      <td className="muted">—</td>
      <td>
        <span className={`badge ${
          a.bucket === 'strong' || a.bucket === 'good' ? 'badge-shortlist' :
          a.bucket === 'rejected' || a.bucket === 'notrec' ? 'badge-pass' : 'badge-review'
        }`}>
          {BUCKET_LABELS[a.bucket]}
        </span>
      </td>
      <td>
        <button className="btn btn-secondary" onClick={onScreen}>
          {isPending ? 'Complete screening →' : 'Edit screening'}
        </button>
      </td>
    </tr>
  )
}

function FindCandidateModal({ jobId, onClose, onSelected }: { jobId: string; onClose: () => void; onSelected: (assessmentId: string) => void }) {
  const [search, setSearch] = useState('')
  const { data: candidates } = useQuery({ queryKey: ['candidates', search], queryFn: () => listCandidates(search) })

  const startMutation = useMutation({
    mutationFn: (candidateId: string) => startAssessment(candidateId, jobId),
    onSuccess: (assessment) => onSelected(assessment.id),
  })

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <h2>Assess a candidate</h2>
        <input className="text-input-wide" placeholder="Search name, email or phone…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="find-candidate-results">
          {candidates?.map((c) => (
            <div key={c.id} className="find-candidate-row">
              <div>
                <strong>{c.name}</strong>
                <div className="muted">{c.email} · {c.experience_years} yrs</div>
              </div>
              <button className="btn btn-secondary" onClick={() => startMutation.mutate(c.id)} disabled={startMutation.isPending}>
                Select &amp; screen
              </button>
            </div>
          ))}
          {candidates?.length === 0 && <p className="muted">No candidates match. Add one from the Candidates directory first.</p>}
        </div>
        <div className="row-between" style={{ marginTop: 'var(--space-4)' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
