import { useState } from 'react'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Icon from '../components/Icon'
import { Alert, Avatar, Card, EmptyState, Loading, PageHeader, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import { formatMoney, formatTime } from '../utils/format'

// Company receptionist: find the EUCL employee, tick the services they used
export default function RecordVisitsPage() {
  const { user } = useAuth()
  const companyId = user.company?.id
  // Only services the company offers AND EUCL covers can be recorded
  const services = useApi('/services/', { company: companyId, available: 'yes' })
  const today = useApi('/visits/', { today: 1, company: companyId })

  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null) // null = nothing searched yet
  const [selected, setSelected] = useState(null) // the employee being served
  const [ticked, setTicked] = useState([]) // service ids
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null) // { type, text }

  const todayRows = today.data ?? []
  const offered = services.data ?? []
  const tickedTotal = offered.filter((service) => ticked.includes(service.id)).reduce((sum, service) => sum + Number(service.price), 0)
  // Today's table: one line per employee, their services joined with commas
  const todayByEmployee = []
  for (const visit of todayRows) {
    let line = todayByEmployee.find((row) => row.employee === visit.employee)
    if (!line) {
      line = { employee: visit.employee, name: visit.employee_name, code: visit.employee_code, time: visit.visited_at, services: [], amount: 0, recordedBy: [] }
      todayByEmployee.push(line)
    }
    line.services.push(visit.service_name)
    line.amount += Number(visit.price)
    if (visit.visited_at > line.time) line.time = visit.visited_at // the latest service
    const by = visit.recorded_by_name ?? '—'
    if (!line.recordedBy.includes(by)) line.recordedBy.push(by)
  }
  const usedTodayHere = selected ? todayRows.filter((visit) => visit.employee === selected.id).map((visit) => visit.service) : []

  const search = async (event) => {
    event.preventDefault()
    const text = query.trim()
    if (!text) return
    setSearching(true)
    setMessage(null)
    setSelected(null)
    try {
      const { data } = await api.get('/employees/', { params: { search: text, status: 'active' } })
      setResults(data)
      if (data.length === 1) choose(data[0]) // an employee ID finds exactly one person
    } catch (err) {
      setMessage({ type: 'error', text: errorMessage(err) })
    } finally {
      setSearching(false)
    }
  }

  const choose = (employee) => {
    setSelected(employee)
    setTicked([])
  }

  const toggle = (serviceId) =>
    setTicked((prev) => (prev.includes(serviceId) ? prev.filter((id) => id !== serviceId) : [...prev, serviceId]))

  const record = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const { data } = await api.post('/visits/', { employee: selected.id, services: ticked })
      const names = data.visits.map((visit) => visit.service_name).join(', ')
      setMessage({
        type: 'success',
        text:
          `Recorded for ${selected.user_name}: ${names}.` +
          (data.skipped.length ? ` Already recorded today: ${data.skipped.join(', ')}.` : ''),
      })
      today.setData((prev) => [...data.visits, ...(prev ?? [])])
      setTicked([])
    } catch (err) {
      setMessage({ type: 'error', text: errorMessage(err) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader title="Record services" subtitle="Find the EUCL employee (type their name or employee ID), then tick the services they used. One company per employee per day." />

      {!user.company?.is_active && <Alert>This company is deactivated, so services can't be recorded right now.</Alert>}

      <div className="stat-grid">
        <StatCard label="Services today" value={todayRows.length} icon="checkin" />
        <StatCard label="Amount today" value={formatMoney(todayRows.reduce((sum, visit) => sum + Number(visit.price), 0))} icon="money" tone="success" />
        <StatCard label="Employees served today" value={new Set(todayRows.map((visit) => visit.employee)).size} icon="users" tone="info" />
      </div>

      <div className="grid-1-2">
        <Card title="1. Find the employee">
          <form className="checkin-search" onSubmit={search}>
            <Icon name="search" size={20} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. EMP0003 or John" aria-label="Search EUCL employees" autoFocus />
            <button type="submit" className="btn btn-primary" disabled={searching}>
              {searching ? 'Searching…' : 'Find'}
            </button>
          </form>

          {results !== null &&
            (results.length === 0 ? (
              <EmptyState icon="search" title={`No EUCL employee matches “${query}”`} />
            ) : (
              <ul className="pick-list">
                {results.map((employee) => (
                  <li key={employee.id}>
                    <button type="button" className={selected?.id === employee.id ? 'pick active' : 'pick'} onClick={() => choose(employee)}>
                      <Avatar name={employee.user_name} size={36} />
                      <span>
                        <span className="cell-main">{employee.user_name}</span>
                        <span className="cell-sub">
                          {employee.employee_id} · {employee.department}
                        </span>
                        {employee.elsewhere_today && <span className="cell-sub text-warning">Visited another company today</span>}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ))}
        </Card>

        <Card title="2. Tick the services used" subtitle={selected ? `${selected.user_name} · ${selected.employee_id}` : 'Choose an employee first'}>
          {message && <Alert type={message.type}>{message.text}</Alert>}
          {selected?.elsewhere_today && (
            <Alert type="warning">
              {selected.user_name} already used services at another company today. An EUCL employee can visit only one company per day.
            </Alert>
          )}
          {services.loading ? (
            <Loading />
          ) : !offered.length ? (
            <EmptyState icon="sparkles" title="No services available for EUCL yet">
              Your boss adds the services; EUCL chooses which ones its employees may use.
            </EmptyState>
          ) : (
            <>
              <div className="service-ticks">
                {offered.map((service) => {
                  const doneToday = usedTodayHere.includes(service.id)
                  return (
                    <label key={service.id} className={`checkbox-card ${doneToday ? 'done' : ''}`}>
                      <input
                        type="checkbox"
                        checked={ticked.includes(service.id)}
                        disabled={!selected || doneToday || selected.elsewhere_today}
                        onChange={() => toggle(service.id)}
                        aria-label={service.name}
                      />
                      <span>
                        <span className="checkbox-title">{service.name}</span>
                        <span className="checkbox-description">{doneToday ? 'Already recorded today' : formatMoney(service.price)}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
              <div className="record-bar">
                <span className="muted">
                  {ticked.length} service{ticked.length === 1 ? '' : 's'} · {formatMoney(tickedTotal)}
                </span>
                <button type="button" className="btn btn-primary" disabled={!selected || !ticked.length || saving} onClick={record}>
                  {saving ? 'Saving…' : 'Record services'}
                </button>
              </div>
            </>
          )}
        </Card>
      </div>

      <Card
        title="Today at this company"
        subtitle={`${todayByEmployee.length} employee${todayByEmployee.length === 1 ? '' : 's'} · ${todayRows.length} service${todayRows.length === 1 ? '' : 's'} recorded`}
        flush
      >
        {todayRows.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Employee</th>
                  <th>Services</th>
                  <th className="num">Amount</th>
                  <th>Recorded by</th>
                </tr>
              </thead>
              <tbody>
                {todayByEmployee.map((line) => (
                  <tr key={line.employee}>
                    <td>{formatTime(line.time)}</td>
                    <td>
                      <div className="cell-main">{line.name}</div>
                      <div className="cell-sub">{line.code}</div>
                    </td>
                    <td>{line.services.join(', ')}</td>
                    <td className="num">{formatMoney(line.amount)}</td>
                    <td>{line.recordedBy.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="clock" title="Nothing recorded yet today" />
        )}
      </Card>
    </>
  )
}
