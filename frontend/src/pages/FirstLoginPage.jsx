import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Brand from '../components/Brand'
import Icon from '../components/Icon'
import PasswordInput from '../components/PasswordInput'
import ThemeToggle from '../components/ThemeToggle'
import { Alert } from '../components/ui'

/**
 * First login: an EUCL employee that HR added creates their account by
 * proving who they are (Employee ID + the email or phone HR saved) and
 * choosing their own password. Then they sign in normally.
 */
export default function FirstLoginPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ employee_id: '', contact: '', password: '', password_confirm: '' })
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(null) // { username }

  if (user) return <Navigate to="/" replace />

  const handleChange = (event) => setForm({ ...form, [event.target.name]: event.target.value })

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setFieldErrors({})
    setSubmitting(true)
    try {
      const { data } = await api.post('/first-login/', form)
      setDone(data)
    } catch (err) {
      const data = err.response?.data
      if (data?.password || data?.password_confirm) {
        setFieldErrors({ password: data.password?.join?.(' ') ?? data.password, password_confirm: data.password_confirm })
      } else {
        setError(errorMessage(err))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login">
      <ThemeToggle className="login-theme" />
      <aside className="login-brand">
        <Brand />
        <div className="login-pitch">
          <h1>Welcome to EUCL Wellness.</h1>
          <ul>
            <li><Icon name="user" /> HR has already added you as an EUCL employee</li>
            <li><Icon name="key" /> Confirm who you are and choose your password</li>
            <li><Icon name="map" /> Then see partner places and the services you can use</li>
          </ul>
        </div>
        <div className="login-foot">EUCL Wellness Management System</div>
      </aside>

      <main className="login-main">
        {done ? (
          <div className="login-form">
            <h2>Your account is ready</h2>
            <Alert type="success">
              Your username is <strong>{done.username}</strong>. Sign in with it and the password you just chose.
            </Alert>
            <button type="button" className="btn btn-primary btn-block" onClick={() => navigate('/login', { state: { username: done.username } })}>
              Sign in
            </button>
          </div>
        ) : (
          <form className="login-form" onSubmit={handleSubmit}>
            <h2>Create your account</h2>
            <p className="muted">For your first sign-in. Use the Employee ID and the email or phone number HR has for you.</p>

            <Alert>{error}</Alert>

            <label className="field">
              <span className="field-label">Employee ID</span>
              <input name="employee_id" value={form.employee_id} onChange={handleChange} placeholder="e.g. EMP0009" autoComplete="off" autoFocus required />
            </label>

            <label className="field">
              <span className="field-label">Email or phone number</span>
              <input name="contact" value={form.contact} onChange={handleChange} placeholder="you@example.com or 0788 123 456" autoComplete="email" required />
            </label>

            <label className="field">
              <span className="field-label">Choose a password</span>
              <PasswordInput name="password" value={form.password} onChange={handleChange} autoComplete="new-password" required />
              {fieldErrors.password ? <span className="field-error">{fieldErrors.password}</span> : <span className="field-hint">At least 8 characters, not too common.</span>}
            </label>

            <label className="field">
              <span className="field-label">Confirm the password</span>
              <PasswordInput name="password_confirm" value={form.password_confirm} onChange={handleChange} autoComplete="new-password" required />
              {fieldErrors.password_confirm && <span className="field-error">{fieldErrors.password_confirm}</span>}
            </label>

            <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
              {submitting ? 'Creating…' : 'Create my account'}
            </button>

            <p className="login-switch">
              Already have an account? <Link to="/login">Sign in</Link>
            </p>
          </form>
        )}
      </main>
    </div>
  )
}
