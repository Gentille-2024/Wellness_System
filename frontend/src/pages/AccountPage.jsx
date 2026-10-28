import { useState } from 'react'
import api from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Alert, Avatar, Card, Field, PageHeader } from '../components/ui'
import useForm from '../hooks/useForm'

// Every role: see my details, update my contact info, change my password
export default function AccountPage() {
  const { user, reloadUser } = useAuth()
  const employee = user.employee
  const displayName = user.full_name || user.username

  const [profileNotice, setProfileNotice] = useState('')
  const [passwordNotice, setPasswordNotice] = useState('')

  const profile = useForm(employee ? { email: user.email, phone: employee.phone } : { email: user.email })
  const password = useForm({ current_password: '', password: '', password_confirm: '' })

  const saveProfile = profile.submit(async (values) => {
    setProfileNotice('')
    await api.patch('/me/', values)
    await reloadUser() // refresh the name/email shown around the app
    setProfileNotice('Your details were saved.')
  })

  const savePassword = password.submit(async (values) => {
    setPasswordNotice('')
    const { data } = await api.post('/me/password/', values)
    password.setValues({ current_password: '', password: '', password_confirm: '' })
    setPasswordNotice(data.detail)
  })

  return (
    <>
      <PageHeader title="My account" subtitle="Your details and password." />

      <div className="grid-1-2">
        <Card>
          <div className="profile-summary">
            <Avatar name={displayName} size={64} />
            <div className="profile-name">{displayName}</div>
            <div className="muted">@{user.username}</div>
          </div>
          <dl className="details">
            <div>
              <dt>{user.role_names.length > 1 ? 'Roles' : 'Role'}</dt>
              <dd>{user.role_names.join(', ') || '—'}</dd>
            </div>
            {(user.company || employee) && (
              <div>
                <dt>Company</dt>
                <dd>{user.company?.name ?? 'EUCL'}</dd>
              </div>
            )}
            {employee && (
              <>
                <div>
                  <dt>Employee ID</dt>
                  <dd>{employee.employee_id}</dd>
                </div>
                <div>
                  <dt>Job</dt>
                  <dd>
                    {employee.position} · {employee.department}
                  </dd>
                </div>
              </>
            )}
          </dl>
          {employee && <p className="field-hint">To change your name or job details, ask EUCL HR.</p>}
        </Card>

        <div className="stack">
          <Card title="Contact details">
            <form onSubmit={saveProfile}>
              <Alert type="success">{profileNotice}</Alert>
              <Alert>{profile.errors._general}</Alert>
              <div className="form-grid">
                <Field label="Email" name="email" type="email" value={profile.values.email} onChange={profile.handleChange} error={profile.errors.email} required />
                {employee && (
                  <Field label="Phone" name="phone" type="tel" value={profile.values.phone} onChange={profile.handleChange} error={profile.errors.phone} required />
                )}
              </div>
              <button type="submit" className="btn btn-primary" disabled={profile.submitting}>
                {profile.submitting ? 'Saving…' : 'Save details'}
              </button>
            </form>
          </Card>

          <Card title="Change password">
            <form onSubmit={savePassword}>
              <Alert type="success">{passwordNotice}</Alert>
              <Alert>{password.errors._general}</Alert>
              <Field
                label="Current password"
                name="current_password"
                type="password"
                value={password.values.current_password}
                onChange={password.handleChange}
                error={password.errors.current_password}
                autoComplete="current-password"
                required
              />
              <div className="form-grid">
                <Field
                  label="New password"
                  name="password"
                  type="password"
                  value={password.values.password}
                  onChange={password.handleChange}
                  error={password.errors.password}
                  autoComplete="new-password"
                  hint="At least 8 characters, not too common."
                  required
                />
                <Field
                  label="Confirm new password"
                  name="password_confirm"
                  type="password"
                  value={password.values.password_confirm}
                  onChange={password.handleChange}
                  error={password.errors.password_confirm}
                  autoComplete="new-password"
                  required
                />
              </div>
              <button type="submit" className="btn btn-primary" disabled={password.submitting}>
                {password.submitting ? 'Saving…' : 'Change password'}
              </button>
            </form>
          </Card>
        </div>
      </div>
    </>
  )
}
