import { ReactNode } from 'react'
import './AuthLayout.css'

interface AuthLayoutProps {
  title: string
  children: ReactNode
  footer?: ReactNode
}

/**
 * Shared centered card layout used by both Login and Register, so the two
 * pages don't duplicate the same wrapper markup/styles while each still
 * keeps its own page file and its own (page-specific) stylesheet.
 */
export default function AuthLayout({ title, children, footer }: AuthLayoutProps) {
  return (
    <div className="auth-page">
      <div className="card auth-card">
        <h1>{title}</h1>
        {children}
        {footer && <p className="muted auth-switch">{footer}</p>}
      </div>
    </div>
  )
}
