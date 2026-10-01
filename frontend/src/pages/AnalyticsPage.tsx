import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFunnel, getByRole } from '../api/analytics'
import { getDueFollowUps, getInvoiceStatus, formatDate, formatDateTime, formatMoney } from '../api/tracking'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import CandidateTrackingModal from '../components/CandidateTrackingModal'
import PageHeader from '../components/ui/PageHeader'
import EmptyState from '../components/ui/EmptyState'
import './AnalyticsPage.css'

export default function AnalyticsPage() {
  const { data: funnel } = useQuery({ queryKey: ['funnel'], queryFn: getFunnel })
  const { data: byRole } = useQuery({ queryKey: ['byRole'], queryFn: getByRole })

  const { data: dueFollowUps } = useQuery({ queryKey: ['dueFollowUps'], queryFn: () => getDueFollowUps(7) })
  const { data: invoiceRows } = useQuery({ queryKey: ['invoiceStatus'], queryFn: getInvoiceStatus })
  const [trackingId, setTrackingId] = useState<string | null>(null)

  const maxStage = funnel ? Math.max(...Object.values(funnel), 1) : 1

  // Overdue / Today / Upcoming, judged by the browser's local date.
  const now = new Date()
  const todayKey = now.toDateString()
  function dueLabel(iso: string): { text: string; variant: 'pass' | 'review' | 'shortlist' } {
    const d = new Date(iso)
    if (d.getTime() < now.getTime()) return { text: 'Overdue', variant: 'pass' }
    if (d.toDateString() === todayKey) return { text: 'Today', variant: 'review' }
    return { text: 'Upcoming', variant: 'shortlist' }
  }
  const overdueCount = (dueFollowUps || []).filter((f) => new Date(f.scheduled_at).getTime() < now.getTime()).length
  const pendingInvoices = (invoiceRows || []).filter((r) => r.stage === 'Joined' && !r.invoice_raised).length

  return (
    <div className="container analytics-page">
      <PageHeader title="Analytics" />

      <div className="card analytics-section">
        <h2>Hiring funnel</h2>
        {funnel && Object.entries(funnel).map(([label, val]) => (
          <div key={label} className="funnel-row">
            <span className="funnel-label">{label}</span>
            <div className="funnel-track"><div className="funnel-fill" style={{ width: `${(val / maxStage) * 100}%` }} /></div>
            <span className="funnel-value">{val}</span>
          </div>
        ))}
        {!funnel && <p className="muted">Loading funnel...</p>}
      </div>

      <div className="card analytics-section">
        <h2>
          Follow-ups due (next 7 days)
          {overdueCount > 0 && <span className="analytics-count-pass"> · {overdueCount} overdue</span>}
        </h2>
        {dueFollowUps && dueFollowUps.length === 0 ? (
          <EmptyState message="No follow-ups due." />
        ) : (
          <div className="table-responsive">
            <table className="table">
              <thead><tr><th>When</th><th>Candidate</th><th>Role / Company</th><th>Type</th><th></th></tr></thead>
              <tbody>
                {dueFollowUps?.map((f) => {
                  const due = dueLabel(f.scheduled_at)
                  return (
                    <tr key={f.id}>
                      <td><Badge variant={due.variant}>{due.text}</Badge><div className="muted">{formatDateTime(f.scheduled_at)}</div></td>
                      <td><strong>{f.candidate_name}</strong></td>
                      <td>{f.job_title}<div className="muted">{f.company_name}</div></td>
                      <td>{f.follow_up_type}</td>
                      <td><Button variant="secondary" size="sm" onClick={() => setTrackingId(f.assessment_id)}>Open →</Button></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card analytics-section">
        <h2>
          Selected &amp; joined — invoice status
          {pendingInvoices > 0 && <span className="analytics-count-pass"> · {pendingInvoices} invoice{pendingInvoices === 1 ? '' : 's'} pending</span>}
        </h2>
        {invoiceRows && invoiceRows.length === 0 ? (
          <EmptyState message="No selected candidates yet." />
        ) : (
          <div className="table-responsive">
            <table className="table">
              <thead><tr><th>Candidate</th><th>Role / Company</th><th>Stage</th><th>CTC / Joining</th><th>Invoice</th><th></th></tr></thead>
              <tbody>
                {invoiceRows?.map((r) => (
                  <tr key={r.assessment_id}>
                    <td><strong>{r.candidate_name}</strong></td>
                    <td>{r.job_title}<div className="muted">{r.company_name}</div></td>
                    <td><Badge variant="shortlist">{r.stage}</Badge></td>
                    <td>{formatMoney(r.offered_ctc)}<div className="muted">Joining {formatDate(r.joining_date)}</div></td>
                    <td>
                      {r.stage === 'Joined' ? (
                        <>
                          <Badge variant={r.invoice_raised ? 'shortlist' : 'pass'}>{r.invoice_raised ? 'YES' : 'NO'}</Badge>
                          {r.invoice_raised && <div className="muted">{formatDate(r.invoice_date)}</div>}
                        </>
                      ) : <span className="muted">After joining</span>}
                    </td>
                    <td><Button variant="secondary" size="sm" onClick={() => setTrackingId(r.assessment_id)}>Open →</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Per-role breakdown</h2>
        {byRole && byRole.length === 0 ? (
          <EmptyState message="No roles to report on yet." />
        ) : (
          <div className="table-responsive">
            <table className="table">
              <thead><tr><th>Role</th><th>Company</th><th>Total</th><th>Pending</th><th>Screened</th></tr></thead>
              <tbody>
                {byRole?.map((r) => (
                  <tr key={r.job_id}>
                    <td><strong>{r.title}</strong></td>
                    <td>{r.company}</td>
                    <td>{r.total}</td>
                    <td>{r.pending}</td>
                    <td>{r.screened}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {trackingId && <CandidateTrackingModal assessmentId={trackingId} onClose={() => setTrackingId(null)} />}
    </div>
  )
}