import type { MatchResult } from '../types'

export default function RecommendationBadge({ recommendation }: { recommendation: MatchResult['recommendation'] }) {
  const cls =
    recommendation === 'Shortlist' ? 'badge-shortlist' :
    recommendation === 'Review' ? 'badge-review' : 'badge-pass'

  return <span className={`badge ${cls}`}>{recommendation}</span>
}
