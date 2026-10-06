import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFunnel, getByRole, getAiUsage } from '../api/analytics'
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
  const [usageDays, setUsageDays] = useState(30)
  const { data: usage } = useQuery({ queryKey: ['aiUsage', usageDays], queryFn: () => getAiUsage(usageDays) })
  const inr = (n: number) => `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

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

      <div className="card analytics-section">
        <div className="row-between">
          <h2>AI usage (exact)</h2>
          <select value={usageDays} onChange={(e) => setUsageDays(Number(e.target.value))} aria-label="Period">
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>
        {!usage && <p className="muted">Loading AI usage…</p>}
        {usage && usage.calls === 0 && (
          <EmptyState message="No AI calls recorded yet in this period. Costs appear here from the next resume upload, JD upload or AI score." />
        )}
        {usage && usage.calls > 0 && (
          <>
            <p className="ai-usage-total">
              <strong>{inr(usage.total_inr)}</strong>{' '}
              <span className="muted">(${usage.total_usd.toFixed(2)} · {usage.calls} AI calls · ₹{usage.usd_to_inr}/$)</span>
            </p>
            {usage.unpriced_calls > 0 && (
              <p className="error-text">{usage.unpriced_calls} calls used a model missing from the price table, so they are not included in the total.</p>
            )}
            <div className="table-responsive">
              <table className="table">
                <thead><tr><th>Task</th><th>Calls</th><th>Tokens in / out</th><th>Cost</th></tr></thead>
                <tbody>
                  {usage.by_task.map((t) => (
                    <tr key={t.task}>
                      <td>{t.label}</td>
                      <td>{t.calls}</td>
                      <td className="muted">{t.input_tokens.toLocaleString('en-IN')} / {t.output_tokens.toLocaleString('en-IN')}</td>
                      <td><strong>{inr(t.cost_inr)}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {usage.by_job.length > 0 && (
              <>
                <h3 className="ai-usage-sub">By job (JD reading + AI scoring)</h3>
                <div className="table-responsive">
                  <table className="table">
                    <thead><tr><th>Job</th><th>Company</th><th>Calls</th><th>Cost</th></tr></thead>
                    <tbody>
                      {usage.by_job.map((j) => (
                        <tr key={j.job_id}>
                          <td>{j.title}</td>
                          <td className="muted">{j.company}</td>
                          <td>{j.calls}</td>
                          <td><strong>{inr(j.cost_inr)}</strong></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </>
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
