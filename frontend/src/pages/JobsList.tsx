import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { createJob } from '../api/jobs'
import './JobsList.css'

export default function JobsList() {
  const [title, setTitle] = useState('')
  const [rawText, setRawText] = useState('')
  const navigate = useNavigate()

  const createMutation = useMutation({
    mutationFn: () => createJob(title, rawText),
    onSuccess: (job) => navigate(`/jobs/${job.id}`),
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    createMutation.mutate()
  }

  return (
    <div className="container jobs-page">
      <h1>New job posting</h1>
      <form className="card" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="title">Job title</label>
          <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="raw_text">Job description</label>
          <textarea
            id="raw_text"
            rows={12}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Paste the full job description here..."
            required
          />
        </div>
        {createMutation.isError && <p className="error-text">Could not create the job posting.</p>}
        <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
          {createMutation.isPending ? 'Creating...' : 'Create & continue to matching'}
        </button>
      </form>
    </div>
  )
}
