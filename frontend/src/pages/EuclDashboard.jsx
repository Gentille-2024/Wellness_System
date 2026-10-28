import { Link } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { can } from '../auth/access'
import { DailyChart } from '../components/charts'
import { Alert, Card, EmptyState, Loading, PageHeader, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import { formatDateTime, formatMoney } from '../utils/format'

// EUCL side: the whole platform at a glance
export default function EuclDashboard() {
  const { user } = useAuth()
  const stats = useApi('/stats/', { scope: 'platform' })
  const canSeeVisits = can(user, 'view_all_visits', 'manage_payments')
  const recent = useApi(canSeeVisits ? '/visits/' : null, { today: 1 })

  if (stats.error) return <Alert>{stats.error}</Alert>
  if (stats.loading) return <Loading />
  const data = stats.data

  return (
    <>
      <PageHeader
        title={`Welcome back, ${user.first_name || user.username}`}
        subtitle="EUCL wellness across all partner companies."
        actions={
          can(user, 'manage_payments') && (
            <Link to="/eucl/payments" className="btn btn-primary">
              Payments
            </Link>
          )
        }
      />

      <div className="stat-grid">
        <StatCard label="Open companies" value={data.companies_open} hint={`${data.companies_deactivated} deactivated · ${data.companies_deleted} deleted`} icon="building" />
        <StatCard label="EUCL employees" value={data.employees} hint={`${data.active_employees} active`} icon="users" tone="info" />
        <StatCard label="Visits today" value={data.visits_today} hint={`${data.visits_this_month} this month`} icon="checkin" tone="warning" />
        <StatCard label="Amount this month" value={formatMoney(data.amount_this_month)} hint={`${data.total_visits} visits in total`} icon="money" tone="success" />
        <StatCard label="Unpaid to companies" value={formatMoney(data.unpaid)} hint={`${formatMoney(data.paid)} paid so far`} icon="card" tone="danger" />
      </div>

      <div className="grid-2-1">
        <Card title="Visits" subtitle="Last 14 days">
          <DailyChart days={data.daily} />
        </Card>

        <Card title="By company" subtitle="Amount of all visits" flush>
          {data.by_company.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Company</th>
                    <th className="num">Visits</th>
                    <th className="num">Unpaid</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_company.map((row) => (
                    <tr key={row.company}>
                      <td className="cell-main">{row.company}</td>
                      <td className="num">{row.visits}</td>
                      <td className="num">{formatMoney(row.unpaid)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon="building" title="No visits yet" />
          )}
        </Card>
      </div>

      {canSeeVisits && (
        <Card
          title="Today's visits"
          flush
          actions={
            <Link to="/eucl/visits" className="btn btn-ghost btn-sm">
              All usage records
            </Link>
          }
        >
          {recent.data?.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Employee</th>
                    <th>Company</th>
                    <th>Service</th>
                    <th className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.data.slice(0, 10).map((visit) => (
                    <tr key={visit.id}>
                      <td className="nowrap">{formatDateTime(visit.visited_at)}</td>
                      <td>
                        <div className="cell-main">{visit.employee_name}</div>
                        <div className="cell-sub">{visit.employee_code}</div>
                      </td>
                      <td>{visit.company_name}</td>
                      <td>{visit.service_name}</td>
                      <td className="num">{formatMoney(visit.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon="clock" title="No visits yet today" />
          )}
        </Card>
      )}
    </>
  )
}
