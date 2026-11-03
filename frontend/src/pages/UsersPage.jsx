import { useState } from 'react'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { PasswordModal, PermissionFormModal, RoleFormModal, UserFormModal } from '../components/forms'
import { groupByArea, sortRoles } from '../auth/access'
import Icon from '../components/Icon'
import { Alert, Avatar, Badge, Card, ConfirmDialog, EmptyState, FilterButton, Loading, Modal, PageHeader, SearchInput, Segmented, SelectField } from '../components/ui'
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
  // "Open role" from a user's permissions jumps to that role in the Roles tab
  const [openRoleId, setOpenRoleId] = useState(null)
  const openRole = (roleId) => {
    setOpenRoleId(roleId)
    setTab('roles')
  }

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
      {tab === 'users' ? <UsersTab platform={platform} onOpenRole={platform ? openRole : null} /> : <RolesTab initialRoleId={openRoleId} />}
    </>
  )
}

// ------------------------------------------------------------------- users

function UsersTab({ platform, onOpenRole }) {
  const { user: me } = useAuth()
  const [viewing, setViewing] = useState(null) // the login whose permissions are shown
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
                  const name = `${account.last_name} ${account.first_name}`.trim() || account.username
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
                          <button type="button" className="btn-icon" title="What they can do" aria-label={`What ${account.username} can do`} onClick={() => setViewing(account)}>
                            <Icon name="eye" size={16} />
                          </button>
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

      {viewing && <AccessModal account={viewing} onClose={() => setViewing(null)} onOpenRole={onOpenRole} />}

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

/**
 * Left: the roles. Right: every permission of the selected role, each with
 * an on/off switch that saves straight away.
 */
/**
 * Everything one login may do and the role(s) each permission comes from.
 * A permission stays as long as ANY of the person's roles has it switched on.
 */
function AccessModal({ account, onClose, onOpenRole }) {
  const access = useApi(`/users/${account.id}/access/`)
  const data = access.data
  const groups = groupByArea(data?.permissions ?? [])
  const name = account.full_name || account.username

  return (
    <Modal title={`What ${name} can do`} subtitle="Each permission and the role that gives it." onClose={onClose} wide>
      {access.error && <Alert>{access.error}</Alert>}
      {access.loading ? (
        <Loading />
      ) : data ? (
        <>
          <p className="role-note">
            A permission stays on while <strong>any</strong> of the person’s roles has it. To take one away, switch it off in every
            role named next to it, or remove that role from the person.
            {data.is_superuser && ' This login is a super admin: it also gets everything switched on for the Super admin role.'}
          </p>
          <div className="access-roles">
            {data.roles.length ? (
              data.roles.map((role) => (
                <span key={role.id} className="access-role">
                  <Badge tone={role.counts ? 'info' : 'warning'}>{role.name}</Badge>
                  {!role.counts && <span className="muted"> (paused: company deactivated)</span>}
                  {onOpenRole && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => onOpenRole(role.id)}>
                      Open role
                    </button>
                  )}
                </span>
              ))
            ) : (
              <span className="muted">No roles.</span>
            )}
          </div>
          {groups.length ? (
            groups.map((group) => (
              <section key={group.area} className="permission-group" aria-label={`${group.area} permissions`}>
                <div className="permission-group-head">
                  <h4>{group.area}</h4>
                  <span className="muted">{group.items.length} on</span>
                </div>
                <div className="switch-list">
                  {group.items.map((permission) => (
                    <div key={permission.code} className="switch-row">
                      <span className="switch-text">
                        <span className="checkbox-title">{permission.name}</span>
                        {permission.description && <span className="checkbox-description">{permission.description}</span>}
                      </span>
                      <span className="switch-side access-sources">
                        {permission.roles.map((roleName) => (
                          <Badge key={roleName}>{roleName}</Badge>
                        ))}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            ))
          ) : (
            <EmptyState icon="shield" title="No permissions">
              None of this person’s roles has a permission switched on.
            </EmptyState>
          )}
        </>
      ) : null}
    </Modal>
  )
}

function RolesTab({ initialRoleId = null }) {
  const { reloadUser } = useAuth()
  const roles = useApi('/roles/')
  const permissions = useApi('/permissions/')
  const [selectedId, setSelectedId] = useState(initialRoleId)
  const [editing, setEditing] = useState(null) // null = closed, {} = new role, role = edit name
  const [addingPermission, setAddingPermission] = useState(false)
  const [deleting, setDeleting] = useState(null) // { kind: 'role' | 'permission', item }
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState('') // permission code being saved
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  // Switching "Manage users & roles" off for super admins waits for a confirmation
  const [lockWarning, setLockWarning] = useState(null) // { wanted, changed }

  const list = sortRoles(roles.data ?? [])
  const role = list.find((item) => item.id === selectedId) ?? list[0]
  const groups = groupByArea(permissions.data ?? [])
  // Would this change take "Manage users & roles" away from super admins?
  const locksOutSuperAdmins = (wanted) =>
    role.code === 'SUPER_ADMIN' && role.permissions.includes('manage_users') && !wanted.includes('manage_users')

  const savePermissions = async (wanted, changed, confirmed = false) => {
    if (!confirmed && locksOutSuperAdmins(wanted)) {
      setLockWarning({ wanted, changed })
      return
    }
    setLockWarning(null)
    const codes = wanted
    setSaving(changed)
    setActionError('')
    setNotice('')
    const before = role.permissions
    roles.setData((prev) => prev.map((item) => (item.id === role.id ? { ...item, permissions: codes } : item)))
    try {
      await api.patch(`/roles/${role.id}/`, { permissions: codes })
      // Taking "Manage users & roles" away may change the signed-in user's own menu
      if (confirmed) reloadUser?.()
    } catch (err) {
      roles.setData((prev) => prev.map((item) => (item.id === role.id ? { ...item, permissions: before } : item)))
      setActionError(errorMessage(err))
    } finally {
      setSaving('')
    }
  }

  const toggle = (code) =>
    savePermissions(role.permissions.includes(code) ? role.permissions.filter((c) => c !== code) : [...role.permissions, code], code)

  const toggleGroup = (items, allOn) => {
    const codes = items.map((p) => p.code)
    const next = allOn ? role.permissions.filter((c) => !codes.includes(c)) : [...new Set([...role.permissions, ...codes])]
    savePermissions(next, codes[0])
  }

  const remove = async () => {
    setBusy(true)
    setActionError('')
    try {
      if (deleting.kind === 'role') {
        await api.delete(`/roles/${deleting.item.id}/`)
        setSelectedId(null)
        roles.reload()
      } else {
        await api.delete(`/permissions/${deleting.item.code}/`)
        permissions.reload()
        roles.reload()
      }
      setNotice(`${deleting.item.name} was deleted.`)
      setDeleting(null)
    } catch (err) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Alert type="success">{notice}</Alert>
      <Alert>{deleting ? '' : actionError || roles.error || permissions.error}</Alert>

      <div className="card-header-bar">
        <p className="muted">Choose a role to see every permission and switch them on or off. Each user has one role and gets its permissions.</p>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary" onClick={() => setAddingPermission(true)}>
            <Icon name="plus" size={16} /> New permission
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setEditing({})}>
            <Icon name="plus" size={16} /> New role
          </button>
        </div>
      </div>

      {roles.loading || permissions.loading ? (
        <Loading />
      ) : (
        <div className="roles-layout">
          <Card title="Roles" subtitle={`${list.length} roles`} flush>
            <ul className="role-list">
              {list.map((item) => (
                <li key={item.id}>
                  <button type="button" className={item.id === role?.id ? 'role-item active' : 'role-item'} onClick={() => setSelectedId(item.id)}>
                    <span className="role-item-text">
                      <span className="cell-main">{item.name}</span>
                      <span className="cell-sub">
                        {item.company_name ? `${item.company_name} only` : item.is_company_role ? 'Company role' : 'EUCL role'} · {item.user_count} user{item.user_count === 1 ? '' : 's'}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {role && (
            <Card
              title={role.name}
              subtitle={role.description || (role.is_system ? 'Built-in role' : 'Role added by EUCL')}
              flush
              actions={
                <div className="row-actions">
                  {role.code !== 'SUPER_ADMIN' && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing(role)}>
                      <Icon name="edit" size={14} /> Rename
                    </button>
                  )}
                  {!role.is_system && (
                    <button type="button" className="btn btn-ghost btn-sm text-danger" onClick={() => setDeleting({ kind: 'role', item: role })}>
                      <Icon name="trash" size={14} /> Delete role
                    </button>
                  )}
                </div>
              }
            >
              {role.code === 'SUPER_ADMIN' && <p className="role-note">What super admins may do. New permissions start switched on here. If you switch “Manage users & roles” off, super admins lose this page.</p>}
              {role.code === 'EMPLOYEE' && <p className="role-note">Every EUCL employee gets this role automatically when HR adds them. The super admin can give an EUCL employee another role instead (one role per person).</p>}
              {role.code === 'EUCL_HR' && <p className="role-note">Employees in the HR department get this role automatically, instead of Employee. It includes every My wellness page.</p>}
              {groups.map((group) => {
                const onCount = group.items.filter((p) => role.permissions.includes(p.code)).length
                const allOn = onCount === group.items.length
                return (
                  <section key={group.area} className="permission-group" aria-label={`${group.area} permissions`}>
                    <div className="permission-group-head">
                      <h4>{group.area}</h4>
                      <span className="muted">
                        {onCount} of {group.items.length} on
                      </span>
                    </div>
                    <div className="switch-list">
                      <label className="switch-row switch-row-all">
                        <span className="switch-text">
                          <span className="checkbox-title">All</span>
                          <span className="checkbox-description">Every {group.area} permission at once</span>
                        </span>
                        <input type="checkbox" role="switch" className="switch" checked={allOn} disabled={Boolean(saving)} onChange={() => toggleGroup(group.items, allOn)} aria-label={`All ${group.area} permissions`} />
                      </label>
                      {group.items.map((permission) => (
                        <label key={permission.code} className="switch-row">
                          <span className="switch-text">
                            <span className="checkbox-title">
                              {permission.name}
                              {!permission.is_builtin && <Badge tone="info">added</Badge>}
                            </span>
                            {permission.description && <span className="checkbox-description">{permission.description}</span>}
                          </span>
                          <span className="switch-side">
                            {!permission.is_builtin && (
                              <button
                                type="button"
                                className="btn-icon danger"
                                title="Delete permission"
                                aria-label={`Delete ${permission.name}`}
                                onClick={(event) => {
                                  event.preventDefault()
                                  setDeleting({ kind: 'permission', item: permission })
                                }}
                              >
                                <Icon name="trash" size={15} />
                              </button>
                            )}
                            <input
                              type="checkbox"
                              role="switch"
                              className="switch"
                              checked={role.permissions.includes(permission.code)}
                              disabled={Boolean(saving)}
                              onChange={() => toggle(permission.code)}
                              aria-label={permission.name}
                            />
                          </span>
                        </label>
                      ))}
                    </div>
                  </section>
                )
              })}
            </Card>
          )}
        </div>
      )}

      {editing && (
        <RoleFormModal
          role={editing.id ? editing : null}
          withPermissions={false}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setNotice(editing.id ? `${saved.name} saved.` : `${saved.name} added: switch on its permissions.`)
            setEditing(null)
            setSelectedId(saved.id)
            roles.reload()
          }}
        />
      )}

      {addingPermission && (
        <PermissionFormModal
          areas={groups.map((group) => group.area)}
          onClose={() => setAddingPermission(false)}
          onSaved={(saved) => {
            setNotice(`${saved.name} added. Switch it on for the roles that need it.`)
            setAddingPermission(false)
            permissions.reload()
            roles.reload() // the Super admin role gets it straight away
          }}
        />
      )}

      {lockWarning && (
        <ConfirmDialog
          title="Switch off “Manage users & roles” for super admins?"
          confirmLabel="Switch it off"
          danger
          onConfirm={() => savePermissions(lockWarning.wanted, lockWarning.changed, true)}
          onCancel={() => setLockWarning(null)}
        >
          <p>
            Super admins will no longer see Users &amp; roles, so they can’t switch it back on from here. Unless another role
            still has this permission, only a Django superuser can turn it on again, in the Django admin (/admin/ → Roles → Super
            admin).
          </p>
        </ConfirmDialog>
      )}

      {deleting && (
        <ConfirmDialog
          title={`Delete ${deleting.item.name}?`}
          confirmLabel={deleting.kind === 'role' ? 'Delete role' : 'Delete permission'}
          danger
          busy={busy}
          error={actionError}
          onConfirm={remove}
          onCancel={() => {
            setDeleting(null)
            setActionError('')
          }}
        >
          <p>
            {deleting.kind === 'permission'
              ? 'It is taken away from every role that has it.'
              : deleting.item.user_count
                ? `${deleting.item.user_count} user(s) still have this role; remove it from them first.`
                : 'No one has this role, so nothing else changes.'}
          </p>
        </ConfirmDialog>
      )}
    </>
  )
}
