import { ReactNode } from 'react'
import BackButton from './BackButton'
import './PageHeader.css'

interface PageHeaderProps {
  title: ReactNode
  eyebrow?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  /** Pass this on any page reached by drilling in (not from a top-level
   *  Navbar link) to show a "← Back" control above the title. Value is the
   *  fallback route if there's no in-app history to go back to. */
  backTo?: string
}

/**
 * Consistent page-title row used across every page: an optional back
 * control, a title (with optional small eyebrow line above it and subtitle
 * below), plus a right-aligned action slot that wraps under the title on
 * narrow screens.
 */
export default function PageHeader({ title, eyebrow, subtitle, actions, backTo }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="page-header-text">
        {backTo && <BackButton fallbackTo={backTo} />}
        {eyebrow && <p className="muted page-header-eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  )
}