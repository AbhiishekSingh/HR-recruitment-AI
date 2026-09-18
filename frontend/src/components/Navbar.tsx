import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Button from './ui/Button'
import './Navbar.css'

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  function handleLogout() {
    setMenuOpen(false)
    logout()
    navigate('/login')
  }

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <Link to="/" className="navbar-brand" onClick={() => setMenuOpen(false)}>ShortlistOS</Link>

        {user && (
          <>
            <button
              className="navbar-toggle"
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
            >
              <span />
              <span />
              <span />
            </button>

            <nav className={`navbar-links ${menuOpen ? 'navbar-links-open' : ''}`}>
              <Link to="/companies" onClick={() => setMenuOpen(false)}>Companies &amp; Roles</Link>
              <Link to="/candidates" onClick={() => setMenuOpen(false)}>Candidates</Link>
              <Link to="/analytics" onClick={() => setMenuOpen(false)}>Analytics</Link>
              <span className="muted navbar-user">{user.name}</span>
              <Button variant="secondary" size="sm" onClick={handleLogout}>Log out</Button>
            </nav>
          </>
        )}
      </div>
    </header>
  )
}
