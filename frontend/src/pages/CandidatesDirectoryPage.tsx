import { useState, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCandidates, createCandidate } from '../api/candidates'
import PageHeader from '../components/ui/PageHeader'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import './CandidatesDirectoryPage.css'

export default function CandidatesDirectoryPage() {
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)
  const queryClient = useQueryClient()

  const { data: candidates, isLoading } = useQuery({
    queryKey: ['candidates', search],
    queryFn: () => listCandidates(search || undefined),
  })

  const createMutation = useMutation({
    mutationFn: createCandidate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      setShowForm(false)
    },
  })

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    createMutation.mutate({
      name: String(fd.get('name')),
      email: String(fd.get('email')),
      phone: String(fd.get('phone') || ''),
      current_company: String(fd.get('current_company') || ''),
      experience_years: Number(fd.get('experience_years') || 0),
      resume_skills: String(fd.get('resume_skills') || '').split(',').map((s) => s.trim()).filter(Boolean),
      resume_summary: String(fd.get('resume_summary') || ''),
    })
  }

  return (
    <div className="container candidates-page">
      <PageHeader
        title="Candidates"
        subtitle="One record per person, independent of any specific role."
        actions={
          <Button variant={showForm ? 'secondary' : 'primary'} onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ Add one candidate'}
          </Button>
        }
      />

      {showForm && (
        <form className="card" onSubmit={handleSubmit} style={{ marginBottom: 'var(--space-5)' }}>
          <div className="grid-2">
            <div className="field"><label>Name</label><input name="name" required /></div>
            <div className="field"><label>Current company</label><input name="current_company" /></div>
          </div>
          <div className="grid-2">
            <div className="field"><label>Email</label><input name="email" type="email" required /></div>
            <div className="field"><label>Phone</label><input name="phone" /></div>
          </div>
          <div className="grid-2">
            <div className="field"><label>Experience (yrs)</label><input name="experience_years" type="number" step="0.5" /></div>
            <div className="field"><label>Skills (comma separated)</label><input name="resume_skills" placeholder="React, TypeScript" /></div>
          </div>
          <div className="field"><label>Resume summary</label><textarea name="resume_summary" rows={2} /></div>
          {createMutation.isError && <p className="error-text" role="alert">Could not save — check the email isn't already in use.</p>}
          <Button type="submit" loading={createMutation.isPending}>
            {createMutation.isPending ? 'Saving...' : 'Save candidate'}
          </Button>
        </form>
      )}

      <input className="text-input-wide candidates-search" placeholder="Search name, email, or phone…" value={search} onChange={(e) => setSearch(e.target.value)} />

      <div className="card">
        {isLoading && <p className="muted">Loading...</p>}
        {!isLoading && candidates?.length === 0 && <EmptyState message="No candidates match." />}
        {candidates && candidates.length > 0 && (
          <div className="table-responsive">
            <table className="table">
              <thead><tr><th>Candidate</th><th>Contact</th><th>Experience</th><th>Skills</th><th>Status</th></tr></thead>
              <tbody>
                {candidates.map((c) => (
                  <tr key={c.id}>
                    <td><strong>{c.name}</strong><div className="muted">{c.current_company}</div></td>
                    <td>{c.email}<div className="muted">{c.phone}</div></td>
                    <td>{c.experience_years} yrs</td>
                    <td className="muted">{c.resume_skills.join(', ') || '—'}</td>
                    <td><span className="badge badge-review">{c.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
