import { useState, FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { login } from '../api/auth'
import { useAuth } from '../context/AuthContext'
import AuthLayout from '../components/AuthLayout'
import Button from '../components/ui/Button'
import './Login.css'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const { setToken } = useAuth()
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const token = await login(email, password)
      setToken(token)
      navigate('/')
    } catch {
      setError('Incorrect email or password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Log in"
      footer={<>No account? <Link to="/register">Register</Link></>}
    >
      <form className="login-form" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {error && <p className="error-text" role="alert">{error}</p>}
        <Button type="submit" loading={loading} block>
          {loading ? 'Logging in...' : 'Log in'}
        </Button>
      </form>
    </AuthLayout>
  )
}
