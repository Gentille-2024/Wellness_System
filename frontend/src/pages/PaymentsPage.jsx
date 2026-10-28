import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { PaymentFormModal } from '../components/forms'
import Icon from '../components/Icon'
import { Alert, Card, EmptyState, Field, FilterButton, Loading, PageHeader, Segmented, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import { formatDate, formatDateTime, formatMoney, todayISO } from '../utils/format'
import { exportStatementExcel, plural } from '../utils/statement'

const SHOW_OPTIONS = [
  { value: 'no', label: 'Still owed' },
  { value: 'yes', label: 'Paid' },
  { value: '', label: 'All' },
]
const SHOW_LABELS = { no: 'Still owed', yes: 'Paid', '': 'All visits (paid and owed)' }
const EMPTY_DATES = { date_from: '', date_to: '' }

/**
 * scope="eucl":    what EUCL owes each company (amount and employees attended);
 *                  mark periods as paid (manage_payments)
 * scope="company": what EUCL owes this company, per employee, and the payments received
 * Both can export the employees and amounts, with the total, as PDF or Excel.
 */
export default function PaymentsPage({ scope }) {
  const { user } = useAuth()
  const isEucl = scope === 'eucl'
  const companyFilter = isEucl ? {} : { company: user.company?.id }

  const [dates, setDates] = useState(EMPTY_DATES)
  const [show, setShow] = useState('no')
  const [exporting, setExporting] = useState('')
  const [paying, setPaying] = useState(null) // null = closed, { companyId } = open
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const balances = useApi('/payments/balances/', { ...companyFilter, ...dates })
  const statement = useApi('/payments/statement/', { ...companyFilter, ...dates, paid: show })
  const payments = useApi('/payments/', companyFilter)
  const companies = useApi(isEucl ? '/companies/' : null, { status: 'current' })

  const changeDate = (event) => setDates((prev) => ({ ...prev, [event.target.name]: event.target.value }))
  const activeDates = Object.values(dates).filter(Boolean).length

  const rows = balances.data ?? []
  const totals = rows.reduce(
    (sum, row) => ({
      total: sum.total + Number(row.total),
      paid: sum.paid + Number(row.paid),
      unpaid: sum.unpaid + Number(row.unpaid),
      visits: sum.visits + row.visits,
      employees: sum.employees + row.employees,
    }),
    { total: 0, paid: 0, unpaid: 0, visits: 0, employees: 0 },
  )
  const owedTo = rows.filter((row) => Number(row.unpaid) > 0).length

  const statementData = statement.data ?? { companies: [], totals: { companies: 0, employees: 0, visits: 0, amount: 0 } }
  const ownEmployees = statementData.companies[0]?.employees ?? []

  const periodText = () => {
    if (!dates.date_from && !dates.date_to) return 'Period: all dates'
    return `Period: ${dates.date_from ? formatDate(dates.date_from) : 'start'} to ${dates.date_to ? formatDate(dates.date_to) : 'today'}`
  }

  const exportAs = async (format) => {
    setExporting(format)
    setError('')
    const options = {
      title: isEucl ? 'Payment statement — all companies' : `Payment statement — ${user.company?.name}`,
      details: [isEucl ? 'All companies' : `Company: ${user.company?.name}`, periodText(), `Showing: ${SHOW_LABELS[show]}`],
      data: statementData,
      perCompany: isEucl,
    }
    const name = `payments-${isEucl ? 'eucl' : 'company'}-${todayISO()}`
    try {
      if (format === 'pdf') {
        // Loaded only when someone exports
        const { exportStatementPdf } = await import('../utils/pdf')
        exportStatementPdf({ ...options, filename: `${name}.pdf` })
      } else {
        await exportStatementExcel({ ...options, filename: `${name}.xlsx` })
      }
    } catch {
      setError('The file could not be created. Please try again.')
    } finally {
      setExporting('')
    }
  }

  const nothingToExport = statement.loading || !statementData.companies.length

  return (
    <>
      <PageHeader
        title="Payments"
        subtitle={isEucl ? 'What EUCL owes each company for the services its employees used.' : `What EUCL owes ${user.company?.name} and what it has paid.`}
        actions={
          isEucl && (
            <button type="button" className="btn btn-primary" onClick={() => setPaying({})}>
              <Icon name="card" size={16} /> Mark as paid
            </button>
          )
        }
      />

      <Alert type="success">{notice}</Alert>
      <Alert>{error || balances.error || statement.error || payments.error}</Alert>

      <Card flush>
        <div className="toolbar">
          <Segmented options={SHOW_OPTIONS} value={show} onChange={setShow} />
          <div className="toolbar-actions">
            <FilterButton activeCount={activeDates} onClear={() => setDates(EMPTY_DATES)}>
              <div className="form-grid">
                <Field label="From" type="date" name="date_from" value={dates.date_from} max={dates.date_to || undefined} onChange={changeDate} />
                <Field label="To" type="date" name="date_to" value={dates.date_to} min={dates.date_from || undefined} onChange={changeDate} />
              </div>
            </FilterButton>
            <button type="button" className="btn btn-secondary" onClick={() => exportAs('pdf')} disabled={nothingToExport || Boolean(exporting)}>
              <Icon name="file" size={16} /> {exporting === 'pdf' ? 'Preparing…' : 'Export PDF'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => exportAs('excel')} disabled={nothingToExport || Boolean(exporting)}>
              <Icon name="download" size={16} /> {exporting === 'excel' ? 'Preparing…' : 'Export Excel'}
            </button>
          </div>
        </div>
        <p className="toolbar-note muted">
          The exports list every EUCL employee and the amount{isEucl ? ', company by company, with each company’s total' : ''} and the total ·{' '}
          {SHOW_LABELS[show]} · {periodText().replace('Period: ', '')}
        </p>
      </Card>

      <div className="stat-grid">
        <StatCard
          label="EUCL owes"
          value={formatMoney(totals.unpaid)}
          hint={isEucl ? `to ${plural(owedTo, 'company', 'companies')}` : 'not paid yet'}
          icon="card"
          tone="danger"
        />
        <StatCard label="Paid" value={formatMoney(totals.paid)} icon="money" tone="success" />
        <StatCard label="Total value of visits" value={formatMoney(totals.total)} hint={plural(totals.visits, 'visit')} icon="activity" tone="info" />
        {!isEucl && <StatCard label="Employees attended" value={rows[0]?.employees ?? 0} icon="users" />}
      </div>

      {isEucl ? (
        <Card title="What EUCL owes each company" subtitle="Amounts for the dates in the filter; the Owed column is what is still to pay." flush>
          {balances.loading ? (
            <Loading />
          ) : rows.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Company</th>
                    <th className="num">Employees attended</th>
                    <th className="num">Visits</th>
                    <th className="num">Total</th>
                    <th className="num">Paid</th>
                    <th className="num">Owed</th>
                    <th className="actions-col" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.company}>
                      <td className="cell-main">{row.company_name}</td>
                      <td className="num">{row.employees}</td>
                      <td className="num">{row.visits}</td>
                      <td className="num">{formatMoney(row.total)}</td>
                      <td className="num">{formatMoney(row.paid)}</td>
                      <td className={`num cell-main${Number(row.unpaid) > 0 ? ' text-danger' : ''}`}>{formatMoney(row.unpaid)}</td>
                      <td className="actions-col">
                        {Number(row.unpaid) > 0 && (
                          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPaying({ companyId: row.company })}>
                            Pay
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td>Total · {plural(rows.length, 'company', 'companies')}</td>
                    <td className="num" title="An employee who visited several companies is counted at each one">{totals.employees}</td>
                    <td className="num">{totals.visits}</td>
                    <td className="num">{formatMoney(totals.total)}</td>
                    <td className="num">{formatMoney(totals.paid)}</td>
                    <td className="num">{formatMoney(totals.unpaid)}</td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <EmptyState icon="card" title="Nothing to pay yet" />
          )}
        </Card>
      ) : (
        <Card title="Employees and amounts" subtitle={`${SHOW_LABELS[show]} · ${periodText().replace('Period: ', '')}`} flush>
          {statement.loading ? (
            <Loading />
          ) : ownEmployees.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Department</th>
                    <th className="num">Visits</th>
                    <th className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {ownEmployees.map((employee) => (
                    <tr key={employee.employee}>
                      <td>
                        <div className="cell-main">{employee.employee_name || employee.employee_code}</div>
                        <div className="cell-sub">{employee.employee_code}</div>
                      </td>
                      <td>{employee.department}</td>
                      <td className="num">{employee.visits}</td>
                      <td className="num cell-main">{formatMoney(employee.amount)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={2}>Total · {plural(statementData.totals.employees, 'employee')}</td>
                    <td className="num">{statementData.totals.visits}</td>
                    <td className="num">{formatMoney(statementData.totals.amount)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <EmptyState icon="users" title="No employees here">
              Change “{SHOW_LABELS[show]}” or the dates.
            </EmptyState>
          )}
        </Card>
      )}

      <Card title="Payment history" flush>
        {payments.loading ? (
          <Loading />
        ) : payments.data?.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Paid on</th>
                  {isEucl && <th>Company</th>}
                  <th>Period</th>
                  <th className="num">Visits</th>
                  <th className="num">Amount</th>
                  <th>Reference</th>
                </tr>
              </thead>
              <tbody>
                {payments.data.map((payment) => (
                  <tr key={payment.id}>
                    <td className="nowrap">
                      {formatDateTime(payment.paid_at)}
                      {payment.recorded_by_name && <div className="cell-sub">by {payment.recorded_by_name}</div>}
                    </td>
                    {isEucl && <td>{payment.company_name}</td>}
                    <td className="nowrap">
                      {formatDate(payment.period_start)} – {formatDate(payment.period_end)}
                    </td>
                    <td className="num">{payment.visit_count}</td>
                    <td className="num cell-main">{formatMoney(payment.amount)}</td>
                    <td>
                      {payment.reference || '—'}
                      {payment.note && <div className="cell-sub">{payment.note}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="money" title="No payments yet" />
        )}
      </Card>

      {paying && (
        <PaymentFormModal
          companies={companies.data ?? []}
          defaultCompanyId={paying.companyId}
          onClose={() => setPaying(null)}
          onSaved={(payment) => {
            setNotice(`${formatMoney(payment.amount)} to ${payment.company_name} recorded as paid (${payment.visit_count} visits).`)
            setPaying(null)
            balances.reload()
            statement.reload()
            payments.reload()
          }}
        />
      )}
    </>
  )
}
