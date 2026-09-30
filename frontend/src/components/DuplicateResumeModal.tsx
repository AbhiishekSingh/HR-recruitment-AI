import type { DuplicateMatch } from '../types'
import Button from './ui/Button'
import './DuplicateResumeModal.css'

interface DuplicateResumeModalProps {
  fileName: string
  matches: DuplicateMatch[]
  onReplace: (candidateId: string) => void
  onSaveAnyway: () => void
  onCancel: () => void
}

function matchedOnLabel(matchedOn: DuplicateMatch['matched_on']): string {
  if (matchedOn.includes('email') && matchedOn.includes('phone')) return 'email and phone number'
  if (matchedOn.includes('email')) return 'email'
  return 'phone number'
}

/** Shown before a resume actually gets uploaded, when
 *  POST /candidates/check-duplicate found an existing candidate with a
 *  matching email or phone number -- lets the recruiter decide whether this
 *  is the same person (replace the old resume) or a genuine second file
 *  worth keeping (save anyway), instead of silently creating a duplicate
 *  candidate row every time. When more than one existing candidate matches
 *  (rare -- e.g. a shared office phone number), each gets its own "Replace
 *  this one" action rather than picking one arbitrarily. */
export default function DuplicateResumeModal({ fileName, matches, onReplace, onSaveAnyway, onCancel }: DuplicateResumeModalProps) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <h2>Possible duplicate candidate</h2>
        <p className="muted">
          <strong>{fileName}</strong>'s {matchedOnLabel(matches[0].matched_on)} matches {matches.length === 1 ? 'an existing candidate' : `${matches.length} existing candidates`} already on file:
        </p>

        <ul className="duplicate-match-list">
          {matches.map((m) => (
            <li key={m.candidate_id} className="duplicate-match-row">
              <div>
                <strong>{m.name}</strong>
                <div className="muted">{m.email} · {m.phone || 'no phone on file'} · status: {m.status}</div>
              </div>
              <Button size="sm" variant="secondary" onClick={() => onReplace(m.candidate_id)}>
                Replace this one
              </Button>
            </li>
          ))}
        </ul>

        <p className="muted">Would you like to replace an existing candidate's resume, save this as a separate (duplicate) candidate anyway, or skip this file?</p>

        <div className="duplicate-modal-actions">
          <Button variant="secondary" onClick={onSaveAnyway}>Save anyway (keep both)</Button>
          <Button variant="secondary" onClick={onCancel}>Cancel this file</Button>
        </div>
      </div>
    </div>
  )
}
