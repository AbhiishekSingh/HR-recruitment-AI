import { ReactNode } from 'react'
import './PageHeader.css'

interface PageHeaderProps {
  title: ReactNode
  eyebrow?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
}

/**
 * Consistent page-title row used across every page: a title (with optional
 * small eyebrow line above it and subtitle below), plus a right-aligned
 * action slot that wraps under the title on narrow screens.
 */
export default function PageHeader({ title, eyebrow, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="page-header-text">
        {eyebrow && <p className="muted page-header-eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  )
}
