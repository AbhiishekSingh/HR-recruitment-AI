import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCandidates, uploadResumes } from '../api/resumes'
import './Dashboard.css'

const STATUS_LABELS: Record<string, string> = {
  queued: 'Queued',
  extracting: 'Extracting text',
  embedding: 'Generating embedding',
  ready: 'Ready',
  failed: 'Failed',
  needs_review: 'Needs review',
}

export default function Dashboard() {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)

  const { data: candidates, isLoading } = useQuery({
    queryKey: ['candidates'],
    queryFn: listCandidates,
    // Poll while any candidate is still processing, so status updates show up
    // without the person needing to manually refresh the page.
    refetchInterval: (query) => {
      const list = query.state.data
      const stillProcessing = list?.some((c) => !['ready', 'failed', 'needs_review'].includes(c.status))
      return stillProcessing ? 3000 : false
    },
  })

  const uploadMutation = useMutation({
    mutationFn: uploadResumes,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      if (fileInputRef.current) fileInputRef.current.value = ''
    },
    onError: () => setError('Upload failed. Check the file types (PDF/DOCX only).'),
  })

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setError(null)
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    uploadMutation.mutate(files)
  }

  return (
    <div className="container dashboard">
      <div className="row-between">
        <h1>Candidates</h1>
        <label className="btn btn-primary upload-btn">
          {uploadMutation.isPending ? 'Uploading...' : 'Upload resumes'}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx"
            multiple
            hidden
            onChange={handleFileChange}
            disabled={uploadMutation.isPending}
          />
        </label>
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="card">
        {isLoading && <p className="muted">Loading candidates...</p>}
        {!isLoading && candidates?.length === 0 && (
          <p className="muted">No resumes uploaded yet. Upload a PDF or DOCX to get started.</p>
        )}
        {!isLoading && candidates && candidates.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={c.id}>
                  <td>{c.name || <span className="muted">Pending extraction</span>}</td>
                  <td>{c.email || <span className="muted">—</span>}</td>
                  <td>
                    <span className={`status-dot status-${c.status}`} />
                    {STATUS_LABELS[c.status] || c.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
