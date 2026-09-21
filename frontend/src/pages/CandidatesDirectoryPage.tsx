import { useState, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCandidates, createCandidate, uploadCandidateResume } from '../api/candidates'
import PageHeader from '../components/ui/PageHeader'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import EmptyState from '../components/ui/EmptyState'
import CandidateAssessmentsModal from '../components/CandidateAssessmentsModal'
import ScreeningFormModal from '../components/ScreeningFormModal'
import type { AssessmentScored, Candidate } from '../types'
import './CandidatesDirectoryPage.css'

export default function CandidatesDirectoryPage() {
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [activeCandidate, setActiveCandidate] = useState<Candidate | null>(null)
  // Full row + resolved job title, both already available from
  // CandidateAssessmentsModal — no extra fetch needed to open this form.
  const [screeningTarget, setScreeningTarget] = useState<{ assessment: AssessmentScored; jobTitle: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: candidates, isLoading } = useQuery({
    queryKey: ['candidates', search],
    queryFn: () => listCandidates(search || undefined),
  })

  const createMutation = useMutation({ mutationFn: createCandidate })
  const uploadMutation = useMutation({ mutationFn: ({ id, file }: { id: string; file: File }) => uploadCandidateResume(id, file) })

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSubmitError(null)
    const fd = new FormData(e.currentTarget)
    const resumeFile = fd.get('resume') as File | null

    setSubmitting(true)
    try {
      const candidate = await createMutation.mutateAsync({
        name: String(fd.get('name')),
        email: String(fd.get('email')),
        phone: String(fd.get('phone') || ''),
        current_company: String(fd.get('current_company') || ''),
        experience_years: Number(fd.get('experience_years') || 0),
        resume_skills: String(fd.get('resume_skills') || '').split(',').map((s) => s.trim()).filter(Boolean),
        resume_summary: String(fd.get('resume_summary') || ''),
      })

      // Attach the resume as a second step against the candidate we just
      // created — the candidate record and the resume file are two
      // separate concerns handled by two endpoints, but from the person's
      // perspective it's one "add candidate" action.
      if (resumeFile && resumeFile.size > 0) {
        await uploadMutation.mutateAsync({ id: candidate.id, file: resumeFile })
      }

      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      setShowForm(false)
      e.currentTarget.reset()
    } catch (err: any) {
      setSubmitError(
        err?.response?.data?.detail || "Could not save — check the email isn't already in use, and the resume is a PDF/Word file under 5MB."
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="container candidates-page">
      <PageHeader
        title="Candidates"
        subtitle="One record per person, independent of any specific role. Click a candidate to see every role they've been assessed against."
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
          <div className="field">
            <label>Resume (PDF or Word, max 5MB)</label>
            <input name="resume" type="file" accept=".pdf,.docx" />
          </div>
          {submitError && <p className="error-text" role="alert">{submitError}</p>}
          <Button type="submit" loading={submitting}>
            {submitting ? 'Saving...' : 'Save candidate'}
          </Button>
        </form>
      )}

      <input className="text-input-wide candidates-search" placeholder="Search name, email, or phone…" value={search} onChange={(e) => setSearch(e.target.value)} />

      <div className="card">
        {isLoading && <p className="muted">Loading...</p>}
        {!isLoading && candidates?.length === 0 && <EmptyState message="No candidates match." />}
        {candidates && candidates.length > 0 && (
          <div className="table-responsive">
            <table className="table candidates-table">
              <thead><tr><th>Candidate</th><th>Contact</th><th>Experience</th><th>Skills</th><th>Resume</th><th>Status</th></tr></thead>
              <tbody>
                {candidates.map((c) => (
                  <tr key={c.id} className="candidates-row" onClick={() => setActiveCandidate(c)}>
                    <td><strong>{c.name}</strong><div className="muted">{c.current_company}</div></td>
                    <td>{c.email}<div className="muted">{c.phone}</div></td>
                    <td>{c.experience_years} yrs</td>
                    <td className="muted">{c.resume_skills.join(', ') || '—'}</td>
                    <td>
                      <Badge variant={c.file_path ? 'shortlist' : 'pass'}>{c.file_path ? 'Attached' : 'Missing'}</Badge>
                    </td>
                    <td><span className="badge badge-review">{c.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {activeCandidate && (
        <CandidateAssessmentsModal
          candidate={activeCandidate}
          onClose={() => setActiveCandidate(null)}
          onScreen={(assessment, jobTitle) => setScreeningTarget({ assessment, jobTitle })}
        />
      )}

      {screeningTarget && (
        <ScreeningFormModal
          assessment={screeningTarget.assessment}
          jobTitle={screeningTarget.jobTitle}
          onClose={() => setScreeningTarget(null)}
          onSaved={() => {
            setScreeningTarget(null)
            if (activeCandidate) {
              queryClient.invalidateQueries({ queryKey: ['candidateAssessments', activeCandidate.id] })
            }
          }}
        />
      )}
    </div>
  )
}