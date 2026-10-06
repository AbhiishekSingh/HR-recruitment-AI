import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCompanies, createCompany, viewCompanyDocument, setCompanyActive } from '../api/companies'
import { listJobs, createJob, setJobStatus, attachJdFile, updateJob, viewJdFile } from '../api/jobs'
import { jobActiveLabel } from '../types'
import type { JobPosting, JDAttachResult } from '../types'
import RequisitionForm, { RequisitionSubmit, valuesFromJob, mergeJdFields } from '../components/RequisitionForm'
import EditJobModal from '../components/EditJobModal'
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

  // --- JD file on an existing job: attach/replace, then optionally update fields ---
  const [attachingFor, setAttachingFor] = useState<string | null>(null)
  const [attachError, setAttachError] = useState<{ jobId: string; text: string } | null>(null)
  const [jdReview, setJdReview] = useState<{ job: JobPosting; result: JDAttachResult } | null>(null)
  const [editingJob, setEditingJob] = useState<JobPosting | null>(null)

  async function handleAttachJd(job: JobPosting, file: File | undefined) {
    if (!file) return
    setAttachError(null)
    setAttachingFor(job.id)
    try {
      const result = await attachJdFile(job.id, file)
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      setJdReview({ job: result.job, result })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setAttachError({ jobId: job.id, text: typeof detail === 'string' ? detail : 'Could not attach the JD file.' })
    } finally {
      setAttachingFor(null)
    }
  }

  const updateJobMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RequisitionSubmit }) =>
      updateJob(id, {
        title: data.title, locations: data.locations,
        budget_min: data.budget_min, budget_max: data.budget_max,
        experience_min: data.experience_min, experience_max: data.experience_max,
        max_notice_days: data.max_notice_days, required_skills: data.required_skills,
        skill_groups: data.skill_groups, related_titles: data.related_titles,
        raw_text: data.raw_text,
        ...(data.requirements && Object.keys(data.requirements).length ? { requirements: data.requirements } : {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      setJdReview(null)
    },
  })

  async function openJd(job: JobPosting) {
    try {
      await viewJdFile(job)
    } catch {
      setAttachError({ jobId: job.id, text: 'Could not open the JD file.' })
    }
  }

  // Active/Inactive toggles -- labels only, nothing is blocked for inactive ones.
  const companyStatusMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) => setCompanyActive(id, isActive),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] })
      queryClient.invalidateQueries({ queryKey: ['shortlisted'] })
    },
  })

  const jobStatusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'Open' | 'Closed' }) => setJobStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      queryClient.invalidateQueries({ queryKey: ['shortlisted'] })
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

  function handleJobSubmit(data: RequisitionSubmit, companyId: string) {
    jobMutation.mutate({
      company_id: companyId,
      title: data.title,
      locations: data.locations,
      budget_min: data.budget_min,
      budget_max: data.budget_max,
      experience_min: data.experience_min,
      experience_max: data.experience_max,
      max_notice_days: data.max_notice_days,
      required_skills: data.required_skills,
      skill_groups: data.skill_groups,
      related_titles: data.related_titles,
      raw_text: data.raw_text,
      jd_upload_token: data.jd_upload_token,
      requirements: data.requirements,
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

      {editingJob && <EditJobModal job={editingJob} onClose={() => setEditingJob(null)} />}

      {jdReview && (
        <div className="modal-overlay" onClick={() => setJdReview(null)}>
          <div className="modal-panel modal-panel-wide" onClick={(e) => e.stopPropagation()}>
            <h2>JD attached to {jdReview.job.title}</h2>
            <p className="muted">
              <strong>{jdReview.result.parse.file_name}</strong> is saved. You can view it any time with "View JD".
              Do you also want to update this job's details from the JD? Check the values below and click Save, or close to keep the current details.
            </p>
            <RequisitionForm
              initialValues={jdReview.result.parse.error
                ? valuesFromJob(jdReview.job)
                : mergeJdFields(valuesFromJob(jdReview.job), jdReview.result.parse.fields, jdReview.result.parse.raw_text)}
              initialMissing={jdReview.result.parse.error ? [] : jdReview.result.parse.missing}
              notice={jdReview.result.parse.error
                ? <p className="jd-message jd-message-warn">{jdReview.result.parse.error}. The job's current details are shown.</p>
                : <p className="jd-message jd-message-ok">Values found in the JD are filled in; details not in the JD keep the job's current values.</p>}
              submitLabel={updateJobMutation.isPending ? 'Saving...' : 'Save job details'}
              loading={updateJobMutation.isPending}
              error={updateJobMutation.isError ? 'Could not update the job.' : null}
              onSubmit={(data) => updateJobMutation.mutate({
                id: jdReview.job.id,
                data: { ...data, requirements: jdReview.result.parse.error ? null : jdReview.result.parse.requirements },
              })}
              onCancel={() => setJdReview(null)}
            />
          </div>
        </div>
      )}

      {companies?.map((company) => {
        const companyJobs = jobs?.filter((j) => j.company_id === company.id) || []
        return (
          <section key={company.id} className="card company-block">
            <div className="row-between">
              <div>
                <div className="row company-title-row">
                  <h2>{company.name}</h2>
                  <Badge variant={company.is_active ? 'shortlist' : 'pass'}>{company.is_active ? 'Active' : 'Inactive'}</Badge>
                  <button
                    type="button"
                    className="link-button muted"
                    disabled={companyStatusMutation.isPending}
                    onClick={() => companyStatusMutation.mutate({ id: company.id, isActive: !company.is_active })}
                  >
                    Mark {company.is_active ? 'inactive' : 'active'}
                  </button>
                </div>
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
              <RequisitionForm
                allowJdUpload
                submitLabel={jobMutation.isPending ? 'Creating...' : 'Create requisition'}
                loading={jobMutation.isPending}
                error={jobMutation.isError ? ((jobMutation.error as any)?.response?.data?.detail || 'Could not create the requisition.') : null}
                onSubmit={(data) => handleJobSubmit(data, company.id)}
                onCancel={() => setJdFormForCompany(null)}
              />
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
                        <td>
                          <strong>{jd.title}</strong>
                          <div className="jd-file-actions">
                            <button type="button" className="link-button" onClick={() => setEditingJob(jd)}>Edit job</button>
                            {jd.has_jd_file && (
                              <button type="button" className="link-button" onClick={() => void openJd(jd)}>View JD ↗</button>
                            )}
                            <label className={`link-button muted jd-attach-label${attachingFor === jd.id ? ' is-busy' : ''}`}>
                              {attachingFor === jd.id ? 'Reading JD…' : jd.has_jd_file ? 'Replace JD' : 'Attach JD'}
                              <input
                                type="file"
                                accept=".pdf,.docx"
                                hidden
                                disabled={attachingFor !== null}
                                onChange={(e) => { void handleAttachJd(jd, e.target.files?.[0]); e.target.value = '' }}
                              />
                            </label>
                          </div>
                          {attachError?.jobId === jd.id && <div className="error-text">{attachError.text}</div>}
                        </td>
                        <td>{jd.locations.join(', ')}</td>
                        <td>₹{(jd.budget_min / 100000).toFixed(1)}L – ₹{(jd.budget_max / 100000).toFixed(1)}L</td>
                        <td>{jd.experience_min}–{jd.experience_max} yrs</td>
                        <td>
                          <Badge variant={jd.status === 'Open' ? 'shortlist' : 'pass'}>{jobActiveLabel(jd.status)}</Badge>
                          <div>
                            <button
                              type="button"
                              className="link-button muted"
                              disabled={jobStatusMutation.isPending}
                              onClick={() => jobStatusMutation.mutate({ id: jd.id, status: jd.status === 'Open' ? 'Closed' : 'Open' })}
                            >
                              Mark {jd.status === 'Open' ? 'inactive' : 'active'}
                            </button>
                          </div>
                        </td>
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
