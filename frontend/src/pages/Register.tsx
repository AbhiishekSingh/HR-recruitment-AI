import { useState, FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { register, login } from '../api/auth'
import { useAuth } from '../context/AuthContext'
import AuthLayout from '../components/AuthLayout'
import Button from '../components/ui/Button'
import './Register.css'

export default function Register() {
  const [name, setName] = useState('')
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
      await register(name, email, password)
      // Auto-login right after registering, so the person doesn't have to
      // re-enter their credentials on a second screen.
      const token = await login(email, password)
      setToken(token)
      navigate('/')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Registration failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Create an account"
      footer={<>Already have an account? <Link to="/login">Log in</Link></>}
    >
      <form className="register-form" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="name">Name</label>
          <input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {error && <p className="error-text" role="alert">{error}</p>}
        <Button type="submit" loading={loading} block>
          {loading ? 'Creating account...' : 'Register'}
        </Button>
      </form>
    </AuthLayout>
  )
}
