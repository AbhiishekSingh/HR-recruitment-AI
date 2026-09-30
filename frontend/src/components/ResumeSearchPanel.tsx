import { useState, FormEvent, Fragment } from 'react'
import { useQuery } from '@tanstack/react-query'
import { searchResumes, openCandidateResumeById } from '../api/candidates'
import Button from './ui/Button'
import EmptyState from './ui/EmptyState'
import type { ResumeSearchMatch } from '../types'
import './ResumeSearchPanel.css'

/** Wraps every [start, end) span in `highlights` (server-computed, see
 *  ResumeSearchResult's docstring in types/index.ts) in a <mark>, splitting
 *  the line's text around them. Spans are used as given -- they already
 *  come pre-sorted, non-overlapping, in character order from the backend. */
function highlightLine(match: ResumeSearchMatch) {
  const { text, highlights } = match
  if (!highlights.length) return text

  const parts: (string | JSX.Element)[] = []
  let cursor = 0
  highlights.forEach(([start, end], i) => {
    if (start > cursor) parts.push(text.slice(cursor, start))
    parts.push(<mark key={i}>{text.slice(start, end)}</mark>)
    cursor = end
  })
  if (cursor < text.length) parts.push(text.slice(cursor))
  return parts
}

/** Full-text search across every candidate's resume raw text -- separate
 *  from the directory's regular search box/filters, which only match
 *  structured fields (name, skills, qualification, etc) already extracted
 *  from the resume. This searches the resume's actual wording, so it finds
 *  a specific tool, client name, or phrase mentioned anywhere in it.
 *  Clicking a matched line opens that candidate's resume file, same as the
 *  directory's "View resume" action. */
export default function ResumeSearchPanel() {
  const [queryInput, setQueryInput] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [openError, setOpenError] = useState<string | null>(null)

  const { data: results, isLoading, isFetching, error } = useQuery({
    queryKey: ['resumeSearch', submittedQuery],
    queryFn: () => searchResumes(submittedQuery),
    enabled: submittedQuery.length > 0,
  })

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSubmittedQuery(queryInput.trim())
  }

  async function handleOpenMatch(candidateId: string, candidateName: string, hasResumeFile: boolean) {
    if (!hasResumeFile || openingId) return
    setOpenError(null)
    setOpeningId(candidateId)
    try {
      await openCandidateResumeById(candidateId, candidateName)
    } catch {
      setOpenError(`Couldn't open ${candidateName}'s resume -- the file may be missing from storage.`)
    } finally {
      setOpeningId(null)
    }
  }

  return (
    <div className="resume-search-panel">
      <form className="resume-search-form" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Search the text of every resume on file (e.g. a tool, a client name, a phrase)…"
          value={queryInput}
          onChange={(e) => setQueryInput(e.target.value)}
          className="resume-search-input"
        />
        <Button type="submit" disabled={!queryInput.trim()}>Search</Button>
      </form>

      {openError && <p className="form-error">{openError}</p>}

      {!submittedQuery && (
        <EmptyState message="Type a word or phrase to search across every uploaded resume's full text." />
      )}

      {submittedQuery && (isLoading || isFetching) && (
        <p className="muted">Searching…</p>
      )}

      {submittedQuery && error && (
        <p className="form-error">Something went wrong running that search. Try again.</p>
      )}

      {submittedQuery && results && results.length === 0 && !isFetching && (
        <EmptyState message={<>No resumes contain “{submittedQuery}”.</>} />
      )}

      {submittedQuery && results && results.length > 0 && (
        <ul className="resume-search-results">
          {results.map((r) => (
            <li key={r.candidate_id} className="resume-search-result">
              <div className="resume-search-result-header">
                <span className="resume-search-candidate-name">{r.candidate_name}</span>
                {(r.sector || r.position_role) && (
                  <span className="muted resume-search-candidate-meta">
                    {[r.position_role, r.sector].filter(Boolean).join(' · ')}
                  </span>
                )}
                {!r.has_resume_file && (
                  <span className="muted resume-search-candidate-meta">(resume file unavailable)</span>
                )}
              </div>
              <div className="resume-search-lines">
                {r.matches.map((m) => (
                  <Fragment key={m.line_number}>
                    <button
                      type="button"
                      className="resume-search-line"
                      disabled={!r.has_resume_file || openingId === r.candidate_id}
                      onClick={() => handleOpenMatch(r.candidate_id, r.candidate_name, r.has_resume_file)}
                      title={r.has_resume_file ? 'Open this resume' : 'Resume file unavailable'}
                    >
                      {highlightLine(m)}
                    </button>
                  </Fragment>
                ))}
                {r.has_more_matches && (
                  <span className="muted resume-search-more">more matches in this resume — open it to see the rest</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
