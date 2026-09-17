import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import './Navbar.css'

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <Link to="/" className="navbar-brand">ShortlistOS</Link>
        {user && (
          <nav className="navbar-links">
            <Link to="/companies">Companies &amp; Roles</Link>
            <Link to="/candidates">Candidates</Link>
            <Link to="/analytics">Analytics</Link>
            <span className="muted">{user.name}</span>
            <button className="btn btn-secondary" onClick={handleLogout}>Log out</button>
          </nav>
        )}
      </div>
    </header>
  )
}
