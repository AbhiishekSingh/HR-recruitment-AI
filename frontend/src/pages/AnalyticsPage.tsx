import { useQuery } from '@tanstack/react-query'
import { getFunnel, getByRole } from '../api/analytics'
import './AnalyticsPage.css'

export default function AnalyticsPage() {
  const { data: funnel } = useQuery({ queryKey: ['funnel'], queryFn: getFunnel })
  const { data: byRole } = useQuery({ queryKey: ['byRole'], queryFn: getByRole })

  const maxStage = funnel ? Math.max(...Object.values(funnel), 1) : 1

  return (
    <div className="container analytics-page">
      <h1>Analytics</h1>

      <div className="card" style={{ marginBottom: 'var(--space-5)' }}>
        <h2>Hiring funnel</h2>
        {funnel && Object.entries(funnel).map(([label, val]) => (
          <div key={label} className="funnel-row">
            <span className="funnel-label">{label}</span>
            <div className="funnel-track"><div className="funnel-fill" style={{ width: `${(val / maxStage) * 100}%` }} /></div>
            <span className="funnel-value">{val}</span>
          </div>
        ))}
      </div>

      <div className="card">
        <h2>Per-role breakdown</h2>
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
    </div>
  )
}
