import { ReactNode } from 'react'

interface EmptyStateProps {
  message: ReactNode
}

/** Small, centered placeholder used wherever a list/table has no rows yet. */
export default function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <p className="muted">{message}</p>
    </div>
  )
}
