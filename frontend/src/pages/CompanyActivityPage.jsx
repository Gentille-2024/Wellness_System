import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import Icon from '../components/Icon'
import { Alert, Card, EmptyState, Loading, PageHeader, SelectField, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import { formatDate, formatMoney, formatMonth, formatTime, todayISO, toISODate } from '../utils/format'
import { exportVisitsExcel, visitsByEmployeeDay } from '../utils/statement'

// "2026-10" -> first and last day of that month as "YYYY-MM-DD"
function monthRange(yearMonth) {
  const [year, month] = yearMonth.split('-').map(Number)
  return { date_from: `${yearMonth}-01`, date_to: toISODate(new Date(year, month, 0)) }
}

/**
 * EUCL: one company's EUCL employees — who came, on which day and time, and
 * which services they used (one line per employee per day). Filter by month.
 */
export default function CompanyActivityPage() {
  const { companyId } = useParams()
  const navigate = useNavigate()
  const [month, setMonth] = useState(todayISO().slice(0, 7)) // '' = all months
  const [exporting, setExporting] = useState('')
  const [exportError, setExportError] = useState('')

  const companies = useApi('/companies/')
  const visits = useApi('/visits/', { company: companyId, ...(month ? monthRange(month) : {}) })

  const company = (companies.data ?? []).find((c) => String(c.id) === String(companyId))
  const rows = visits.data ?? []

  const lines = visitsByEmployeeDay(rows)

  const total = rows.reduce((sum, visit) => sum + Number(visit.price), 0)
  const people = new Set(rows.map((visit) => visit.employee)).size
  const companyName = company?.name ?? 'Company'
  const period = month ? formatMonth(month) : 'All months'

  const exportAs = async (format) => {
    setExporting(format)
    setExportError('')
    const title = `${companyName} — EUCL employees who used services`
    const name = `${companyName.replace(/\s+/g, '-').toLowerCase()}-${month || 'all'}`
    try {
      if (format === 'excel') {
        await exportVisitsExcel({ title, details: [period], rows, columns: { company: false }, filename: `${name}.xlsx` })
      } else {
        const { exportVisitsPdf } = await import('../utils/pdf')
        exportVisitsPdf({ title, filtersText: period, rows, columns: { company: false }, filename: `${name}.pdf` })
      }
    } catch (err) {
      setExportError(err.message || 'The file could not be prepared.')
    } finally {
      setExporting('')
    }
  }

  const back = (
    <Link to="/eucl" className="back-link">
      <Icon name="back" size={14} /> Dashboard
    </Link>
  )

  return (
    <>
      <PageHeader
        back={back}
        title={companyName}
        subtitle="The EUCL employees who came, when, and the services they used."
        actions={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => exportAs('pdf')} disabled={!rows.length || Boolean(exporting)}>
              <Icon name="file" size={16} /> {exporting === 'pdf' ? 'Preparing…' : 'Export PDF'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => exportAs('excel')} disabled={!rows.length || Boolean(exporting)}>
              <Icon name="download" size={16} /> {exporting === 'excel' ? 'Preparing…' : 'Export Excel'}
            </button>
          </>
        }
      />

      <Alert>{exportError}</Alert>

      <div className="stat-grid">
        <StatCard label="Employees" value={people} hint={period} icon="users" tone="info" />
        <StatCard label="Days attended" value={lines.length} hint="One per employee per day" icon="calendar" />
        <StatCard label="Services" value={rows.length} icon="activity" tone="neutral" />
        <StatCard label="Amount" value={formatMoney(total)} icon="money" tone="success" />
      </div>

      <Card flush>
        <div className="toolbar toolbar-end">
          <SelectField label="Company" value={companyId} onChange={(event) => navigate(`/eucl/activity/${event.target.value}`)}>
            {!company && <option value={companyId}>…</option>}
            {(companies.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </SelectField>
          <label className="field">
            <span className="field-label">Month</span>
            <input type="month" value={month} max={todayISO().slice(0, 7)} onChange={(event) => setMonth(event.target.value)} />
          </label>
          <button type="button" className={month ? 'btn btn-ghost btn-sm' : 'btn btn-secondary btn-sm'} onClick={() => setMonth('')} disabled={!month}>
            All months
          </button>
        </div>

        {visits.error && <Alert>{visits.error}</Alert>}
        {visits.loading ? (
          <Loading />
        ) : lines.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Time</th>
                  <th>Employee</th>
                  <th>Services</th>
                  <th className="num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line.key}>
                    <td className="nowrap">{formatDate(line.date)}</td>
                    <td>{formatTime(line.time)}</td>
                    <td>
                      <div className="cell-main">{line.name}</div>
                      <div className="cell-sub">
                        {line.code}
                        {line.department ? ` · ${line.department}` : ''}
                      </div>
                    </td>
                    <td>{line.services.join(', ')}</td>
                    <td className="num">{formatMoney(line.amount)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td className="cell-main" colSpan={4}>
                    Total · {period}
                  </td>
                  <td className="num cell-main">{formatMoney(total)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <EmptyState icon="users" title={`No EUCL employee used services here in ${month ? formatMonth(month) : 'any month'}`}>
            Pick another month, or All months.
          </EmptyState>
        )}
      </Card>
    </>
  )
}
