import { Link } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { DailyChart } from '../components/charts'
import { Alert, Card, EmptyState, Loading, PageHeader, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import { formatMoney } from '../utils/format'

// Company boss / receptionist: visits and what EUCL owes for them
export default function CompanyDashboard() {
  const { user } = useAuth()
  const stats = useApi('/stats/', { scope: 'company' })
  const canRecord = user.role_permissions.includes('record_visits')

  if (stats.error) return <Alert>{stats.error}</Alert>
  if (stats.loading) return <Loading />
  const data = stats.data

  return (
    <>
      <PageHeader
        title={data.company.name}
        subtitle={data.company.is_active ? 'EUCL employees’ visits and what EUCL owes you.' : 'This company is deactivated: no new visits can be recorded.'}
        actions={
          canRecord && (
            <Link to="/company/record" className="btn btn-primary">
              Record visits
            </Link>
          )
        }
      />

      <div className="stat-grid">
        <StatCard label="Visits today" value={data.visits_today} hint={`${data.visits_this_month} this month`} icon="checkin" />
        <StatCard label="Employees attended" value={data.employees_today} hint={`${data.employees_this_month} this month · ${data.employees_total} in total`} icon="users" tone="info" />
        <StatCard label="Amount this month" value={formatMoney(data.amount_this_month)} icon="money" tone="success" />
        <StatCard label="Owed by EUCL" value={formatMoney(data.unpaid)} hint={`${formatMoney(data.paid)} paid so far`} icon="card" tone="danger" />
        <StatCard label="Services for EUCL" value={data.services} hint={data.services_waiting ? `${data.services_waiting} not covered by EUCL` : `${data.total_visits} visits in total`} icon="sparkles" tone="info" />
      </div>

      <div className="grid-2-1">
        <Card
          title="Payment amount per service"
          subtitle="All visits so far"
          flush
          actions={
            <Link to="/company/payments" className="btn btn-ghost btn-sm">
              Payments
            </Link>
          }
        >
          {data.by_service.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th className="num">EUCL pays now</th>
                    <th className="num">Visits</th>
                    <th className="num">Total</th>
                    <th className="num">Paid</th>
                    <th className="num">Owed</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_service.map((row) => (
                    <tr key={row.service}>
                      <td className="cell-main">{row.service}</td>
                      <td className="num">{formatMoney(row.current_price)}</td>
                      <td className="num">{row.visits}</td>
                      <td className="num">{formatMoney(row.total)}</td>
                      <td className="num">{formatMoney(row.paid)}</td>
                      <td className="num cell-main">{formatMoney(row.unpaid)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td className="cell-main">Total</td>
                    <td />
                    <td className="num">{data.total_visits}</td>
                    <td className="num">{formatMoney(data.total)}</td>
                    <td className="num">{formatMoney(data.paid)}</td>
                    <td className="num cell-main">{formatMoney(data.unpaid)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <EmptyState icon="money" title="No visits yet">
              Amounts appear here once visits are recorded.
            </EmptyState>
          )}
        </Card>

        <Card title="Visits" subtitle="Last 14 days">
          <DailyChart days={data.daily} />
        </Card>
      </div>
    </>
  )
}
