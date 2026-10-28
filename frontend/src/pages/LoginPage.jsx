import { useEffect, useState } from 'react'
import { Navigate } from 'react-router'
import { errorMessage, signOutNotice } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Brand from '../components/Brand'
import Icon from '../components/Icon'
import { Alert } from '../components/ui'

const FEATURES = [
  { icon: 'map', text: 'See partner places and their services before you go' },
  { icon: 'checkin', text: 'Reception ticks the services you used in seconds' },
  { icon: 'card', text: 'Clear usage records and payments for every company' },
]

export default function LoginPage() {
  const { user, login } = useAuth()
  const [form, setForm] = useState({ username: '', password: '' })
  // Starts with the reason the app signed the user out, if any
  // (e.g. "This company has been deactivated! Please contact EUCL for more information.")
  const [error, setError] = useState(signOutNotice.read)
  const [submitting, setSubmitting] = useState(false)

  // Show that message once only
  useEffect(() => signOutNotice.clear(), [])

  // Already logged in? Go to the home page (which redirects by role)
  if (user) return <Navigate to="/" replace />

  const handleChange = (event) => {
    setForm({ ...form, [event.target.name]: event.target.value })
  }

  const handleSubmit = async (event) => {
    event.preventDefault() // stop the browser from reloading the page
    setError('')
    setSubmitting(true)
    try {
      await login(form.username, form.password)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login">
      <aside className="login-brand">
        <Brand />
        <div className="login-pitch">
          <h1>Wellness for every EUCL employee.</h1>
          <ul>
            {FEATURES.map((feature) => (
              <li key={feature.text}>
                <Icon name={feature.icon} />
                {feature.text}
              </li>
            ))}
          </ul>
        </div>
        <div className="login-foot">EUCL Wellness Management System</div>
      </aside>

      <main className="login-main">
        <form className="login-form" onSubmit={handleSubmit}>
          <h2>Sign in</h2>
          <p className="muted">Use the username and password you were given.</p>

          <Alert>{error}</Alert>

          <label className="field">
            <span className="field-label">Username</span>
            <input name="username" value={form.username} onChange={handleChange} autoComplete="username" autoFocus required />
          </label>

          <label className="field">
            <span className="field-label">Password</span>
            <input name="password" type="password" value={form.password} onChange={handleChange} autoComplete="current-password" required />
          </label>

          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </main>
    </div>
  )
}
