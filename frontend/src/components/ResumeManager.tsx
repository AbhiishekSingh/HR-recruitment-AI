import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { uploadCandidateResume, deleteCandidateResume, viewCandidateResume } from '../api/candidates'
import type { Candidate } from '../types'
import Button from './ui/Button'
import './ResumeManager.css'

interface ResumeManagerProps {
  candidate: Candidate
  /** Called with the updated candidate after a successful upload/delete, so
   *  the caller can keep its own copy of the candidate in sync without a
   *  refetch. */
  onChanged: (candidate: Candidate) => void
}

/**
 * View / attach / replace / delete a candidate's resume — the one place
 * this app manages resume files, reused anywhere a candidate's resume
 * needs to be handled (currently the candidate assessments modal).
 */
export default function ResumeManager({ candidate, onChanged }: ResumeManagerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const queryClient = useQueryClient()

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadCandidateResume(candidate.id, file),
    onSuccess: (updated) => {
      onChanged(updated)
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      if (fileInputRef.current) fileInputRef.current.value = ''
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteCandidateResume(candidate.id),
    onSuccess: (updated) => {
      onChanged(updated)
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      setConfirmingDelete(false)
    },
  })

  const [viewing, setViewing] = useState(false)
  async function handleView() {
    setViewing(true)
    try {
      await viewCandidateResume(candidate)
    } finally {
      setViewing(false)
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) uploadMutation.mutate(file)
  }

  const hasResume = !!candidate.file_path
  const extension = candidate.file_path?.split('.').pop()?.toUpperCase()

  return (
    <div className="resume-manager">
      <div className="resume-manager-status">
        {hasResume ? (
          <span className="badge badge-shortlist">Resume attached{extension ? ` (${extension})` : ''}</span>
        ) : (
          <span className="badge badge-pass">No resume attached</span>
        )}
      </div>

      <div className="resume-manager-actions">
        {hasResume && (
          <Button variant="secondary" size="sm" onClick={handleView} loading={viewing}>
            View
          </Button>
        )}

        <label className="btn btn-secondary btn-sm resume-manager-upload-label">
          {uploadMutation.isPending ? 'Uploading...' : hasResume ? 'Replace' : 'Attach resume'}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx"
            hidden
            onChange={handleFileChange}
            disabled={uploadMutation.isPending}
          />
        </label>

        {hasResume && !confirmingDelete && (
          <Button variant="secondary" size="sm" onClick={() => setConfirmingDelete(true)}>
            Delete
          </Button>
        )}
        {hasResume && confirmingDelete && (
          <span className="resume-manager-confirm">
            <span className="muted">Remove this resume?</span>
            <Button variant="secondary" size="sm" onClick={() => deleteMutation.mutate()} loading={deleteMutation.isPending}>
              Yes, delete
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setConfirmingDelete(false)}>
              Cancel
            </Button>
          </span>
        )}
      </div>

      {uploadMutation.isError && <p className="error-text" role="alert">Could not upload — check it's a PDF or Word file under 5MB.</p>}
      {deleteMutation.isError && <p className="error-text" role="alert">Could not delete the resume.</p>}
    </div>
  )
}