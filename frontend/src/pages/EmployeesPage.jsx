import { useRef, useState } from 'react'
import { Link } from 'react-router'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { can } from '../auth/access'
import { EmployeeFormModal } from '../components/forms'
import Icon from '../components/Icon'
import { Alert, Avatar, Badge, Card, ConfirmDialog, EmptyState, FilterButton, Loading, PageHeader, SearchInput, Segmented, SelectField } from '../components/ui'
import useApi from '../hooks/useApi'
import useDebounced from '../hooks/useDebounced'

const STATUS_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Deactivated' },
]

// EUCL HR (manage_employees): the EUCL staff who can use the wellness services
export default function EmployeesPage() {
  const { user } = useAuth()
  const canImport = can(user, 'import_employees')
  // "Upload employees from Excel" alone: the upload, without the list
  const canManage = can(user, 'manage_employees')
  const fileInput = useRef(null)
  const [importing, setImporting] = useState(false)
  const [importErrors, setImportErrors] = useState([]) // [{ row, message }]
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [department, setDepartment] = useState('')
  const debouncedSearch = useDebounced(search)

  const employees = useApi(canManage ? '/employees/' : null, { search: debouncedSearch, status, department })
  const departments = useApi(canManage ? '/employees/departments/' : null)

  const [editing, setEditing] = useState(null) // null = closed, {} = onboard, employee = edit
  const [blocking, setBlocking] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')

  const setActive = async (employee, isActive) => {
    setBusy(true)
    setActionError('')
    try {
      await api.post(`/employees/${employee.id}/set-active/`, { is_active: isActive })
      setNotice(`${employee.user_name} ${isActive ? 'can use the services again' : 'can no longer log in or use services'}.`)
      setBlocking(null)
      employees.reload()
    } catch (err) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  // The empty Excel template: EmpID, First name, Last name, Department, Position
  const downloadTemplate = async () => {
    setActionError('')
    try {
      const { data } = await api.get('/employees/template/', { responseType: 'blob' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(data)
      link.download = 'eucl-employees-template.xlsx'
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }

  // Upload the filled template: nothing is saved if any row has a problem
  const upload = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = '' // the same file can be chosen again after fixing it
    if (!file) return
    setImporting(true)
    setNotice('')
    setActionError('')
    setImportErrors([])
    try {
      const body = new FormData()
      body.append('file', file)
      const { data } = await api.post('/employees/import/', body)
      const parts = []
      if (data.created) parts.push(`${data.created} new employee${data.created === 1 ? '' : 's'} added: their username is their last name, and they create their password with “First time here? Create your account” on the sign-in page`)
      if (data.updated) parts.push(`${data.updated} existing employee${data.updated === 1 ? '' : 's'} updated`)
      setNotice(`${file.name}: ${parts.join(', ')}.`)
      employees.reload()
      departments.reload()
    } catch (err) {
      setActionError(errorMessage(err))
      setImportErrors(err.response?.data?.errors ?? [])
    } finally {
      setImporting(false)
    }
  }

  return (
    <>
      <PageHeader
        title="EUCL employees"
        subtitle="Everyone who can use the wellness services at partner companies."
        actions={
          <>
            {canImport && (
              <>
                <button type="button" className="btn btn-secondary" onClick={downloadTemplate}>
                  <Icon name="download" size={16} /> Excel template
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => fileInput.current?.click()} disabled={importing}>
                  <Icon name="file" size={16} /> {importing ? 'Uploading…' : 'Upload Excel'}
                </button>
                <input ref={fileInput} type="file" accept=".xlsx,.csv" hidden onChange={upload} />
              </>
            )}
            {canManage && (
              <button type="button" className="btn btn-primary" onClick={() => setEditing({})}>
                <Icon name="plus" size={16} /> Onboard employee
              </button>
            )}
          </>
        }
      />

      <Alert type="success">{notice}</Alert>
      <Alert>{blocking ? '' : actionError}</Alert>
      {importErrors.length > 0 && (
        <Card title="Problems to fix in the file" subtitle="Nothing was saved. Correct these rows in Excel, then upload the file again." flush>
          <ul className="import-errors">
            {importErrors.map((item) => (
              <li key={item.message}>
                <Icon name="x" size={14} />
                {item.message}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {!canManage && (
        <Card title="Upload employees from Excel">
          <p className="muted">Download the Excel template, fill in one row per employee, then upload it with “Upload Excel”.</p>
        </Card>
      )}

      {canManage && (
        <Card flush>
          <div className="toolbar">
            <SearchInput value={search} onChange={setSearch} placeholder="Search name, ID, username or email…" />
            <FilterButton
              activeCount={(status ? 1 : 0) + (department ? 1 : 0)}
              onClear={() => {
                setStatus('')
                setDepartment('')
              }}
            >
              <SelectField label="Department" value={department} onChange={(event) => setDepartment(event.target.value)}>
                <option value="">All departments</option>
                {(departments.data ?? []).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </SelectField>
              <div className="field">
                <span className="field-label">Status</span>
                <Segmented options={STATUS_OPTIONS} value={status} onChange={setStatus} />
              </div>
            </FilterButton>
          </div>

          {employees.error && <Alert>{employees.error}</Alert>}
          {employees.loading ? (
            <Loading />
          ) : employees.data?.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Job</th>
                    <th>Contact</th>
                    <th>Status</th>
                    <th className="actions-col" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {employees.data.map((employee) => (
                    <tr key={employee.id} className={employee.is_active ? '' : 'row-muted'}>
                      <td>
                        <div className="cell-person">
                          <Avatar name={employee.user_name || employee.username} size={32} />
                          <div>
                            <Link to={`/eucl/employees/${employee.id}`} className="cell-main cell-link">
                              {employee.user_name || employee.username}
                            </Link>
                            <div className="cell-sub">
                              {employee.employee_id} · @{employee.username}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div>{employee.position}</div>
                        <div className="cell-sub">{employee.department}</div>
                      </td>
                      <td>
                        <div>{employee.email}</div>
                        <div className="cell-sub">{employee.phone}</div>
                      </td>
                      <td>{employee.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="warning">Deactivated</Badge>}</td>
                      <td className="actions-col">
                        <div className="row-actions">
                          <button type="button" className="btn-icon" title="Edit" aria-label={`Edit ${employee.user_name}`} onClick={() => setEditing(employee)}>
                            <Icon name="edit" size={16} />
                          </button>
                          <button
                            type="button"
                            className={employee.is_active ? 'btn-icon danger' : 'btn-icon'}
                            title={employee.is_active ? 'Deactivate' : 'Activate'}
                            aria-label={employee.is_active ? `Deactivate ${employee.user_name}` : `Activate ${employee.user_name}`}
                            onClick={() => (employee.is_active ? setBlocking(employee) : setActive(employee, true))}
                          >
                            <Icon name={employee.is_active ? 'lock' : 'unlock'} size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon="users" title="No employees found">
              {search || status || department ? 'Try different filters.' : 'Onboard the first EUCL employee.'}
            </EmptyState>
          )}
        </Card>
      )}

      {editing && (
        <EmployeeFormModal
          employee={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setNotice(editing.id ? `${saved.user_name}'s details were saved.` : `${saved.user_name} was onboarded as ${saved.employee_id}. Their username is "${saved.username}"; they create their password with “First time here? Create your account” on the sign-in page.`)
            setEditing(null)
            employees.reload()
            departments.reload()
          }}
        />
      )}

      {blocking && (
        <ConfirmDialog
          title={`Deactivate ${blocking.user_name}?`}
          confirmLabel="Deactivate"
          danger
          busy={busy}
          error={actionError}
          onConfirm={() => setActive(blocking, false)}
          onCancel={() => {
            setBlocking(null)
            setActionError('')
          }}
        >
          <p>They can no longer log in or use services. Their history of services used is kept and you can activate them again at any time.</p>
        </ConfirmDialog>
      )}
    </>
  )
}
