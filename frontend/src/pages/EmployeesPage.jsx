import { useState } from 'react'
import { Link } from 'react-router'
import api, { errorMessage } from '../api/client'
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
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [department, setDepartment] = useState('')
  const debouncedSearch = useDebounced(search)

  const employees = useApi('/employees/', { search: debouncedSearch, status, department })
  const departments = useApi('/employees/departments/')

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

  return (
    <>
      <PageHeader
        title="EUCL employees"
        subtitle="Everyone who can use the wellness services at partner companies."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setEditing({})}>
            <Icon name="plus" size={16} /> Onboard employee
          </button>
        }
      />

      <Alert type="success">{notice}</Alert>
      <Alert>{blocking ? '' : actionError}</Alert>

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

      {editing && (
        <EmployeeFormModal
          employee={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setNotice(editing.id ? `${saved.user_name}'s details were saved.` : `${saved.user_name} was onboarded as ${saved.employee_id} and can log in as "${saved.username}".`)
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
          <p>They can no longer log in or use services. Their visit history is kept and you can activate them again at any time.</p>
        </ConfirmDialog>
      )}
    </>
  )
}
