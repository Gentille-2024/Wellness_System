import { Link } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { Alert, Card, EmptyState, Loading, PageHeader, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import { formatDateTime, monthStartISO, todayISO } from '../utils/format'

// EUCL employee: my numbers, how a visit works, and my latest visits
export default function EmployeeHomePage() {
  const { user } = useAuth()
  const visits = useApi('/visits/', { mine: 1 })
  const places = useApi('/places/')

  if (visits.error) return <Alert>{visits.error}</Alert>
  if (visits.loading) return <Loading />

  const employee = user.employee
  if (!employee) {
    return (
      <EmptyState icon="user" title="No employee record">
        Your login isn’t linked to an EUCL employee record. Please contact EUCL HR.
      </EmptyState>
    )
  }

  const rows = visits.data
  const today = rows.filter((visit) => visit.visit_date === todayISO())
  const thisMonth = rows.filter((visit) => visit.visit_date >= monthStartISO())

  return (
    <>
      <PageHeader
        title={`Hello, ${user.first_name || user.username}`}
        subtitle={`${employee.position} · ${employee.department} · EUCL`}
        actions={
          <Link to="/my-wellness/places" className="btn btn-primary">
            Find a place
          </Link>
        }
      />

      <div className="stat-grid">
        <StatCard label="Today" value={today.length} hint={today.length ? today.map((visit) => visit.service_name).join(', ') : 'No services yet today'} icon="checkin" />
        <StatCard label="This month" value={thisMonth.length} hint="services used" icon="calendar" tone="info" />
        <StatCard label="All time" value={rows.length} hint="services used" icon="activity" tone="neutral" />
        <StatCard label="Partner places" value={places.data?.length ?? '—'} hint="you can visit" icon="map" tone="success" />
      </div>

      <div className="grid-1-2">
        <Card title="How a visit works">
          {today.length > 0 && (
            <Alert type="success">
              Today you’re at {today[0].company_name}. You can use more of its services today, but not another company’s.
            </Alert>
          )}
          <ol className="steps">
            <li>Choose a place under “Places & services” and check which services EUCL covers there.</li>
            <li>
              At reception, give your name or your employee ID: <strong>{employee.employee_id}</strong>.
            </li>
            <li>Use as many covered services as you like that day, all at the same company: one company per day.</li>
          </ol>
        </Card>

        <Card
          title="Latest visits"
          flush
          actions={
            <Link to="/my-wellness/visits" className="btn btn-ghost btn-sm">
              All my visits
            </Link>
          }
        >
          {rows.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Company</th>
                    <th>Service</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 6).map((visit) => (
                    <tr key={visit.id}>
                      <td className="nowrap">{formatDateTime(visit.visited_at)}</td>
                      <td>{visit.company_name}</td>
                      <td>{visit.service_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon="clock" title="No visits yet">
              Choose a place under “Places & services” and give reception your employee ID.
            </EmptyState>
          )}
        </Card>
      </div>
    </>
  )
}
