import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getCandidateAssessments } from '../api/assessments'
import { listJobs } from '../api/jobs'
import { BUCKET_LABELS } from '../types'
import type { AssessmentScored, Candidate } from '../types'
import Button from './ui/Button'
import Badge from './ui/Badge'
import EmptyState from './ui/EmptyState'
import ResumeManager from './ResumeManager'
import './CandidateAssessmentsModal.css'

interface CandidateAssessmentsModalProps {
  candidate: Candidate
  onClose: () => void
  onScreen: (assessment: AssessmentScored, jobTitle: string) => void
}

/**
 * Shows every Assessment connected to one candidate — one row per job
 * they've been put forward for, each with its own score/status, since a
 * candidate is job-independent but can have many candidate+job Assessments.
 */
export default function CandidateAssessmentsModal({ candidate: initialCandidate, onClose, onScreen }: CandidateAssessmentsModalProps) {
  // Local copy so a resume upload/delete updates this view immediately
  // without needing the parent list to refetch first.
  const [candidate, setCandidate] = useState(initialCandidate)

  const { data: assessments, isLoading } = useQuery({
    queryKey: ['candidateAssessments', candidate.id],
    queryFn: () => getCandidateAssessments(candidate.id),
  })

  // Jobs are already fetched/cached elsewhere (e.g. CompaniesPage) under the
  // same query key, so this just reuses that cache to resolve job titles.
  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: () => listJobs() })

  function jobTitle(jobId: string) {
    return jobs?.find((j) => j.id === jobId)?.title || `Job ${jobId.slice(0, 8)}`
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-panel-wide" onClick={(e) => e.stopPropagation()}>
        <h2>{candidate.name}</h2>
        <p className="muted candidate-modal-subtitle">{candidate.email} · {candidate.experience_years} yrs experience</p>

        <ResumeManager candidate={candidate} onChanged={setCandidate} />

        {isLoading && <p className="muted">Loading assessments...</p>}

        {!isLoading && assessments?.length === 0 && (
          <EmptyState message="No assessments yet. This candidate hasn't been put forward for a role." />
        )}

        {assessments && assessments.length > 0 && (
          <div className="candidate-assessment-list">
            {assessments.map((a) => (
              <div key={a.id} className="candidate-assessment-row">
                <div className="candidate-assessment-info">
                  <strong>{jobTitle(a.job_id)}</strong>
                  <div className="row candidate-assessment-meta">
                    <Badge variant={
                      a.bucket === 'strong' || a.bucket === 'good' ? 'shortlist' :
                      a.bucket === 'rejected' || a.bucket === 'notrec' ? 'pass' : 'review'
                    }>
                      {BUCKET_LABELS[a.bucket]}
                    </Badge>
                    <span className="muted">
                      Score: <strong>{a.bucket === 'pending' ? a.ai_score ?? '—' : a.final_score ?? '—'}</strong>
                    </span>
                    {a.sent_to_client && <span className="muted">Sent to client</span>}
                  </div>
                </div>
                <Button variant="secondary" size="sm" onClick={() => onScreen(a, jobTitle(a.job_id))}>
                  {a.bucket === 'pending' ? 'Complete screening →' : 'Edit screening'}
                </Button>
              </div>
            ))}
          </div>
        )}

        <div className="row-between candidate-modal-actions">
          <Button variant="secondary" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  )
}