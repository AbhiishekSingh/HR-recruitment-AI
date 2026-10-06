import { useState, FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCandidates, createCandidate, uploadCandidateResume, updateCandidateClassification, reprocessCandidates, deleteCandidate, clearDuplicateFlag } from '../api/candidates'
import PageHeader from '../components/ui/PageHeader'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import EmptyState from '../components/ui/EmptyState'
import CandidateAssessmentsModal from '../components/CandidateAssessmentsModal'
import ScreeningFormModal from '../components/ScreeningFormModal'
import BulkUploadModal from '../components/BulkUploadModal'
import SectorPicker from '../components/SectorPicker'
import type { AssessmentScored, Candidate } from '../types'
import { MAX_RESUME_MB } from '../types'
import { RESUME_ACCEPT, resumeFileProblem } from '../utils/resumeFiles'
import './CandidatesDirectoryPage.css'

export default function CandidatesDirectoryPage() {
  const [search, setSearch] = useState('')
  const [searchParams, setSearchParams] = useSearchParams()
  // Set when arriving from a sector card on /candidates/categories
  // (?sector=IT); an empty string means "all sectors".
  const sectorFilter = searchParams.get('sector') || ''
  // Set from the status cards on /candidates/categories:
  // attention | processing | unclassified | duplicates
  const statusFilter = searchParams.get('status') || ''
  // Arriving from the sector-cards page's "+ Add one candidate" button
  // (/candidates?openForm=1) opens the form immediately, since that page
  // only shows cards and has no form of its own.
  const [showForm, setShowForm] = useState(() => searchParams.get('openForm') === '1')
  const [showFilters, setShowFilters] = useState(false)
  // Upload is the default, since a resume is all that's actually needed --
  // AI extraction fills in the rest. Manual entry is a fallback for a
  // candidate with no resume file (e.g. added from a phone screen), so it's
  // the only path where name/email stay required.
  const [addMode, setAddMode] = useState<'upload' | 'manual'>('upload')
  const [bulkFiles, setBulkFiles] = useState<File[]>([])
  // Pins every resume in this upload batch to a specific sector, bypassing
  // AI auto-classification for it -- pre-filled from the sector card the
  // recruiter arrived from (if any), since "add resumes while looking at
  // the IT card" almost always means "these are IT resumes". Left blank,
  // sector is auto-detected from each resume as before.
  const [uploadSector, setUploadSector] = useState(sectorFilter)
  const [manualSector, setManualSector] = useState('')
  // Files handed to BulkUploadModal, which runs the whole upload (pre-check,
  // duplicates, batched upload, AI-processing progress, retry) in a popup.
  const [uploadingFiles, setUploadingFiles] = useState<File[] | null>(null)
  // Bumped after each bulk upload to reset the <input type="file">.
  const [fileInputKey, setFileInputKey] = useState(0)
  const [activeCandidate, setActiveCandidate] = useState<Candidate | null>(null)
  // Full row + resolved job title, both already available from
  // CandidateAssessmentsModal — no extra fetch needed to open this form.
  const [screeningTarget, setScreeningTarget] = useState<{ assessment: AssessmentScored; jobTitle: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [editingSectorFor, setEditingSectorFor] = useState<string | null>(null)
  // Lifted out of the inline edit <form> for the same reason as
  // manualSector above -- SectorPicker is a controlled component, so its
  // value can't be read back via FormData the way the plain
  // position_role input next to it still is.
  const [editingSectorValue, setEditingSectorValue] = useState('')
  const queryClient = useQueryClient()

  // Advanced filters -- typed freely, only actually applied to the query
  // once "Apply filters" is clicked (avoids refetching on every keystroke).
  const [skillsInput, setSkillsInput] = useState('')
  const [minExpInput, setMinExpInput] = useState('')
  const [maxExpInput, setMaxExpInput] = useState('')
  const [qualificationInput, setQualificationInput] = useState('')
  const [appliedFilters, setAppliedFilters] = useState({ skills: '', minExp: '', maxExp: '', qualification: '' })

  function applyFilters() {
    setAppliedFilters({
      skills: skillsInput.trim(),
      minExp: minExpInput.trim(),
      maxExp: maxExpInput.trim(),
      qualification: qualificationInput.trim(),
    })
  }

  function clearAdvancedFilters() {
    setSkillsInput(''); setMinExpInput(''); setMaxExpInput(''); setQualificationInput('')
    setAppliedFilters({ skills: '', minExp: '', maxExp: '', qualification: '' })
  }

  const hasActiveAdvancedFilters = Object.values(appliedFilters).some(Boolean)

  const { data: candidates, isLoading } = useQuery({
    queryKey: ['candidates', search, sectorFilter, statusFilter, appliedFilters],
    queryFn: () => listCandidates({
      search: search || undefined,
      sector: sectorFilter || undefined,
      status: statusFilter || undefined,
      skills: appliedFilters.skills || undefined,
      min_experience: appliedFilters.minExp ? Number(appliedFilters.minExp) : undefined,
      max_experience: appliedFilters.maxExp ? Number(appliedFilters.maxExp) : undefined,
      qualification: appliedFilters.qualification || undefined,
    }),
    // Ingestion (extraction -> embedding) runs in the background via
    // Celery -- a candidate's row is still "queued"/"extracting" the
    // instant it's created, and only fills in with a real name/skills/
    // sector once that finishes a few seconds later. Without this, the
    // table would only ever show that stale first snapshot until something
    // else (navigating away and back, a manual refresh) forced a refetch.
    // Polling every 3s while anything is still in-flight keeps this page
    // current on its own; refetchInterval returning false once nothing is
    // pending stops the polling instead of running forever.
    refetchInterval: (query) => {
      const rows = query.state.data
      const stillProcessing = rows?.some((c) => ['queued', 'extracting', 'embedding'].includes(c.status))
      return stillProcessing ? 3000 : false
    },
  })

  const createMutation = useMutation({ mutationFn: createCandidate })
  const uploadMutation = useMutation({ mutationFn: ({ id, file }: { id: string; file: File }) => uploadCandidateResume(id, file) })
  const reclassifyMutation = useMutation({
    mutationFn: ({ id, sector, position_role }: { id: string; sector: string; position_role: string }) =>
      updateCandidateClassification(id, { sector, position_role: position_role || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      queryClient.invalidateQueries({ queryKey: ['candidateSectorCounts'] })
      setEditingSectorFor(null)
    },
  })

  function clearSectorFilter() {
    searchParams.delete('sector')
    setSearchParams(searchParams)
  }

  function clearStatusFilter() {
    searchParams.delete('status')
    setSearchParams(searchParams)
  }

  function refreshCandidateLists() {
    queryClient.invalidateQueries({ queryKey: ['candidates'] })
    queryClient.invalidateQueries({ queryKey: ['candidateSectorCounts'] })
    queryClient.invalidateQueries({ queryKey: ['candidateOverview'] })
  }

  // Re-runs AI processing on already-saved resumes (no re-upload).
  const retryMutation = useMutation({
    mutationFn: (ids: string[]) => reprocessCandidates(ids),
    onSuccess: refreshCandidateLists,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCandidate(id),
    onSuccess: refreshCandidateLists,
  })

  const notDuplicateMutation = useMutation({
    mutationFn: (id: string) => clearDuplicateFlag(id),
    onSuccess: refreshCandidateLists,
  })

  function handleDelete(c: Candidate) {
    if (window.confirm(`Delete ${c.name}? This removes them from all lists (their history is kept).`)) {
      deleteMutation.mutate(c.id)
    }
  }

  const STATUS_FILTER_LABELS: Record<string, string> = {
    attention: 'Needs attention: AI processing failed or got stuck',
    processing: 'Still processing',
    unclassified: 'Processed, but no sector assigned',
    duplicates: 'Possible duplicates: same email, phone or file as another candidate',
  }
  const retryableIds = (candidates || [])
    .filter((c) => c.file_path && (c.status === 'failed' || c.status === 'needs_review' || c.stuck))
    .map((c) => c.id)

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
        // Read from the lifted `manualSector` state, not FormData -- unlike
        // every other field here, SectorPicker is a controlled component
        // (it needs to be, to support its own "custom sector" free-text
        // mode), so it's never an uncontrolled `<select name="sector">` for
        // FormData to have captured in the first place.
        sector: manualSector.trim() || null,
        position_role: String(fd.get('position_role') || '') || null,
      })

      // Attach the resume as a second step against the candidate we just
      // created — the candidate record and the resume file are two
      // separate concerns handled by two endpoints, but from the person's
      // perspective it's one "add candidate" action.
      if (resumeFile && resumeFile.size > 0) {
        await uploadMutation.mutateAsync({ id: candidate.id, file: resumeFile })
      }

      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      queryClient.invalidateQueries({ queryKey: ['candidateSectorCounts'] })
      setShowForm(false)
      setManualSector('')
      e.currentTarget.reset()
    } catch (err: any) {
      setSubmitError(
        err?.response?.data?.detail || `Could not save — check the email isn't already in use, and the resume is a PDF/Word file under ${MAX_RESUME_MB}MB.`
      )
    } finally {
      setSubmitting(false)
    }
  }

  function handleBulkUpload() {
    if (bulkFiles.length === 0) return
    setUploadingFiles(bulkFiles)
  }

  function finishBulkUpload() {
    setUploadingFiles(null)
    setBulkFiles([])
    setFileInputKey((k) => k + 1)
    setUploadSector(sectorFilter)
  }

  function refreshAfterUpload() {
    refreshCandidateLists()
  }

  function handleReclassifySubmit(e: FormEvent<HTMLFormElement>, candidateId: string) {
    e.preventDefault()
    e.stopPropagation()
    const fd = new FormData(e.currentTarget)
    reclassifyMutation.mutate({
      id: candidateId,
      sector: editingSectorValue,
      position_role: String(fd.get('position_role') || ''),
    })
  }

  return (
    <div className="container candidates-page">
      <PageHeader
        title="Candidates"
        subtitle={
          sectorFilter
            ? `Showing ${sectorFilter} candidates only. Click a candidate to see every role they've been assessed against.`
            : "One record per person, independent of any specific role. Click a candidate to see every role they've been assessed against."
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => setShowFilters((v) => !v)}>
              {showFilters ? 'Hide filters' : 'Filters'}{hasActiveAdvancedFilters ? ' •' : ''}
            </Button>
            <Button
              variant={showForm ? 'secondary' : 'primary'}
              onClick={() => setShowForm((v) => !v)}
            >
              {showForm ? 'Cancel' : '+ Add one candidate'}
            </Button>
          </>
        }
      />

      {sectorFilter && (
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <Badge variant="review">{sectorFilter}</Badge>{' '}
          <button className="link-button" onClick={clearSectorFilter}>Clear filter</button>
        </div>
      )}

      {statusFilter && (
        <div className="status-filter-banner">
          <div>
            <Badge variant={statusFilter === 'attention' ? 'pass' : 'review'}>{STATUS_FILTER_LABELS[statusFilter] || statusFilter}</Badge>{' '}
            <button className="link-button" onClick={clearStatusFilter}>Show all candidates</button>
          </div>
          {retryableIds.length > 0 && (
            <Button size="sm" loading={retryMutation.isPending} onClick={() => retryMutation.mutate(retryableIds)}>
              Retry AI processing for all {retryableIds.length}
            </Button>
          )}
          {retryMutation.isSuccess && (
            <span className="muted">Re-queued {retryMutation.data?.queued}. Make sure the Celery worker is running.</span>
          )}
        </div>
      )}

      {showForm && (
        <div className="card" style={{ marginBottom: 'var(--space-5)' }}>
          <div className="add-mode-tabs">
            <button
              type="button"
              className={`add-mode-tab ${addMode === 'upload' ? 'add-mode-tab-active' : ''}`}
              onClick={() => setAddMode('upload')}
            >
              Upload resume(s)
            </button>
            <button
              type="button"
              className={`add-mode-tab ${addMode === 'manual' ? 'add-mode-tab-active' : ''}`}
              onClick={() => setAddMode('manual')}
            >
              Add manually (no resume)
            </button>
          </div>

          {addMode === 'upload' && (
            <div className="upload-mode">
              <p className="muted">
                Select one or more resumes (PDF or Word .docx, <strong>max {MAX_RESUME_MB}MB each</strong>; image files are not accepted).
                Any file that doesn't fit is listed before upload so you can skip it. Name, contact details,
                skills, experience, sector, and position are all extracted automatically — nothing
                else to fill in, unless you want to pin the sector yourself below.
              </p>
              <div className="field">
                <input
                  key={fileInputKey}
                  type="file"
                  accept={RESUME_ACCEPT}
                  multiple
                  onChange={(e) => setBulkFiles(Array.from(e.target.files || []))}
                />
              </div>
              <SectorPicker
                value={uploadSector}
                onChange={setUploadSector}
                helpText="pins every resume in this batch to this sector instead of auto-detecting it, and adds a new sector card if it's not one of the existing ones"
              />
              {bulkFiles.length > 0 && (() => {
                const problems = bulkFiles.filter((f) => resumeFileProblem(f)).length
                return (
                  <p className="muted">
                    {bulkFiles.length} file{bulkFiles.length === 1 ? '' : 's'} selected
                    {problems > 0 && <span className="error-text"> · {problems} can't be uploaded (you'll be asked to skip them)</span>}
                  </p>
                )
              })()}
              <Button onClick={handleBulkUpload} disabled={bulkFiles.length === 0 || uploadingFiles !== null}>
                {`Upload ${bulkFiles.length || ''} resume${bulkFiles.length === 1 ? '' : 's'}`}
              </Button>
            </div>
          )}

          {addMode === 'manual' && (
            <form onSubmit={handleSubmit}>
              <p className="muted">
                Use this only when there's no resume file to upload — name and email are required
                here since there's nothing to extract them from. Everything else is optional.
              </p>
              <div className="field">
                <label>Resume (optional — PDF or Word .docx, max {MAX_RESUME_MB}MB)</label>
                <input name="resume" type="file" accept={RESUME_ACCEPT} />
              </div>
              <div className="grid-2">
                <div className="field">
                  <label>Name</label>
                  <input name="name" required />
                </div>
                <div className="field">
                  <label>Current company</label>
                  <input name="current_company" />
                </div>
              </div>
              <div className="grid-2">
                <div className="field">
                  <label>Email</label>
                  <input name="email" type="email" required />
                </div>
                <div className="field">
                  <label>Phone</label>
                  <input name="phone" />
                </div>
              </div>
              <div className="grid-2">
                <div className="field">
                  <label>Experience (yrs)</label>
                  <input name="experience_years" type="number" step="0.5" />
                </div>
                <div className="field">
                  <label>Skills (comma separated)</label>
                  <input name="resume_skills" placeholder="React, TypeScript" />
                </div>
              </div>
              <div className="grid-2">
                <SectorPicker value={manualSector} onChange={setManualSector} helpText="or type a brand-new one" />
                <div className="field">
                  <label>Position / role (optional)</label>
                  <input name="position_role" placeholder="e.g. HR Recruiter" />
                </div>
              </div>
              <div className="field">
                <label>Resume summary</label>
                <textarea name="resume_summary" rows={2} />
              </div>
              {submitError && <p className="error-text" role="alert">{submitError}</p>}
              <Button type="submit" loading={submitting}>
                {submitting ? 'Saving...' : 'Save candidate'}
              </Button>
            </form>
          )}
        </div>
      )}

      <input className="text-input-wide candidates-search" placeholder="Search name, email, or phone…" value={search} onChange={(e) => setSearch(e.target.value)} />

      {showFilters && (
        <div className="card filters-panel" style={{ marginBottom: 'var(--space-4)' }}>
          <div className="grid-2">
            <div className="field">
              <label>Skills (comma separated — matches any)</label>
              <input value={skillsInput} onChange={(e) => setSkillsInput(e.target.value)} placeholder="React, Python, SQL" />
            </div>
            <div className="field">
              <label>Qualification (degree / institution)</label>
              <input value={qualificationInput} onChange={(e) => setQualificationInput(e.target.value)} placeholder="B.Tech, MBA, ..." />
            </div>
          </div>
          <div className="grid-2">
            <div className="field">
              <label>Min experience (yrs)</label>
              <input type="number" step="0.5" min="0" value={minExpInput} onChange={(e) => setMinExpInput(e.target.value)} />
            </div>
            <div className="field">
              <label>Max experience (yrs)</label>
              <input type="number" step="0.5" min="0" value={maxExpInput} onChange={(e) => setMaxExpInput(e.target.value)} />
            </div>
          </div>
          <div className="filters-actions">
            <Button onClick={applyFilters}>Apply filters</Button>
            <Button variant="secondary" onClick={clearAdvancedFilters}>Clear</Button>
          </div>
        </div>
      )}

      <div className="card">
        {isLoading && <p className="muted">Loading...</p>}
        {!isLoading && candidates?.length === 0 && <EmptyState message="No candidates match." />}
        {candidates && candidates.length > 0 && (
          <div className="table-responsive">
            <table className="table candidates-table">
              <thead><tr><th>Candidate</th><th>Contact</th><th>Experience</th><th>Sector / Role</th><th>Skills</th><th>Resume</th><th>Status</th></tr></thead>
              <tbody>
                {candidates.map((c) => (
                  <tr key={c.id} className="candidates-row" onClick={() => setActiveCandidate(c)}>
                    <td>
                      <strong>{c.name}</strong><div className="muted">{c.current_company}</div>
                      {c.possible_duplicate_of && (
                        <div className="duplicate-flag" onClick={(e) => e.stopPropagation()}>
                          ⧉ Possible duplicate of <strong>{c.possible_duplicate_of_name || 'another candidate'}</strong>
                          {' · '}
                          <button className="link-button" onClick={() => notDuplicateMutation.mutate(c.id)}>Not a duplicate</button>
                        </div>
                      )}
                    </td>
                    <td>{c.email}<div className="muted">{c.phone}</div></td>
                    <td>{c.experience_years} yrs</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {editingSectorFor === c.id ? (
                        <form className="sector-edit-form" onSubmit={(e) => handleReclassifySubmit(e, c.id)}>
                          <SectorPicker value={editingSectorValue} onChange={setEditingSectorValue} label="Sector" helpText="or type a new one" />
                          <input name="position_role" defaultValue={c.position_role || ''} placeholder="Position role" />
                          <Button type="submit" size="sm" loading={reclassifyMutation.isPending}>Save</Button>
                          <Button type="button" size="sm" variant="secondary" onClick={() => setEditingSectorFor(null)}>Cancel</Button>
                        </form>
                      ) : (
                        <div>
                          {c.sector ? <Badge variant="review">{c.sector}</Badge> : <span className="muted">Unclassified</span>}
                          {c.position_role && <div className="muted">{c.position_role}</div>}
                          <button className="link-button" onClick={() => { setEditingSectorFor(c.id); setEditingSectorValue(c.sector || '') }}>Edit</button>
                        </div>
                      )}
                    </td>
                    <td className="muted">{c.resume_skills.join(', ') || '—'}</td>
                    <td>
                      <Badge variant={c.file_path ? 'shortlist' : 'pass'}>{c.file_path ? 'Attached' : 'Missing'}</Badge>
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <Badge variant={
                        c.status === 'ready' ? 'shortlist'
                          : c.status === 'failed' || c.status === 'needs_review' || c.stuck ? 'pass'
                            : 'review'
                      }>
                        {c.stuck ? 'stuck' : c.status === 'needs_review' ? 'needs review' : c.status}
                      </Badge>
                      {c.status_detail && <div className="muted status-detail">{c.status_detail}</div>}
                      {c.stuck && <div className="muted status-detail">No progress for 15+ min. Is the Celery worker running?</div>}
                      <div className="row status-actions">
                        {c.file_path && (c.status === 'failed' || c.status === 'needs_review' || c.stuck) && (
                          <button className="link-button" onClick={() => retryMutation.mutate([c.id])}>Retry</button>
                        )}
                        {(statusFilter === 'attention' || statusFilter === 'duplicates' || c.possible_duplicate_of) && (
                          <button className="link-button status-delete" onClick={() => handleDelete(c)}>Delete</button>
                        )}
                      </div>
                    </td>
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

      {uploadingFiles && (
        <BulkUploadModal
          files={uploadingFiles}
          sector={uploadSector.trim() || undefined}
          onChanged={refreshAfterUpload}
          onClose={finishBulkUpload}
        />
      )}
    </div>
  )
}
