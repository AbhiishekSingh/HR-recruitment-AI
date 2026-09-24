import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCompanies, createCompany, viewCompanyDocument } from '../api/companies'
import { listJobs, createJob } from '../api/jobs'
import PageHeader from '../components/ui/PageHeader'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import Badge from '../components/ui/Badge'
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
    const documentFile = fd.get('document') as File | null
    companyMutation.mutate({
      name: String(fd.get('name')),
      industry: String(fd.get('industry')),
      contact_name: String(fd.get('contact_name')),
      contact_email: String(fd.get('contact_email')),
      gst_number: String(fd.get('gst_number')),
      tier: String(fd.get('tier') || 'Standard'),
      document: documentFile && documentFile.size > 0 ? documentFile : null,
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
      <PageHeader
        title="Companies & roles"
        actions={
          <Button variant={showCompanyForm ? 'secondary' : 'primary'} onClick={() => setShowCompanyForm((v) => !v)}>
            {showCompanyForm ? 'Cancel' : '+ Onboard company'}
          </Button>
        }
      />

      {showCompanyForm && (
        <form className="card" onSubmit={handleCompanySubmit} style={{ marginBottom: 'var(--space-5)' }}>
          <div className="field">
            <label>Company details document (PDF or Word, max 5MB)</label>
            <input name="document" type="file" accept=".pdf,.doc,.docx" />
          </div>
          <div className="field"><label>Company name</label><input name="name" required /></div>
          <div className="field"><label>Industry</label><input name="industry" /></div>
          <div className="field"><label>Primary contact</label><input name="contact_name" /></div>
          <div className="field"><label>Contact email</label><input name="contact_email" type="email" /></div>
          <div className="field"><label>GST number</label><input name="gst_number" placeholder="22AAAAA0000A1Z5" maxLength={15} style={{ textTransform: 'uppercase' }} /></div>
          {/* <div className="field">
            <label>Tier</label>
            <select name="tier" defaultValue="Standard">
              <option>Standard</option>
              <option>Premium</option>
            </select>
          </div> */}
          {companyMutation.isError && (
            <p className="error-text" role="alert">
              Could not save — check the GST number format and that the document is a PDF/Word file under 5MB.
            </p>
          )}
          <Button type="submit" loading={companyMutation.isPending}>
            {companyMutation.isPending ? 'Saving...' : 'Onboard company'}
          </Button>
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
                <p className="muted">
                  {company.industry} · {company.contact_name}
                  {company.gst_number && <> · GST: {company.gst_number}</>}
                </p>
                {company.document_path && (
                  <button
                    type="button"
                    className="link-button muted"
                    onClick={() => viewCompanyDocument(company)}
                  >
                    View uploaded document ↗
                  </button>
                )}
              </div>
              <Button
                variant="secondary"
                onClick={() => setJdFormForCompany(jdFormForCompany === company.id ? null : company.id)}
              >
                + New requisition
              </Button>
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
                <Button type="submit" loading={jobMutation.isPending}>
                  {jobMutation.isPending ? 'Creating...' : 'Create requisition'}
                </Button>
              </form>
            )}

            {companyJobs.length === 0 ? (
              <EmptyState message="No requisitions yet for this company." />
            ) : (
              <div className="table-responsive">
                <table className="table">
                  <thead><tr><th>Role</th><th>Locations</th><th>Budget</th><th>Experience</th><th>Status</th><th></th></tr></thead>
                  <tbody>
                    {companyJobs.map((jd) => (
                      <tr key={jd.id}>
                        <td><strong>{jd.title}</strong></td>
                        <td>{jd.locations.join(', ')}</td>
                        <td>₹{(jd.budget_min / 100000).toFixed(1)}L – ₹{(jd.budget_max / 100000).toFixed(1)}L</td>
                        <td>{jd.experience_min}–{jd.experience_max} yrs</td>
                        <td><Badge variant={jd.status === 'Open' ? 'shortlist' : 'pass'}>{jd.status}</Badge></td>
                        <td><Button variant="secondary" size="sm" onClick={() => navigate(`/pipeline/${jd.id}`)}>Open pipeline →</Button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}
