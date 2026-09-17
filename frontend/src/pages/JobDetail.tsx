import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJob, triggerMatching, getShortlist } from '../api/jobs'
import { getCandidate } from '../api/resumes'
import RecommendationBadge from '../components/RecommendationBadge'
import './JobDetail.css'

export default function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>()
  const queryClient = useQueryClient()
  const [topK, setTopK] = useState(150)

  const { data: job } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
  })

  const { data: shortlist, isLoading: shortlistLoading } = useQuery({
    queryKey: ['shortlist', jobId],
    queryFn: () => getShortlist(jobId!),
    enabled: !!jobId,
  })

  const matchMutation = useMutation({
    mutationFn: () => triggerMatching(jobId!, topK),
    onSuccess: () => {
      // Matching runs async in Celery; poll the shortlist a few times so
      // results appear without a manual refresh.
      let attempts = 0
      const interval = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: ['shortlist', jobId] })
        attempts += 1
        if (attempts > 20) clearInterval(interval) // stop after ~2 minutes
      }, 6000)
    },
  })

  return (
    <div className="container job-detail">
      <h1>{job?.title || 'Loading...'}</h1>

      <div className="card match-controls">
        <div className="row">
          <label htmlFor="topk" className="muted">Candidates to consider (top-K):</label>
          <input
            id="topk"
            type="number"
            min={10}
            max={1000}
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            style={{ width: 90 }}
          />
          <button className="btn btn-primary" onClick={() => matchMutation.mutate()} disabled={matchMutation.isPending}>
            {matchMutation.isPending ? 'Starting...' : 'Run matching'}
          </button>
        </div>
        {matchMutation.isSuccess && (
          <p className="muted">Matching started — results will appear below as scoring completes.</p>
        )}
      </div>

      <div className="card">
        <h2>Shortlist</h2>
        {shortlistLoading && <p className="muted">Loading...</p>}
        {!shortlistLoading && shortlist?.length === 0 && (
          <p className="muted">No results yet. Run matching to score candidates against this job.</p>
        )}
        {shortlist && shortlist.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Score</th>
                <th>Recommendation</th>
                <th>Matched skills</th>
                <th>Missing skills</th>
              </tr>
            </thead>
            <tbody>
              {shortlist.map((r) => (
                <ShortlistRow key={r.candidate_id} result={r} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function ShortlistRow({ result }: { result: import('../types').MatchResult }) {
  const { data: candidate } = useQuery({
    queryKey: ['candidate', result.candidate_id],
    queryFn: () => getCandidate(result.candidate_id),
  })

  return (
    <tr>
      <td>{candidate?.name || candidate?.id.slice(0, 8) || '...'}</td>
      <td><strong>{result.score}</strong></td>
      <td><RecommendationBadge recommendation={result.recommendation} /></td>
      <td className="muted">{result.matched_skills.join(', ') || '—'}</td>
      <td className="muted">{result.missing_skills.join(', ') || '—'}</td>
    </tr>
  )
}
