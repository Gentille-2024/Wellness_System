import { useState } from 'react'
import api from '../api/client'
import { groupByArea, sortRoles } from '../auth/access'
import { FEEDBACK_KINDS } from '../utils/feedback'
import Icon from './Icon'
import useApi from '../hooks/useApi'
import useForm from '../hooks/useForm'
import { formatDate, formatMoney, monthStartISO, todayISO } from '../utils/format'
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
          employee_id: employee.employee_id,
          first_name: employee.first_name,
          last_name: employee.last_name,
          email: employee.email,
          phone: employee.phone,
          department: employee.department,
          position: employee.position,
        }
      : {
          employee_id: '',
          first_name: '',
          last_name: '',
          email: '',
          phone: '',
          department: '',
          position: '',
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
      subtitle={
        editing
          ? employee.employee_id
          : 'All fields are required. The username is the last name; the employee creates their password at first sign-in with their Employee ID and their email or phone.'
      }
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label={editing ? 'Save changes' : 'Onboard employee'} formId="employee-form" />}
    >
      <form id="employee-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <h3 className="form-section">Personal details</h3>
        <div className="form-grid">
          <Field label="Employee ID" name="employee_id" value={values.employee_id} onChange={handleChange} error={errors.employee_id} placeholder="e.g. EMP0101" hint="Given by HR. Must be unique." required />
          <span />
          <Field label="Last name" name="last_name" value={values.last_name} onChange={handleChange} error={errors.last_name} placeholder="Family name, e.g. NATUKUNDA" required />
          <Field label="First name" name="first_name" value={values.first_name} onChange={handleChange} error={errors.first_name} required />
          <Field label="Email" name="email" type="email" value={values.email} onChange={handleChange} error={errors.email} placeholder="name@example.com" required />
          <Field label="Phone" name="phone" type="tel" value={values.phone} onChange={handleChange} error={errors.phone} placeholder="+250 788 123 456" required />
        </div>
        <h3 className="form-section">Job at EUCL</h3>
        <div className="form-grid">
          <Field label="Department" name="department" value={values.department} onChange={handleChange} error={errors.department} hint="Employees in HR get the HR role." required />
          <Field label="Position" name="position" value={values.position} onChange={handleChange} error={errors.position} required />
        </div>
      </form>
    </Modal>
  )
}

// ------------------------------------------------------------------ user

/**
 * Create / edit a login. Every login has exactly ONE role (roles come from the
 * database), because each role has its own permissions.
 * platform: the super admin's version (all roles, any company).
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
    roles: (account?.roles ?? []).slice(0, 1),
    company: account?.company ? String(account.company) : fixedCompanyId ? String(fixedCompanyId) : '',
    ...(editing ? {} : { password: '', password_confirm: '' }),
  })
  const { values, errors, handleChange, setValues } = form
  const [addingRole, setAddingRole] = useState(false)
  const chooseRole = (selected) => setValues((prev) => ({ ...prev, roles: selected.slice(-1) }))

  const allRoles = roles.data ?? []
  // A company boss chooses among the company roles (Boss only for someone who already has it)
  const roleOptions = platform
    ? allRoles
    : allRoles.filter((role) => role.is_company_role && (role.code !== 'COMPANY_BOSS' || values.roles.includes('COMPANY_BOSS')))
  const needsCompany = allRoles.some((role) => role.is_company_role && values.roles.includes(role.code))

  const save = form.submit(async (formValues) => {
    const payload = { ...formValues, company: needsCompany && formValues.company ? Number(formValues.company) : null }
    delete payload.is_superuser // the Super admin role decides it
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
            ? 'Choose one role. Roles and their permissions are managed under Users & roles → Roles.'
            : 'Choose the role this person has: it decides which pages of the company dashboard they open.'
      }
      onClose={onClose}
      footer={
        <FormFooter onClose={onClose} submitting={form.submitting} label={editing ? 'Save changes' : 'Create login'} formId="user-form" disabled={values.roles.length !== 1} />
      }
    >
      <form id="user-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <div className="form-grid">
          <Field label="Last name" name="last_name" value={values.last_name} onChange={handleChange} error={errors.last_name} required={!account || Boolean(account.last_name)} />
          <Field label="First name" name="first_name" value={values.first_name} onChange={handleChange} error={errors.first_name} required />
          <Field label="Username" name="username" value={values.username} onChange={handleChange} error={errors.username} autoComplete="off" required />
          <Field label="Email" name="email" type="email" value={values.email} onChange={handleChange} error={errors.email} required />
        </div>

        {roles.loading ? (
          <Loading text="Loading roles…" />
        ) : (
          <>
            <CheckboxGroup
              single
              name="role"
              label="Role"
              options={sortRoles(roleOptions).map((role) => {
                // The Employee role is only for people HR added as EUCL employees
                const employeeOnly = role.code === 'EMPLOYEE' && !isEmployee
                return {
                  value: role.code,
                  label: role.name,
                  description: employeeOnly ? 'Only for EUCL employees: add them on the EUCL employees page.' : role.description,
                  disabled: employeeOnly,
                }
              })}
              value={values.roles}
              onChange={chooseRole}
              error={errors.roles}
              hint={
                isEmployee
                  ? 'One role per person. This person is an EUCL employee: that record stays whatever role you choose.'
                  : 'One role per person: each role has its own permissions.'
              }
            />
            {!platform && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAddingRole(true)}>
                <Icon name="plus" size={14} /> Add role
              </button>
            )}
          </>
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
            // The new role becomes this person's role straight away
            setValues((prev) => ({ ...prev, roles: [role.code] }))
          }}
        />
      )}
    </Modal>
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
export function RoleFormModal({ role, forCompany = false, withPermissions = true, onClose, onSaved }) {
  const editing = Boolean(role)
  const permissions = useApi('/permissions/')
  const form = useForm({
    name: role?.name ?? '',
    description: role?.description ?? '',
    permissions: role?.permissions ?? [],
    is_company_role: role ? role.is_company_role : forCompany,
  })
  // EUCL chooses who a new role is for; built-in roles keep theirs
  const chooseKind = !forCompany && !role?.is_system && !role?.company
  const { values, errors, handleChange, setValues } = form

  const save = form.submit(async (formValues) => {
    const payload = { ...formValues }
    if (!withPermissions && editing) delete payload.permissions // switched on the Roles page
    if (!chooseKind) delete payload.is_company_role
    const { data } = editing ? await api.patch(`/roles/${role.id}/`, payload) : await api.post('/roles/', payload)
    onSaved(data)
  })

  const byArea = groupByArea(permissions.data ?? [])

  return (
    <Modal
      wide
      title={editing ? `Edit role: ${role.name}` : 'New role'}
      subtitle={
        forCompany
          ? 'A role for your company’s staff: choose the pages it opens. Only your company sees it.'
          : withPermissions
            ? 'A role is a named set of permissions. Everyone with the role gets all of them.'
            : 'Name the role and choose who gets it, then switch on its permissions.'
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

        {chooseKind && (
          <CheckboxGroup
            single
            name="role-kind"
            label="Who gets this role?"
            options={[
              { value: 'eucl', label: 'EUCL staff', description: 'People not linked to a company (like HR or M&E officer): EUCL pages, My wellness, M&E.' },
              { value: 'company', label: 'Company staff', description: 'Staff of a service provider: the My company pages (and EUCL pages if you switch them on).' },
            ]}
            value={[values.is_company_role ? 'company' : 'eucl']}
            onChange={([kind]) => setValues((prev) => ({ ...prev, is_company_role: kind === 'company' }))}
            error={errors.is_company_role}
            hint={editing ? 'Can only change while nobody has this role.' : null}
          />
        )}


        {withPermissions && (
          <>
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
          </>
        )}
      </form>
    </Modal>
  )
}

// -------------------------------------------------------------- feedback


// An employee's feedback on one service they used (optional)
export function FeedbackModal({ visit, onClose, onSaved }) {
  const form = useForm({ kind: visit.feedback_kind || 'comment', message: visit.feedback_message || '' })
  const { values, errors, handleChange, setValues } = form
  const [removing, setRemoving] = useState(false)

  const save = form.submit(async (formValues) => {
    const { data } = await api.post(`/visits/${visit.id}/feedback/`, formValues)
    onSaved(data, 'sent')
  })

  const remove = async () => {
    setRemoving(true)
    try {
      const { data } = await api.delete(`/visits/${visit.id}/feedback/`)
      onSaved(data, 'removed')
    } finally {
      setRemoving(false)
    }
  }

  return (
    <Modal
      title="Feedback on this service"
      subtitle={`${visit.service_name} at ${visit.company_name}, ${formatDate(visit.visit_date)}. HR, EUCL and the company will see it.`}
      onClose={onClose}
      footer={
        <>
          {visit.feedback_kind && (
            <button type="button" className="btn btn-ghost text-danger" onClick={remove} disabled={removing} style={{ marginRight: 'auto' }}>
              {removing ? 'Removing…' : 'Remove my feedback'}
            </button>
          )}
          <FormFooter onClose={onClose} submitting={form.submitting} label="Send feedback" formId="feedback-form" />
        </>
      }
    >
      <form id="feedback-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <div className="field">
          <span className="field-label">Type</span>
          <div className="choice-list">
            {FEEDBACK_KINDS.map((kind) => (
              <label key={kind.value} className={values.kind === kind.value ? 'choice active' : 'choice'}>
                <input type="radio" name="kind" value={kind.value} checked={values.kind === kind.value} onChange={() => setValues((prev) => ({ ...prev, kind: kind.value }))} />
                <span>
                  <span className="checkbox-title">{kind.label}</span>
                  <span className="checkbox-description">{kind.description}</span>
                </span>
              </label>
            ))}
          </div>
          {errors.kind && <span className="field-error">{errors.kind}</span>}
        </div>
        <TextAreaField
          label="Message"
          name="message"
          value={values.message}
          onChange={handleChange}
          error={errors.message}
          rows={4}
          maxLength={1000}
          placeholder={values.kind === 'complaint' ? 'What went wrong? e.g. I did not attend: I was at work that day' : 'Your comment'}
          required
        />
      </form>
    </Modal>
  )
}

// ------------------------------------------------------------ permission

// The super admin adds a permission; it can then be switched on for roles
export function PermissionFormModal({ areas, onClose, onSaved }) {
  const form = useForm({ name: '', description: '', area: areas[0] ?? 'EUCL' })
  const { values, errors, handleChange } = form
  const save = form.submit(async (formValues) => {
    const { data } = await api.post('/permissions/', formValues)
    onSaved(data)
  })

  return (
    <Modal
      title="New permission"
      subtitle="Switch it on for the roles that should have it. A new permission is a label until a page of the system is made to check it."
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label="Add permission" formId="permission-form" />}
    >
      <form id="permission-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <Field label="Name" name="name" value={values.name} onChange={handleChange} error={errors.name} placeholder="e.g. Approve refunds" required />
        <Field label="Description" name="description" value={values.description} onChange={handleChange} error={errors.description} placeholder="What it allows" />
        <SelectField label="Group" name="area" value={values.area} onChange={handleChange} error={errors.area}>
          {areas.map((area) => (
            <option key={area} value={area}>
              {area}
            </option>
          ))}
          {!areas.includes('Custom') && <option value="Custom">Custom</option>}
        </SelectField>
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
              the services it offers, records the services EUCL employees use and adds receptionists.
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
// priceOnly: staff who may only change the price (e.g. a receptionist)
export function ServiceFormModal({ service, companyId, priceOnly = false, onClose, onSaved }) {
  const editing = Boolean(service)
  const form = useForm({
    name: service?.name ?? '',
    price: service ? String(Number(service.price)) : '',
    description: service?.description ?? '',
  })
  const { values, errors, handleChange } = form

  const save = form.submit(async (formValues) => {
    const { data } = editing
      ? await api.patch(`/services/${service.id}/`, priceOnly ? { price: formValues.price } : formValues)
      : await api.post('/services/', { ...formValues, company: Number(companyId) })
    onSaved(data, !editing)
  })

  return (
    <Modal
      title={editing ? (priceOnly ? `Change the price of ${service.name}` : `Edit ${service.name}`) : 'Add a service'}
      subtitle={
        priceOnly
          ? 'EUCL pays this price when it covers the service. The change is recorded with your name.'
          : 'The company’s own price. EUCL pays this price when it covers the service.'
      }
      onClose={onClose}
      footer={<FormFooter onClose={onClose} submitting={form.submitting} label={editing ? 'Save' : 'Add service'} formId="service-form" />}
    >
      <form id="service-form" onSubmit={save}>
        <Alert>{errors._general}</Alert>
        <div className="form-grid">
          <Field label="Service name" name="name" value={values.name} onChange={handleChange} error={errors.name} placeholder="e.g. Yoga class" maxLength={100} required disabled={priceOnly} />
          <Field label="Price (RWF)" name="price" type="number" min="0" step="1" value={values.price} onChange={handleChange} error={errors.price} required autoFocus={priceOnly} />
        </div>
        {!priceOnly && (
          <TextAreaField label="Description" name="description" value={values.description} onChange={handleChange} error={errors.description} placeholder="e.g. 60 minutes, towels provided" />
        )}
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
      subtitle="Every unpaid service used at the company in this period is marked as paid by this payment."
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
