import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { listShortlisted, formatDate, formatDateTime, formatMoney } from '../api/tracking'
import { listCompanies } from '../api/companies'
import { PIPELINE_STAGES, stageBadgeVariant, jobActiveLabel } from '../types'
import PageHeader from '../components/ui/PageHeader'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import EmptyState from '../components/ui/EmptyState'
import CandidateTrackingModal from '../components/CandidateTrackingModal'
import './ShortlistedPage.css'

/**
 * Every shortlisted candidate across all companies and roles, with where
 * they are in the process: submitted to which client, next follow-up,
 * selection (CTC / joining date) and invoice status. "Manage" opens the
 * tracking modal for follow-ups, stage changes and history.
 */
export default function ShortlistedPage() {
  const navigate = useNavigate()
  const [companyId, setCompanyId] = useState('')
  const [stage, setStage] = useState('')
  const [search, setSearch] = useState('')
  const [invoice, setInvoice] = useState<'' | 'yes' | 'no'>('')
  const [minCtc, setMinCtc] = useState('')
  const [maxCtc, setMaxCtc] = useState('')
  const [openAssessmentId, setOpenAssessmentId] = useState<string | null>(null)

  const { data: companies } = useQuery({ queryKey: ['companies'], queryFn: listCompanies })
  const { data: rows, isLoading } = useQuery({
    queryKey: ['shortlisted', companyId, stage, search, invoice, minCtc, maxCtc],
    queryFn: () => listShortlisted({
      company_id: companyId,
      stage,
      search: search.trim(),
      invoice,
      min_ctc: minCtc ? Number(minCtc) : null,
      max_ctc: maxCtc ? Number(maxCtc) : null,
    }),
  })

  return (
    <div className="container shortlisted-page">
      <PageHeader
        title="Shortlisted candidates"
        subtitle="Track submissions, follow-ups, interviews, selection, joining and invoices."
      />

      <div className="row filter-row">
        <select value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
          <option value="">All companies</option>
          {(companies || []).map((c) => (
            <option key={c.id} value={c.id}>{c.name}{c.is_active === false ? ' (Inactive)' : ''}</option>
          ))}
        </select>
        <select value={stage} onChange={(e) => setStage(e.target.value)}>
          <option value="">All stages</option>
          {PIPELINE_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={invoice} onChange={(e) => setInvoice(e.target.value as '' | 'yes' | 'no')}>
          <option value="">Invoice: All</option>
          <option value="yes">Invoice: YES</option>
          <option value="no">Invoice: NO</option>
        </select>
      </div>

      <div className="row filter-row shortlisted-search-row">
        <input
          className="text-input-wide shortlisted-search"
          placeholder="Search name, email, phone or role…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="shortlisted-ctc" title="Filters on the candidate's Expected CTC">
          <span className="muted">Expected CTC ₹</span>
          <input
            className="text-input-wide"
            type="number"
            min={0}
            placeholder="Min"
            value={minCtc}
            onChange={(e) => setMinCtc(e.target.value)}
          />
          <span className="muted">–</span>
          <input
            className="text-input-wide"
            type="number"
            min={0}
            placeholder="Max"
            value={maxCtc}
            onChange={(e) => setMaxCtc(e.target.value)}
          />
        </div>
        {(search || minCtc || maxCtc || invoice || stage || companyId) && (
          <button
            type="button"
            className="link-button muted"
            onClick={() => { setSearch(''); setMinCtc(''); setMaxCtc(''); setInvoice(''); setStage(''); setCompanyId('') }}
          >
            Clear filters
          </button>
        )}
        <span className="muted">{rows?.length ?? 0} candidate{rows?.length === 1 ? '' : 's'}</span>
      </div>

      <div className="card">
        {isLoading && <p className="muted">Loading shortlisted candidates…</p>}
        {!isLoading && rows?.length === 0 && (
          <EmptyState message="No shortlisted candidates yet. Candidates appear here once a screening is marked 'Share to Client'." />
        )}
        {rows && rows.length > 0 && (
          <div className="table-responsive">
            <table className="table shortlisted-table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Role / Company</th>
                  <th>Stage</th>
                  <th>Submitted</th>
                  <th>Next follow-up</th>
                  <th>CTC / Joining</th>
                  <th>Invoice</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.assessment_id}>
                    <td>
                      <strong>{r.candidate_name}</strong>
                      <div className="muted">{r.candidate_email}</div>
                      {r.candidate_phone && <div className="muted">{r.candidate_phone}</div>}
                    </td>
                    <td>
                      <button type="button" className="link-button" onClick={() => navigate(`/pipeline/${r.job_id}`)}>
                        {r.job_title}
                      </button>
                      <Badge variant={r.job_status === 'Open' ? 'shortlist' : 'pass'}>{jobActiveLabel(r.job_status)}</Badge>
                      <div className="muted shortlisted-company">
                        {r.company_name}{' '}
                        <Badge variant={r.company_active ? 'shortlist' : 'pass'}>{r.company_active ? 'Active' : 'Inactive'}</Badge>
                      </div>
                    </td>
                    <td>
                      <Badge variant={stageBadgeVariant(r.stage)}>{r.stage || 'Shortlisted'}</Badge>
                    </td>
                    <td>
                      {r.submitted_on ? (
                        <>
                          <div>{formatDate(r.submitted_on)}</div>
                          <div className="muted">{r.submitted_to || r.company_name}</div>
                        </>
                      ) : <span className="muted">Not yet</span>}
                    </td>
                    <td>
                      {r.next_follow_up_at ? (
                        <>
                          <div className={r.overdue_follow_ups > 0 ? 'shortlisted-overdue' : ''}>
                            {formatDateTime(r.next_follow_up_at)}
                          </div>
                          <div className="muted">
                            {r.next_follow_up_type}
                            {r.overdue_follow_ups > 0 && ` · ${r.overdue_follow_ups} overdue`}
                          </div>
                        </>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td>
                      <div className="muted">Expected {formatMoney(r.expected_ctc)}</div>
                      {(r.offered_ctc != null || r.joining_date) && (
                        <>
                          <div>Offered {formatMoney(r.offered_ctc)}</div>
                          <div className="muted">Joining {formatDate(r.joining_date)}</div>
                        </>
                      )}
                    </td>
                    <td>
                      {r.stage === 'Joined' ? (
                        <>
                          <Badge variant={r.invoice_raised ? 'shortlist' : 'pass'}>{r.invoice_raised ? 'YES' : 'NO'}</Badge>
                          {r.invoice_raised && (
                            <div className="muted">{formatDate(r.invoice_date)}</div>
                          )}
                        </>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td>
                      <Button variant="secondary" size="sm" onClick={() => setOpenAssessmentId(r.assessment_id)}>
                        Manage →
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {openAssessmentId && (
        <CandidateTrackingModal assessmentId={openAssessmentId} onClose={() => setOpenAssessmentId(null)} />
      )}
    </div>
  )
}
