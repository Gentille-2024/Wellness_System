import { useState } from 'react'
import api from '../api/client'
import { PERMISSION_AREAS } from '../auth/access'
import Icon from './Icon'
import useApi from '../hooks/useApi'
import useForm from '../hooks/useForm'
import { formatMoney, monthStartISO, todayISO } from '../utils/format'
import { Alert, CheckboxGroup, Field, Loading, Modal, SelectField, TextAreaField } from './ui'

// Pop-up forms shared by several pages. Each one calls onSaved(result) after a
// successful save; the page then updates its list and closes the pop-up.

function FormFooter({ onClose, submitting, label, formId, disabled = false }) {
  return (
    <>
      <button type="button" className="btn btn-secondary" onClick={onClose}>
        Cancel
      </button>
      <button type="submit" form={formId} className="btn btn-primary" disabled={submitting || disabled}>
        {submitting ? 'Saving…' : label}
      </button>
    </>
  )
}

// ---------------------------------------------------------- EUCL employee

export function EmployeeFormModal({ employee, onClose, onSaved }) {
  const editing = Boolean(employee)
  const form = useForm(
    editing
      ? {
          first_name: employee.first_name,
          last_name: employee.last_name,
          email: employee.email,
          phone: employee.phone,
          department: employee.department,
          position: employee.position,
        }
      : {
          first_name: '',
          last_name: '',
          username: '',
          email: '',
          phone: '',
          department: '',
          position: '',
          password: '',
          password_confirm: '',
        },
  )
  const { values, errors, handleChange } = form

  const save = form.submit(async (formValues) => {
    const { data } = editing
      ? await api.patch(`/employees/${employee.id}/`, formValues)
      : await api.post('/employees/register/', formValues)
    onSaved(data)
  })

  return (
    <Modal
      wide
      title={editing ? `Edit ${employee.user_name}` : 'Onboard EUCL employee'}
      subtitle={editing ? employee.employee_id : 'All fields are required. The employee logs in with this username and password.'}
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label={editing ? 'Save changes' : 'Onboard employee'} formId="employee-form" />}
    >
      <form id="employee-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <h3 className="form-section">Personal details</h3>
        <div className="form-grid">
          <Field label="First name" name="first_name" value={values.first_name} onChange={handleChange} error={errors.first_name} required />
          <Field label="Last name" name="last_name" value={values.last_name} onChange={handleChange} error={errors.last_name} required />
          <Field label="Email" name="email" type="email" value={values.email} onChange={handleChange} error={errors.email} required />
          <Field label="Phone" name="phone" type="tel" value={values.phone} onChange={handleChange} error={errors.phone} placeholder="+250 788 123 456" required />
        </div>
        <h3 className="form-section">Job at EUCL</h3>
        <div className="form-grid">
          <Field label="Department" name="department" value={values.department} onChange={handleChange} error={errors.department} required />
          <Field label="Position" name="position" value={values.position} onChange={handleChange} error={errors.position} required />
        </div>
        {!editing && (
          <>
            <h3 className="form-section">Login</h3>
            <div className="form-grid">
              <Field label="Username" name="username" value={values.username} onChange={handleChange} error={errors.username} autoComplete="off" required />
              <span />
              <Field label="Password" name="password" type="password" value={values.password} onChange={handleChange} error={errors.password} autoComplete="new-password" hint="At least 8 characters, not too common." required />
              <Field label="Confirm password" name="password_confirm" type="password" value={values.password_confirm} onChange={handleChange} error={errors.password_confirm} autoComplete="new-password" required />
            </div>
          </>
        )}
      </form>
    </Modal>
  )
}

// ------------------------------------------------------------------ user

/**
 * Create / edit a login with one or more roles (roles come from the database).
 * platform: the super admin's version (all roles, super admin switch, any company).
 * fixedCompanyId: a company boss adding staff to their own company.
 */
export function UserFormModal({ account, companies = [], platform = false, fixedCompanyId, onClose, onSaved }) {
  const editing = Boolean(account)
  const roles = useApi('/roles/')
  const isEmployee = Boolean(account?.employee_id)

  const form = useForm({
    first_name: account?.first_name ?? '',
    last_name: account?.last_name ?? '',
    username: account?.username ?? '',
    email: account?.email ?? '',
    roles: (account?.roles ?? []).filter((code) => code !== 'EMPLOYEE'),
    company: account?.company ? String(account.company) : fixedCompanyId ? String(fixedCompanyId) : '',
    is_superuser: account?.is_superuser ?? false,
    ...(editing ? {} : { password: '', password_confirm: '' }),
  })
  const { values, errors, handleChange, setValues } = form
  const [addingRole, setAddingRole] = useState(false)

  // Only roles that can be ticked here: never Employee (it comes from onboarding)
  const roleOptions = (roles.data ?? [])
    .filter((role) => role.code !== 'EMPLOYEE')
    .filter((role) => platform || role.is_company_role)
  const needsCompany = roleOptions.some((role) => role.is_company_role && values.roles.includes(role.code))

  const save = form.submit(async (formValues) => {
    const payload = { ...formValues, company: needsCompany && formValues.company ? Number(formValues.company) : null }
    if (!platform) delete payload.is_superuser
    if (isEmployee) payload.roles = [...payload.roles, 'EMPLOYEE']
    const { data } = editing ? await api.patch(`/users/${account.id}/`, payload) : await api.post('/users/', payload)
    onSaved(data)
  })

  return (
    <Modal
      wide
      title={editing ? `Edit ${account.username}` : platform ? 'Add user' : 'Add staff member'}
      subtitle={
        editing
          ? null
          : platform
            ? 'Tick one or more roles. Roles and their permissions are managed under Users & roles → Roles.'
            : 'Switch on the roles this person needs: each role opens a page of the company dashboard.'
      }
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label={editing ? 'Save changes' : 'Create login'} formId="user-form" />}
    >
      <form id="user-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <div className="form-grid">
          <Field label="First name" name="first_name" value={values.first_name} onChange={handleChange} error={errors.first_name} required />
          <Field label="Last name" name="last_name" value={values.last_name} onChange={handleChange} error={errors.last_name} required={!account || Boolean(account.last_name)} />
          <Field label="Username" name="username" value={values.username} onChange={handleChange} error={errors.username} autoComplete="off" required />
          <Field label="Email" name="email" type="email" value={values.email} onChange={handleChange} error={errors.email} required />
        </div>

        {roles.loading ? (
          <Loading text="Loading roles…" />
        ) : !platform ? (
          <RoleSwitches
            options={sortPageRoles(roleOptions.filter((role) => role.code !== 'COMPANY_BOSS'))}
            value={values.roles}
            onChange={(selected) => setValues((prev) => ({ ...prev, roles: selected }))}
            onAddRole={() => setAddingRole(true)}
            error={errors.roles}
          />
        ) : (
          <CheckboxGroup
            label="Roles"
            options={roleOptions.map((role) => ({
              value: role.code,
              label: role.is_company_role ? `${role.name} (company)` : role.name,
              description: role.description,
            }))}
            value={values.roles}
            onChange={(selected) => setValues((prev) => ({ ...prev, roles: selected }))}
            error={errors.roles}
            hint={isEmployee ? 'This person is also an EUCL employee; that stays.' : null}
          />
        )}

        {needsCompany && !fixedCompanyId && (
          <SelectField label="Works for company" name="company" value={values.company} onChange={handleChange} error={errors.company} required>
            <option value="">Choose company…</option>
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
          </SelectField>
        )}

        {platform && (
          <label className="checkbox-card">
            <input type="checkbox" name="is_superuser" checked={values.is_superuser} onChange={handleChange} aria-label="Super admin" />
            <span>
              <span className="checkbox-title">Super admin</span>
              <span className="checkbox-description">Every permission on the whole platform. Give this to very few people.</span>
            </span>
          </label>
        )}

        {!editing && (
          <div className="form-grid section-gap">
            <Field label="Password" name="password" type="password" value={values.password} onChange={handleChange} error={errors.password} autoComplete="new-password" required />
            <Field label="Confirm password" name="password_confirm" type="password" value={values.password_confirm} onChange={handleChange} error={errors.password_confirm} autoComplete="new-password" required />
          </div>
        )}
      </form>

      {addingRole && (
        <RoleFormModal
          forCompany
          onClose={() => setAddingRole(false)}
          onSaved={(role) => {
            setAddingRole(false)
            roles.reload()
            // The new role is switched on for this person straight away
            setValues((prev) => ({ ...prev, roles: [...prev.roles, role.code] }))
          }}
        />
      )}
    </Modal>
  )
}

// The company pages in the order of the menu; any other company role comes after
const PAGE_ROLE_ORDER = ['COMPANY_DASHBOARD', 'COMPANY_RECORD_VISITS', 'COMPANY_SERVICES', 'COMPANY_EMPLOYEES_ATTENDED', 'COMPANY_ATTENDANCE']

function sortPageRoles(roles) {
  const rank = (role) => {
    const index = PAGE_ROLE_ORDER.indexOf(role.code)
    return index === -1 ? PAGE_ROLE_ORDER.length : index
  }
  return [...roles].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name))
}

// "All" plus one on/off switch per role. Roles not in `options` (e.g. the
// boss's own role when they edit themselves) are kept as they are.
function RoleSwitches({ options, value, onChange, onAddRole, error }) {
  const codes = options.map((role) => role.code)
  const allOn = codes.length > 0 && codes.every((code) => value.includes(code))
  const others = value.filter((code) => !codes.includes(code))

  const toggle = (code) => onChange(value.includes(code) ? value.filter((c) => c !== code) : [...value, code])
  const toggleAll = () => onChange(allOn ? others : [...others, ...codes])

  return (
    <fieldset className="role-switches">
      <legend className="field-label">Roles</legend>
      <div className="switch-list">
        <label className="switch-row switch-row-all">
          <span className="switch-text">
            <span className="checkbox-title">All</span>
            <span className="checkbox-description">Every page below</span>
          </span>
          <input type="checkbox" role="switch" className="switch" checked={allOn} onChange={toggleAll} aria-label="All roles" />
        </label>
        {options.map((role) => (
          <label key={role.code} className="switch-row">
            <span className="switch-text">
              <span className="checkbox-title">{role.name}</span>
              {role.description && <span className="checkbox-description">{role.description}</span>}
            </span>
            <input type="checkbox" role="switch" className="switch" checked={value.includes(role.code)} onChange={() => toggle(role.code)} aria-label={role.name} />
          </label>
        ))}
      </div>
      {error && <span className="field-error">{error}</span>}
      <button type="button" className="btn btn-ghost btn-sm section-gap" onClick={onAddRole}>
        <Icon name="plus" size={14} /> Add role
      </button>
    </fieldset>
  )
}

export function PasswordModal({ account, onClose, onSaved }) {
  const form = useForm({ password: '', password_confirm: '' })
  const { values, errors, handleChange } = form
  const save = form.submit(async (formValues) => {
    const { data } = await api.post(`/users/${account.id}/set-password/`, formValues)
    onSaved(data)
  })

  return (
    <Modal
      title={`Reset password for ${account.username}`}
      subtitle="Tell the user their new password in person; they can change it under My account."
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label="Set password" formId="password-form" />}
    >
      <form id="password-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <Field label="New password" name="password" type="password" value={values.password} onChange={handleChange} error={errors.password} autoComplete="new-password" required />
        <Field label="Confirm new password" name="password_confirm" type="password" value={values.password_confirm} onChange={handleChange} error={errors.password_confirm} autoComplete="new-password" required />
      </form>
    </Modal>
  )
}

// ------------------------------------------------------------------ role

// forCompany: a company boss adds a role for their own company (company
// pages only); the server limits the permissions they can choose.
export function RoleFormModal({ role, forCompany = false, onClose, onSaved }) {
  const editing = Boolean(role)
  const permissions = useApi('/permissions/')
  const form = useForm({
    name: role?.name ?? '',
    description: role?.description ?? '',
    is_company_role: role?.is_company_role ?? forCompany,
    permissions: role?.permissions ?? [],
  })
  const { values, errors, handleChange, setValues } = form

  const save = form.submit(async (formValues) => {
    const { data } = editing ? await api.patch(`/roles/${role.id}/`, formValues) : await api.post('/roles/', formValues)
    onSaved(data)
  })

  const byArea = PERMISSION_AREAS.map((area) => ({
    area,
    items: (permissions.data ?? []).filter((permission) => permission.area === area),
  })).filter((group) => group.items.length)

  return (
    <Modal
      wide
      title={editing ? `Edit role: ${role.name}` : 'New role'}
      subtitle={
        forCompany
          ? 'A role for your company’s staff: choose the pages it opens. Only your company sees it.'
          : 'A role is a named set of permissions. Everyone with the role gets all of them.'
      }
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label={editing ? 'Save role' : 'Create role'} formId="role-form" />}
    >
      <form id="role-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <div className="form-grid">
          <Field label="Role name" name="name" value={values.name} onChange={handleChange} error={errors.name} placeholder={forCompany ? 'e.g. Cashier' : 'e.g. Finance officer'} required />
          <Field label="Description" name="description" value={values.description} onChange={handleChange} error={errors.description} placeholder="What this person does" />
        </div>

        {!forCompany && role?.code !== 'EMPLOYEE' && (
          <label className="checkbox-card">
            <input type="checkbox" name="is_company_role" checked={values.is_company_role} onChange={handleChange} aria-label="Company role" />
            <span>
              <span className="checkbox-title">Company role</span>
              <span className="checkbox-description">People with this role work for one service provider (like a boss or receptionist).</span>
            </span>
          </label>
        )}

        <h3 className="form-section section-gap">{forCompany ? 'Pages this role opens' : 'Permissions'}</h3>
        {errors.permissions && <span className="field-error">{errors.permissions}</span>}
        {permissions.loading ? (
          <Loading text="Loading permissions…" />
        ) : (
          byArea.map((group) => (
            <CheckboxGroup
              key={group.area}
              label={forCompany ? null : group.area}
              options={group.items.map((permission) => ({ value: permission.code, label: permission.name, description: permission.description }))}
              value={values.permissions}
              onChange={(selected) => setValues((prev) => ({ ...prev, permissions: selected }))}
            />
          ))
        )}
      </form>
    </Modal>
  )
}

// --------------------------------------------------------------- company

const EMPTY_ACCOUNT = {
  account_username: '',
  account_email: '',
  account_password: '',
  account_password_confirm: '',
}

// onSaved(company, note): note says which login was created
export function CompanyFormModal({ company, onClose, onSaved }) {
  const editing = Boolean(company)
  const form = useForm({
    name: company?.name ?? '',
    email: company?.email ?? '',
    phone: company?.phone ?? '',
    address: company?.address ?? '',
    description: company?.description ?? '',
    // New company only: its login (the company boss) for its own dashboard
    ...(editing ? {} : EMPTY_ACCOUNT),
  })
  const { values, errors, handleChange } = form

  const save = form.submit(async (formValues) => {
    if (editing) {
      const { data } = await api.patch(`/companies/${company.id}/`, formValues)
      onSaved(data)
      return
    }

    // The company together with its login; the company then lists its own services
    const { data } = await api.post('/companies/', formValues)
    onSaved(data, `Login "${formValues.account_username}" created. The company can now sign in and list the services it offers.`)
  })

  return (
    <Modal
      wide
      title={editing ? `Edit ${company.name}` : 'Add company'}
      subtitle="A place where EUCL employees can use wellness services."
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label={editing ? 'Save changes' : 'Add company'} formId="company-form" />}
    >
      <form id="company-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <Field label="Company name" name="name" value={values.name} onChange={handleChange} error={errors.name} required />
        <div className="form-grid">
          <Field label="Email" name="email" type="email" value={values.email} onChange={handleChange} error={errors.email} required />
          <Field label="Phone" name="phone" type="tel" value={values.phone} onChange={handleChange} error={errors.phone} placeholder="+250 788 123 456" required />
        </div>
        <Field label="Address" name="address" value={values.address} onChange={handleChange} error={errors.address} required />
        <TextAreaField
          label="About (shown to EUCL employees)"
          name="description"
          value={values.description}
          onChange={handleChange}
          error={errors.description}
          placeholder="e.g. Open every day 6:00–21:00, parking available"
        />

        {!editing && (
          <>
            <h3 className="form-section section-gap">Company login</h3>
            <p className="field-hint">
              The company signs in with this login (shown as {values.name.trim() || 'the company’s name'}). It opens the company dashboard, lists
              the services it offers, records EUCL visits and adds receptionists.
            </p>
            <div className="form-grid">
              <Field
                label="Username"
                name="account_username"
                value={values.account_username}
                onChange={handleChange}
                error={errors.account_username}
                placeholder="e.g. goldgym"
                autoComplete="off"
                required
              />
              <Field label="Login email" name="account_email" type="email" value={values.account_email} onChange={handleChange} error={errors.account_email} required />
            </div>
            <div className="form-grid">
              <Field
                label="Password"
                name="account_password"
                type="password"
                value={values.account_password}
                onChange={handleChange}
                error={errors.account_password}
                hint="At least 8 characters, not only numbers."
                autoComplete="new-password"
                required
              />
              <Field
                label="Confirm password"
                name="account_password_confirm"
                type="password"
                value={values.account_password_confirm}
                onChange={handleChange}
                error={errors.account_password_confirm}
                autoComplete="new-password"
                required
              />
            </div>

          </>
        )}
      </form>
    </Modal>
  )
}

// --------------------------------------------------------------- service

// companyId: the company that offers the service (the server uses the
// boss's own company anyway; the super admin needs to say which one)
export function ServiceFormModal({ service, companyId, onClose, onSaved }) {
  const editing = Boolean(service)
  const form = useForm({
    name: service?.name ?? '',
    price: service ? String(Number(service.price)) : '',
    description: service?.description ?? '',
  })
  const { values, errors, handleChange } = form

  const save = form.submit(async (formValues) => {
    const { data } = editing
      ? await api.patch(`/services/${service.id}/`, formValues)
      : await api.post('/services/', { ...formValues, company: Number(companyId) })
    onSaved(data, !editing)
  })

  return (
    <Modal
      title={editing ? `Edit ${service.name}` : 'Add a service'}
      subtitle="The company’s own price. EUCL sets the amount it pays when it covers the service."
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label={editing ? 'Save' : 'Add service'} formId="service-form" />}
    >
      <form id="service-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <div className="form-grid">
          <Field label="Service name" name="name" value={values.name} onChange={handleChange} error={errors.name} placeholder="e.g. Yoga class" maxLength={100} required />
          <Field label="Company price per visit (RWF)" name="price" type="number" min="0" step="1" value={values.price} onChange={handleChange} error={errors.price} required />
        </div>
        <TextAreaField label="Description" name="description" value={values.description} onChange={handleChange} error={errors.description} placeholder="e.g. 60 minutes, towels provided" />
      </form>
    </Modal>
  )
}

// --------------------------------------------------------------- payment

export function PaymentFormModal({ companies, defaultCompanyId, onClose, onSaved }) {
  const form = useForm({
    company: defaultCompanyId ? String(defaultCompanyId) : '',
    period_start: monthStartISO(),
    period_end: todayISO(),
    reference: '',
    note: '',
  })
  const { values, errors, handleChange } = form

  // Live preview of what will be marked as paid
  const preview = useApi(values.company ? '/payments/balances/' : null, {
    company: values.company,
    date_from: values.period_start,
    date_to: values.period_end,
  })
  const owed = preview.data?.[0]

  const save = form.submit(async (formValues) => {
    const { data } = await api.post('/payments/', { ...formValues, company: Number(formValues.company) })
    onSaved(data)
  })

  return (
    <Modal
      title="Mark as paid"
      subtitle="Every unpaid visit of the company in this period is marked as paid by this payment."
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label="Mark as paid" formId="payment-form" disabled={!owed || Number(owed.unpaid) === 0} />}
    >
      <form id="payment-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <SelectField label="Company" name="company" value={values.company} onChange={handleChange} error={errors.company} required>
          <option value="">Choose company…</option>
          {companies.map((company) => (
            <option key={company.id} value={company.id}>
              {company.name}
            </option>
          ))}
        </SelectField>
        <div className="form-grid">
          <Field label="From" name="period_start" type="date" value={values.period_start} onChange={handleChange} error={errors.period_start} required />
          <Field label="To" name="period_end" type="date" value={values.period_end} min={values.period_start} onChange={handleChange} error={errors.period_end} required />
        </div>
        <div className="form-grid">
          <Field label="Reference" name="reference" value={values.reference} onChange={handleChange} error={errors.reference} placeholder="e.g. bank transfer no." />
          <Field label="Note" name="note" value={values.note} onChange={handleChange} error={errors.note} />
        </div>

        {values.company && (
          <div className="payment-preview">
            {preview.loading ? (
              'Calculating…'
            ) : owed && Number(owed.unpaid) > 0 ? (
              <>
                <span>
                  {owed.unpaid_visits} unpaid visit{owed.unpaid_visits === 1 ? '' : 's'}
                </span>
                <strong>{formatMoney(owed.unpaid)}</strong>
              </>
            ) : (
              <span>Nothing unpaid for this company in this period.</span>
            )}
          </div>
        )}
      </form>
    </Modal>
  )
}
