import { Navigate } from 'react-router-dom'
import { ReactNode } from 'react'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="container"><p className="muted">Loading...</p></div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}
