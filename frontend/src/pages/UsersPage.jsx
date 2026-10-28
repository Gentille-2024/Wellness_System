import { useState } from 'react'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { PasswordModal, RoleFormModal, UserFormModal } from '../components/forms'
import Icon from '../components/Icon'
import { Alert, Avatar, Badge, Card, ConfirmDialog, EmptyState, FilterButton, Loading, PageHeader, SearchInput, Segmented, SelectField } from '../components/ui'
import useApi from '../hooks/useApi'
import useDebounced from '../hooks/useDebounced'
import { formatDateTime } from '../utils/format'

const TABS = [
  { value: 'users', label: 'Users' },
  { value: 'roles', label: 'Roles & permissions' },
]

const STATUS_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'blocked', label: 'Blocked' },
]

const KIND_OPTIONS = [
  { value: '', label: 'Everyone' },
  { value: 'staff', label: 'Staff' },
  { value: 'employees', label: 'EUCL employees' },
]

const EMPTY_FILTERS = { role: '', company: '', status: '', kind: '' }

/**
 * scope="platform": every login + roles & permissions (manage_users)
 * scope="company":  a company boss's own staff (manage_company_staff)
 */
export default function UsersPage({ scope }) {
  const { user } = useAuth()
  const platform = scope === 'platform'
  const [tab, setTab] = useState('users')

  return (
    <>
      <PageHeader
        title={platform ? 'Users & roles' : 'Staff'}
        subtitle={
          platform
            ? 'Logins, the roles they have, and what each role is allowed to do.'
            : `Logins for the people who work at ${user.company?.name}.`
        }
      />
      {platform && (
        <div className="page-tabs">
          <Segmented options={TABS} value={tab} onChange={setTab} />
        </div>
      )}
      {tab === 'users' ? <UsersTab platform={platform} /> : <RolesTab />}
    </>
  )
}

// ------------------------------------------------------------------- users

function UsersTab({ platform }) {
  const { user: me } = useAuth()
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const debouncedSearch = useDebounced(search)

  const users = useApi('/users/', { search: debouncedSearch, ...filters, ...(platform ? {} : { company: me.company?.id }) })
  const roles = useApi('/roles/')
  const companies = useApi(platform ? '/companies/' : null, { status: 'current' })

  const [editing, setEditing] = useState(null) // null = closed, {} = new, account = edit
  const [resetting, setResetting] = useState(null)
  const [toggling, setToggling] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')

  const setFilter = (name, value) => setFilters((prev) => ({ ...prev, [name]: value }))
  const activeCount = Object.values(filters).filter(Boolean).length

  const toggleActive = async () => {
    setBusy(true)
    setActionError('')
    try {
      await api.patch(`/users/${toggling.id}/`, { is_active: !toggling.is_active })
      setNotice(`${toggling.username} ${toggling.is_active ? 'can no longer log in' : 'can log in again'}.`)
      setToggling(null)
      users.reload()
    } catch (err) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Alert type="success">{notice}</Alert>

      <Card flush>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="Search name, username or email…" />
          <FilterButton activeCount={activeCount} onClear={() => setFilters(EMPTY_FILTERS)}>
            <SelectField label="Role" value={filters.role} onChange={(event) => setFilter('role', event.target.value)}>
              <option value="">Any role</option>
              {platform && <option value="SUPERUSER">Super admin</option>}
              {(roles.data ?? []).map((role) => (
                <option key={role.code} value={role.code}>
                  {role.name}
                </option>
              ))}
            </SelectField>
            {platform && (
              <SelectField label="Company" value={filters.company} onChange={(event) => setFilter('company', event.target.value)}>
                <option value="">Any company</option>
                {(companies.data ?? []).map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.name}
                  </option>
                ))}
              </SelectField>
            )}
            {platform && (
              <div className="field">
                <span className="field-label">Kind</span>
                <Segmented options={KIND_OPTIONS} value={filters.kind} onChange={(value) => setFilter('kind', value)} />
              </div>
            )}
            <div className="field">
              <span className="field-label">Status</span>
              <Segmented options={STATUS_OPTIONS} value={filters.status} onChange={(value) => setFilter('status', value)} />
            </div>
          </FilterButton>
          <button type="button" className="btn btn-primary" onClick={() => setEditing({})}>
            <Icon name="plus" size={16} /> {platform ? 'Add user' : 'Add staff member'}
          </button>
        </div>

        {users.error && <Alert>{users.error}</Alert>}
        {users.loading ? (
          <Loading />
        ) : users.data?.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Roles</th>
                  {platform && <th>Company</th>}
                  <th>Last login</th>
                  <th>Status</th>
                  <th className="actions-col" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {users.data.map((account) => {
                  const name = `${account.first_name} ${account.last_name}`.trim() || account.username
                  const isMe = account.id === me.id
                  return (
                    <tr key={account.id} className={account.is_active ? '' : 'row-muted'}>
                      <td>
                        <div className="cell-person">
                          <Avatar name={name} size={32} />
                          <div>
                            <div className="cell-main">
                              {name} {isMe && <span className="muted">(you)</span>}
                            </div>
                            <div className="cell-sub">
                              @{account.username}
                              {account.email && ` · ${account.email}`}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div className="badge-row">
                          {account.role_names.length ? (
                            account.role_names.map((role) => (
                              <Badge key={role} tone={role === 'Super admin' ? 'info' : 'primary'}>
                                {role}
                              </Badge>
                            ))
                          ) : (
                            <Badge>No role</Badge>
                          )}
                        </div>
                        {account.employee_id && <div className="cell-sub">{account.employee_id}</div>}
                      </td>
                      {platform && <td>{account.company_name ?? <span className="muted">EUCL</span>}</td>}
                      <td className="nowrap">{account.last_login ? formatDateTime(account.last_login) : 'Never'}</td>
                      <td>{account.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="warning">Blocked</Badge>}</td>
                      <td className="actions-col">
                        <div className="row-actions">
                          <button type="button" className="btn-icon" title="Edit" aria-label={`Edit ${account.username}`} onClick={() => setEditing(account)}>
                            <Icon name="edit" size={16} />
                          </button>
                          <button type="button" className="btn-icon" title="Reset password" aria-label={`Reset password for ${account.username}`} onClick={() => setResetting(account)}>
                            <Icon name="key" size={16} />
                          </button>
                          {!isMe && (
                            <button
                              type="button"
                              className={account.is_active ? 'btn-icon danger' : 'btn-icon'}
                              title={account.is_active ? 'Block login' : 'Unblock login'}
                              aria-label={account.is_active ? `Block ${account.username}` : `Unblock ${account.username}`}
                              onClick={() => setToggling(account)}
                            >
                              <Icon name={account.is_active ? 'lock' : 'unlock'} size={16} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="shield" title="No users found">
            {activeCount || search ? 'Try different filters.' : null}
          </EmptyState>
        )}
      </Card>

      {editing && (
        <UserFormModal
          account={editing.id ? editing : null}
          platform={platform}
          companies={companies.data ?? []}
          fixedCompanyId={platform ? null : me.company?.id}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setNotice(`${saved.username} saved.`)
            setEditing(null)
            users.reload()
          }}
        />
      )}

      {resetting && (
        <PasswordModal
          account={resetting}
          onClose={() => setResetting(null)}
          onSaved={(result) => {
            setNotice(result.detail)
            setResetting(null)
          }}
        />
      )}

      {toggling && (
        <ConfirmDialog
          title={toggling.is_active ? `Block ${toggling.username}?` : `Unblock ${toggling.username}?`}
          confirmLabel={toggling.is_active ? 'Block login' : 'Unblock login'}
          danger={toggling.is_active}
          busy={busy}
          error={actionError}
          onConfirm={toggleActive}
          onCancel={() => {
            setToggling(null)
            setActionError('')
          }}
        >
          <p>{toggling.is_active ? 'This person will no longer be able to log in. Nothing they recorded is removed.' : 'This person will be able to log in again.'}</p>
        </ConfirmDialog>
      )}
    </>
  )
}

// ------------------------------------------------------------------- roles

function RolesTab() {
  const roles = useApi('/roles/')
  const permissions = useApi('/permissions/')
  const [editing, setEditing] = useState(null) // null = closed, {} = new, role = edit
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')

  const permissionName = (code) => permissions.data?.find((permission) => permission.code === code)?.name ?? code

  const remove = async () => {
    setBusy(true)
    setActionError('')
    try {
      await api.delete(`/roles/${deleting.id}/`)
      setNotice(`The ${deleting.name} role was deleted.`)
      setDeleting(null)
      roles.reload()
    } catch (err) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Alert type="success">{notice}</Alert>
      <Alert>{roles.error}</Alert>

      <div className="card-header-bar">
        <p className="muted">Create a role, tick what it may do, then give it to users on the Users tab. A user with several roles gets all their permissions.</p>
        <button type="button" className="btn btn-primary" onClick={() => setEditing({})}>
          <Icon name="plus" size={16} /> New role
        </button>
      </div>

      {roles.loading ? (
        <Loading />
      ) : (
        <div className="role-grid">
          {roles.data.map((role) => (
            <div key={role.id} className="role-card">
              <div className="role-card-head">
                <div>
                  <h3>{role.name}</h3>
                  <div className="cell-sub">
                    {role.company_name ? `${role.company_name} only` : role.is_company_role ? 'Company role' : 'EUCL role'} · {role.user_count} user{role.user_count === 1 ? '' : 's'}
                    {role.is_system && ' · built-in'}
                  </div>
                </div>
                <div className="row-actions">
                  <button type="button" className="btn-icon" title="Edit" aria-label={`Edit ${role.name}`} onClick={() => setEditing(role)}>
                    <Icon name="edit" size={16} />
                  </button>
                  {!role.is_system && (
                    <button type="button" className="btn-icon danger" title="Delete" aria-label={`Delete ${role.name}`} onClick={() => setDeleting(role)}>
                      <Icon name="trash" size={16} />
                    </button>
                  )}
                </div>
              </div>
              {role.description && <p className="muted">{role.description}</p>}
              <div className="badge-row">
                {role.permissions.map((code) => (
                  <Badge key={code} tone="neutral">
                    {permissionName(code)}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <RoleFormModal
          role={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setNotice(`The ${saved.name} role was saved.`)
            setEditing(null)
            roles.reload()
          }}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title={`Delete the ${deleting.name} role?`}
          confirmLabel="Delete role"
          danger
          busy={busy}
          error={actionError}
          onConfirm={remove}
          onCancel={() => {
            setDeleting(null)
            setActionError('')
          }}
        >
          <p>{deleting.user_count ? `${deleting.user_count} user(s) still have this role; remove it from them first.` : 'No one has this role, so nothing else changes.'}</p>
        </ConfirmDialog>
      )}
    </>
  )
}
