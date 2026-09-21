import { Navigate } from 'react-router-dom'
import { ReactNode } from 'react'
import { useAuth } from '../context/AuthContext'

/**
 * Inverse of ProtectedRoute: for pages that only make sense when logged
 * OUT (Login, Register). If a session already exists, bounce straight to
 * the app instead of showing the auth form underneath an authenticated navbar.
 */
export default function GuestRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="container"><p className="muted">Loading...</p></div>
  if (user) return <Navigate to="/" replace />
  return <>{children}</>
}