import { useState } from 'react'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Icon from '../components/Icon'
import { Alert, Avatar, Card, EmptyState, Loading, PageHeader, SearchInput, SelectField } from '../components/ui'
import useApi from '../hooks/useApi'
import useDebounced from '../hooks/useDebounced'
import { formatDate, formatMoney, todayISO } from '../utils/format'
import { plural } from '../utils/statement'

/**
 * Employees attendance (permission "take_attendance"):
 * the list of EUCL employees, and for each one a tick box per service EUCL
 * covers here. Reception ticks what everyone is taking today, then saves.
 */
export default function AttendancePage() {
  const { user } = useAuth()
  const companyId = user.company?.id

  const [search, setSearch] = useState('')
  const [department, setDepartment] = useState('')
  const debouncedSearch = useDebounced(search)

  // Only services the company offers AND EUCL covers can be recorded
  const services = useApi('/services/', { company: companyId, available: 'yes' })
  const employees = useApi('/employees/', { status: 'active', search: debouncedSearch, department })
  const departments = useApi('/employees/departments/')
  const today = useApi('/visits/', { today: 1, company: companyId })

  const [ticked, setTicked] = useState({}) // { employeeId: [serviceId, …] } not saved yet
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null) // { type, text }

  const offered = services.data ?? []
  const people = employees.data ?? []
  const priceOf = Object.fromEntries(offered.map((service) => [service.id, Number(service.eucl_price)]))

  // What is already recorded today: { employeeId: Set(serviceId) }
  const recorded = {}
  for (const visit of today.data ?? []) {
    if (!recorded[visit.employee]) recorded[visit.employee] = new Set()
    recorded[visit.employee].add(visit.service)
  }

  const isRecorded = (employeeId, serviceId) => Boolean(recorded[employeeId]?.has(serviceId))
  const isTicked = (employeeId, serviceId) => Boolean(ticked[employeeId]?.includes(serviceId))

  const toggle = (employeeId, serviceId) =>
    setTicked((prev) => {
      const current = prev[employeeId] ?? []
      const next = current.includes(serviceId) ? current.filter((id) => id !== serviceId) : [...current, serviceId]
      const copy = { ...prev, [employeeId]: next }
      if (!next.length) delete copy[employeeId]
      return copy
    })

  const pending = Object.entries(ticked)
  const pendingCount = pending.reduce((sum, [, ids]) => sum + ids.length, 0)
  const pendingAmount = pending.reduce((sum, [, ids]) => sum + ids.reduce((s, id) => s + (priceOf[id] ?? 0), 0), 0)

  const rowAmount = (employeeId) =>
    offered.reduce(
      (sum, service) => sum + (isRecorded(employeeId, service.id) || isTicked(employeeId, service.id) ? Number(service.eucl_price) : 0),
      0,
    )

  const save = async () => {
    setSaving(true)
    setMessage(null)
    const names = Object.fromEntries(people.map((person) => [person.id, person.user_name || person.employee_id]))
    const saved = []
    const problems = []
    const stillTicked = {}
    for (const [employeeId, serviceIds] of pending) {
      try {
        const { data } = await api.post('/visits/', { employee: Number(employeeId), services: serviceIds })
        saved.push(...data.visits)
      } catch (err) {
        problems.push(`${names[employeeId] ?? 'Employee'}: ${errorMessage(err)}`)
        stillTicked[employeeId] = serviceIds // keep them so reception can try again
      }
    }
    today.setData((prev) => [...saved, ...(prev ?? [])])
    setTicked(stillTicked)
    setMessage(
      problems.length
        ? { type: 'error', text: `${plural(saved.length, 'service')} saved. Not saved — ${problems.join(' · ')}` }
        : { type: 'success', text: `Attendance saved: ${plural(saved.length, 'service')} for ${plural(pending.length, 'employee')}.` },
    )
    setSaving(false)
  }

  const cameToday = Object.keys(recorded).length

  return (
    <>
      <PageHeader
        title="Employees attendance"
        subtitle={`${formatDate(todayISO())} · Tick the services each EUCL employee is taking today, then save.`}
      />

      {message && <Alert type={message.type}>{message.text}</Alert>}
      <Alert>{services.error || employees.error || today.error}</Alert>

      <Card flush>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="Search name, employee ID or department…" />
          <SelectField label="Department" name="department" value={department} onChange={(event) => setDepartment(event.target.value)} className="field-inline">
            <option value="">All departments</option>
            {(departments.data ?? []).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </SelectField>
          <span className="muted toolbar-count">{plural(cameToday, 'employee')} recorded today</span>
        </div>

        {services.loading || employees.loading || today.loading ? (
          <Loading />
        ) : !offered.length ? (
          <EmptyState icon="sparkles" title="No service to record yet">
            EUCL hasn’t chosen any of this company’s services yet.
          </EmptyState>
        ) : !people.length ? (
          <EmptyState icon="users" title="No EUCL employee found">
            Try another name or department.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table attendance-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  {offered.map((service) => (
                    <th key={service.id} className="attendance-service">
                      {service.name}
                      <span className="cell-sub">{formatMoney(service.eucl_price)}</span>
                    </th>
                  ))}
                  <th className="num">Amount today</th>
                </tr>
              </thead>
              <tbody>
                {people.map((person) => {
                  const name = person.user_name || person.employee_id
                  const amount = rowAmount(person.id)
                  return (
                    <tr key={person.id} className={person.elsewhere_today ? 'row-muted' : ticked[person.id] ? 'row-selected' : ''}>
                      <td>
                        <div className="cell-person">
                          <Avatar name={name} size={32} />
                          <div>
                            <div className="cell-main">{name}</div>
                            <div className="cell-sub">
                              {person.employee_id} · {person.department}
                            </div>
                            {person.elsewhere_today && <div className="cell-sub text-warning">Visited another company today</div>}
                          </div>
                        </div>
                      </td>
                      {offered.map((service) => {
                        const done = isRecorded(person.id, service.id)
                        return (
                          <td key={service.id} className="attendance-service">
                            <input
                              type="checkbox"
                              className="attendance-check"
                              checked={done || isTicked(person.id, service.id)}
                              disabled={done || saving || person.elsewhere_today}
                              onChange={() => toggle(person.id, service.id)}
                              aria-label={`${name}: ${service.name}`}
                              title={
                                done ? 'Already recorded today' : person.elsewhere_today ? 'One company per day: visited another company today' : service.name
                              }
                            />
                          </td>
                        )
                      })}
                      <td className="num">{amount ? <span className="cell-main">{formatMoney(amount)}</span> : <span className="muted">—</span>}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {pendingCount > 0 && (
        <div className="attendance-bar" role="region" aria-label="Attendance not saved yet">
          <span>
            <strong>{plural(pendingCount, 'service')}</strong> ticked for {plural(pending.length, 'employee')} · {formatMoney(pendingAmount)}
          </span>
          <div className="attendance-bar-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setTicked({})} disabled={saving}>
              Clear
            </button>
            <button type="button" className="btn btn-primary" onClick={save} disabled={saving}>
              <Icon name="checkin" size={16} /> {saving ? 'Saving…' : 'Save attendance'}
            </button>
          </div>
        </div>
      )}
    </>
  )
}
