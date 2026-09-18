type BadgeVariant = 'shortlist' | 'review' | 'pass'

interface BadgeProps {
  variant: BadgeVariant
  children: React.ReactNode
}

/**
 * Presentational wrapper for the existing .badge-* classes. Pass whichever
 * variant matches the same status colors already used across the app
 * (shortlist = positive/open, review = neutral/pending, pass = negative/closed).
 */
export default function Badge({ variant, children }: BadgeProps) {
  return <span className={`badge badge-${variant}`}>{children}</span>
}
