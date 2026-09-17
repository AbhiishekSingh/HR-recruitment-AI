import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCompanies, createCompany } from '../api/companies'
import { listJobs, createJob } from '../api/jobs'
import './CompaniesPage.css'

export default function CompaniesPage() {
  const [showCompanyForm, setShowCompanyForm] = useState(false)
  const [jdFormForCompany, setJdFormForCompany] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data: companies, isLoading } = useQuery({ queryKey: ['companies'], queryFn: listCompanies })
  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: () => listJobs() })

  const companyMutation = useMutation({
    mutationFn: createCompany,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] })
      setShowCompanyForm(false)
    },
  })

  const jobMutation = useMutation({
    mutationFn: createJob,
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      setJdFormForCompany(null)
      navigate(`/pipeline/${job.id}`)
    },
  })

  function handleCompanySubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    companyMutation.mutate({
      name: String(fd.get('name')),
      industry: String(fd.get('industry')),
      contact_name: String(fd.get('contact_name')),
      contact_email: String(fd.get('contact_email')),
      tier: String(fd.get('tier')),
    })
  }

  function handleJobSubmit(e: FormEvent<HTMLFormElement>, companyId: string) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    jobMutation.mutate({
      company_id: companyId,
      title: String(fd.get('title')),
      locations: String(fd.get('locations')).split(',').map((s) => s.trim()).filter(Boolean),
      budget_min: Number(fd.get('budget_min')),
      budget_max: Number(fd.get('budget_max')),
      experience_min: Number(fd.get('experience_min')),
      experience_max: Number(fd.get('experience_max')),
      max_notice_days: Number(fd.get('max_notice_days')),
      required_skills: String(fd.get('required_skills')).split(',').map((s) => s.trim()).filter(Boolean),
      raw_text: String(fd.get('raw_text') || ''),
    })
  }

  return (
    <div className="container companies-page">
      <div className="row-between">
        <h1>Companies &amp; roles</h1>
        <button className="btn btn-primary" onClick={() => setShowCompanyForm((v) => !v)}>
          {showCompanyForm ? 'Cancel' : '+ Onboard company'}
        </button>
      </div>

      {showCompanyForm && (
        <form className="card" onSubmit={handleCompanySubmit} style={{ marginBottom: 'var(--space-5)' }}>
          <div className="field"><label>Company name</label><input name="name" required /></div>
          <div className="field"><label>Industry</label><input name="industry" /></div>
          <div className="field"><label>Primary contact</label><input name="contact_name" /></div>
          <div className="field"><label>Contact email</label><input name="contact_email" type="email" /></div>
          <div className="field">
            <label>Tier</label>
            <select name="tier" defaultValue="Standard">
              <option>Standard</option>
              <option>Premium</option>
            </select>
          </div>
          <button className="btn btn-primary" type="submit" disabled={companyMutation.isPending}>
            {companyMutation.isPending ? 'Saving...' : 'Onboard company'}
          </button>
        </form>
      )}

      {isLoading && <p className="muted">Loading companies...</p>}

      {companies?.map((company) => {
        const companyJobs = jobs?.filter((j) => j.company_id === company.id) || []
        return (
          <section key={company.id} className="card company-block">
            <div className="row-between">
              <div>
                <h2>{company.name}</h2>
                <p className="muted">{company.industry} · {company.contact_name}</p>
              </div>
              <button
                className="btn btn-secondary"
                onClick={() => setJdFormForCompany(jdFormForCompany === company.id ? null : company.id)}
              >
                + New requisition
              </button>
            </div>

            {jdFormForCompany === company.id && (
              <form className="jd-form" onSubmit={(e) => handleJobSubmit(e, company.id)}>
                <div className="field"><label>Role title</label><input name="title" required /></div>
                <div className="field"><label>Locations (comma separated)</label><input name="locations" placeholder="Mumbai, Remote" /></div>
                <div className="row">
                  <div className="field"><label>Budget min (₹)</label><input name="budget_min" type="number" required /></div>
                  <div className="field"><label>Budget max (₹)</label><input name="budget_max" type="number" required /></div>
                </div>
                <div className="row">
                  <div className="field"><label>Experience min (yrs)</label><input name="experience_min" type="number" step="0.5" required /></div>
                  <div className="field"><label>Experience max (yrs)</label><input name="experience_max" type="number" step="0.5" required /></div>
                </div>
                <div className="field"><label>Max notice period (days)</label><input name="max_notice_days" type="number" defaultValue={45} required /></div>
                <div className="field"><label>Required skills (comma separated)</label><input name="required_skills" placeholder="React, TypeScript" required /></div>
                <div className="field"><label>Job description (optional, for AI extraction later)</label><textarea name="raw_text" rows={3} /></div>
                <button className="btn btn-primary" type="submit" disabled={jobMutation.isPending}>
                  {jobMutation.isPending ? 'Creating...' : 'Create requisition'}
                </button>
              </form>
            )}

            {companyJobs.length === 0 ? (
              <p className="muted">No requisitions yet for this company.</p>
            ) : (
              <table className="table">
                <thead><tr><th>Role</th><th>Locations</th><th>Budget</th><th>Experience</th><th>Status</th><th></th></tr></thead>
                <tbody>
                  {companyJobs.map((jd) => (
                    <tr key={jd.id}>
                      <td><strong>{jd.title}</strong></td>
                      <td>{jd.locations.join(', ')}</td>
                      <td>₹{(jd.budget_min / 100000).toFixed(1)}L – ₹{(jd.budget_max / 100000).toFixed(1)}L</td>
                      <td>{jd.experience_min}–{jd.experience_max} yrs</td>
                      <td><span className={`badge ${jd.status === 'Open' ? 'badge-shortlist' : 'badge-pass'}`}>{jd.status}</span></td>
                      <td><button className="btn btn-secondary" onClick={() => navigate(`/pipeline/${jd.id}`)}>Open pipeline →</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )
      })}
    </div>
  )
}
