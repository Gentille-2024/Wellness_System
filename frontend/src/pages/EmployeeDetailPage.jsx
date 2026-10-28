import { useState } from 'react'
import { Link, useParams } from 'react-router'
import Icon from '../components/Icon'
import { Alert, Avatar, Badge, Card, EmptyState, Field, FilterButton, Loading, PageHeader, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import { formatDate, formatDateTime, formatMoney } from '../utils/format'
import { plural } from '../utils/statement'

const EMPTY_DATES = { date_from: '', date_to: '' }

/**
 * EUCL (permission manage_employees): one EUCL employee and everything they
 * used: which companies, which services, when, and the amount.
 */
export default function EmployeeDetailPage() {
  const { employeeId } = useParams()
  const [dates, setDates] = useState(EMPTY_DATES)

  const employee = useApi(`/employees/${employeeId}/`)
  const visits = useApi('/visits/', { employee: employeeId, ...dates })

  const back = (
    <Link to="/eucl/employees" className="back-link">
      <Icon name="back" size={14} /> EUCL employees
    </Link>
  )

  if (employee.error) return <>{back}<Alert>{employee.error}</Alert></>
  if (employee.loading) return <Loading />

  const person = employee.data
  const rows = visits.data ?? []
  const changeDate = (event) => setDates((prev) => ({ ...prev, [event.target.name]: event.target.value }))
  const activeDates = Object.values(dates).filter(Boolean).length

  // Totals and one line per company
  const total = rows.reduce((sum, visit) => sum + Number(visit.price), 0)
  const owed = rows.filter((visit) => !visit.is_paid).reduce((sum, visit) => sum + Number(visit.price), 0)
  const days = new Set(rows.map((visit) => visit.visit_date)).size
  const companies = {}
  for (const visit of rows) {
    const company = (companies[visit.company] ??= { name: visit.company_name, days: new Set(), services: {}, visits: 0, amount: 0, last: visit.visit_date })
    company.days.add(visit.visit_date)
    company.services[visit.service_name] = (company.services[visit.service_name] ?? 0) + 1
    company.visits += 1
    company.amount += Number(visit.price)
    if (visit.visit_date > company.last) company.last = visit.visit_date
  }
  const companyRows = Object.entries(companies).sort((a, b) => b[1].amount - a[1].amount)

  return (
    <>
      <PageHeader
        back={back}
        title={person.user_name || person.username}
        subtitle={`${person.employee_id} · ${person.position} · ${person.department}`}
        actions={person.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="warning">Deactivated</Badge>}
      />

      <div className="stat-grid">
        <StatCard label="Services used" value={rows.length} hint={`on ${plural(days, 'day')}`} icon="activity" />
        <StatCard label="Companies visited" value={companyRows.length} icon="building" tone="info" />
        <StatCard label="Total amount" value={formatMoney(total)} hint={owed ? `${formatMoney(owed)} not paid yet` : 'All paid'} icon="money" tone="success" />
      </div>

      <div className="grid-halves">
        <Card title="Contact">
          <dl className="details">
            <div>
              <dt><Icon name="mail" size={15} /> Email</dt>
              <dd>{person.email}</dd>
            </div>
            <div>
              <dt><Icon name="phone" size={15} /> Phone</dt>
              <dd>{person.phone || '—'}</dd>
            </div>
            <div>
              <dt><Icon name="user" size={15} /> Username</dt>
              <dd>@{person.username}</dd>
            </div>
          </dl>
        </Card>

        <Card title="By company" subtitle="Where they went and what they used" flush>
          {companyRows.length ? (
            <ul className="list">
              {companyRows.map(([id, company]) => (
                <li key={id}>
                  <div className="cell-person">
                    <Avatar name={company.name} size={32} />
                    <div>
                      <div className="cell-main">{company.name}</div>
                      <div className="cell-sub">
                        {Object.entries(company.services)
                          .map(([service, count]) => `${service} ×${count}`)
                          .join(' · ')}
                      </div>
                      <div className="cell-sub">
                        {plural(company.days.size, 'day')} · last {formatDate(company.last)}
                      </div>
                    </div>
                  </div>
                  <span className="cell-main nowrap">{formatMoney(company.amount)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon="building" title="No company visited yet" />
          )}
        </Card>
      </div>

      <Card title="Every service used" flush>
        <div className="toolbar">
          <span className="muted">{plural(rows.length, 'service')} · {formatMoney(total)}</span>
          <div className="toolbar-actions">
            <FilterButton activeCount={activeDates} onClear={() => setDates(EMPTY_DATES)}>
              <div className="form-grid">
                <Field label="From" type="date" name="date_from" value={dates.date_from} max={dates.date_to || undefined} onChange={changeDate} />
                <Field label="To" type="date" name="date_to" value={dates.date_to} min={dates.date_from || undefined} onChange={changeDate} />
              </div>
            </FilterButton>
          </div>
        </div>
        <Alert>{visits.error}</Alert>
        {visits.loading ? (
          <Loading />
        ) : rows.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Company</th>
                  <th>Service</th>
                  <th className="num">Amount</th>
                  <th>Payment</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((visit) => (
                  <tr key={visit.id}>
                    <td className="nowrap">{formatDateTime(visit.visited_at)}</td>
                    <td>{visit.company_name}</td>
                    <td>{visit.service_name}</td>
                    <td className="num">{formatMoney(visit.price)}</td>
                    <td>{visit.is_paid ? <Badge tone="success">Paid</Badge> : <Badge tone="warning">Owed</Badge>}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3}>Total · {plural(rows.length, 'service')}</td>
                  <td className="num">{formatMoney(total)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <EmptyState icon="clock" title={activeDates ? 'Nothing in these dates' : 'No services used yet'} />
        )}
      </Card>
    </>
  )
}
