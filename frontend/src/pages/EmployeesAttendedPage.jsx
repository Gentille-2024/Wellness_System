import { Fragment, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import Icon from '../components/Icon'
import { Alert, Avatar, Card, EmptyState, Field, FilterButton, Loading, PageHeader, SearchInput, SelectField, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import useDebounced from '../hooks/useDebounced'
import { formatDate, formatMoney, monthStartISO, todayISO } from '../utils/format'
import { exportEmployeeSummaryExcel } from '../utils/statement'

const EMPTY_FILTERS = { date_from: '', date_to: '', service: '' }

/**
 * Company staff (permission "See company visits & payments"):
 * every EUCL employee who came, the services they used, how many times,
 * the amount for each employee and the total for all of them.
 */
export default function EmployeesAttendedPage() {
  const { user } = useAuth()
  const companyId = user.company?.id

  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS, date_from: monthStartISO(), date_to: todayISO() })
  const [open, setOpen] = useState(null) // employee id whose visits are shown
  const debouncedSearch = useDebounced(search)

  const report = useApi('/visits/by-employee/', { ...filters, company: companyId, search: debouncedSearch })
  const services = useApi('/services/', { company: companyId })
  // The individual visits of the employee that is opened
  const visits = useApi(open ? '/visits/' : null, { ...filters, company: companyId, employee: open })

  const changeFilter = (event) => setFilters((prev) => ({ ...prev, [event.target.name]: event.target.value }))
  const activeCount = Object.values(filters).filter(Boolean).length

  const data = report.data ?? { employees: [], totals: { employees: 0, visits: 0, amount: 0 } }

  const periodText = () => {
    const parts = []
    if (filters.date_from || filters.date_to) {
      parts.push(`${filters.date_from ? formatDate(filters.date_from) : 'start'} to ${filters.date_to ? formatDate(filters.date_to) : 'today'}`)
    }
    if (filters.service) parts.push(services.data?.find((s) => String(s.id) === filters.service)?.name)
    if (search) parts.push(`Search: "${search}"`)
    return parts.filter(Boolean).join('  ·  ')
  }

  const [exporting, setExporting] = useState('')
  const [exportError, setExportError] = useState('')

  const exportAs = async (format) => {
    setExporting(format)
    setExportError('')
    const title = `EUCL employees attended — ${user.company?.name}`
    const name = `employees-attended-${todayISO()}`
    try {
      if (format === 'pdf') {
        // The PDF library is large, so it is only downloaded when someone exports
        const { exportEmployeeSummaryPdf } = await import('../utils/pdf')
        exportEmployeeSummaryPdf({ title, filtersText: periodText(), data, filename: `${name}.pdf` })
      } else {
        await exportEmployeeSummaryExcel({ title, details: [periodText() || 'All records'], data, filename: `${name}.xlsx` })
      }
    } catch {
      setExportError('The file could not be created. Please try again.')
    } finally {
      setExporting('')
    }
  }

  return (
    <>
      <PageHeader
        title="Employees attended"
        subtitle={`Every EUCL employee who used services at ${user.company?.name}, what they used, and the amount.`}
        actions={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => exportAs('pdf')} disabled={!data.employees.length || Boolean(exporting)}>
              <Icon name="file" size={16} /> {exporting === 'pdf' ? 'Preparing…' : 'Export PDF'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => exportAs('excel')} disabled={!data.employees.length || Boolean(exporting)}>
              <Icon name="download" size={16} /> {exporting === 'excel' ? 'Preparing…' : 'Export Excel'}
            </button>
          </>
        }
      />

      <div className="stat-grid">
        <StatCard label="Employees attended" value={data.totals.employees} icon="users" />
        <StatCard label="Services used" value={data.totals.visits} icon="activity" tone="info" />
        <StatCard label="Total amount" value={formatMoney(data.totals.amount)} hint="What EUCL pays for them" icon="money" tone="success" />
      </div>

      <Card flush>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="Search employee name, ID or service…" />
          <FilterButton activeCount={activeCount} onClear={() => setFilters(EMPTY_FILTERS)}>
            <div className="form-grid">
              <Field label="From" type="date" name="date_from" value={filters.date_from} max={filters.date_to || undefined} onChange={changeFilter} />
              <Field label="To" type="date" name="date_to" value={filters.date_to} min={filters.date_from || undefined} onChange={changeFilter} />
            </div>
            <SelectField label="Service" name="service" value={filters.service} onChange={changeFilter}>
              <option value="">All services</option>
              {(services.data ?? []).map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                </option>
              ))}
            </SelectField>
          </FilterButton>
        </div>

        {(report.error || exportError) && <Alert>{report.error || exportError}</Alert>}
        {report.loading ? (
          <Loading />
        ) : data.employees.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Services used</th>
                  <th className="num">Visits</th>
                  <th className="num">Days</th>
                  <th className="num">Amount</th>
                  <th className="actions-col" aria-label="Details" />
                </tr>
              </thead>
              <tbody>
                {data.employees.map((row) => (
                  <Fragment key={row.employee}>
                    <tr>
                      <td>
                        <div className="cell-person">
                          <Avatar name={row.employee_name} size={32} />
                          <div>
                            <div className="cell-main">{row.employee_name}</div>
                            <div className="cell-sub">
                              {row.employee_code} · {row.department}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div className="service-chips">
                          {row.services.map((service) => (
                            <span key={service.service} className="service-chip">
                              {service.service} <strong>×{service.count}</strong>
                              <span className="muted"> {formatMoney(service.amount)}</span>
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="num">{row.visits}</td>
                      <td className="num">{row.days}</td>
                      <td className="num cell-main">{formatMoney(row.total)}</td>
                      <td className="actions-col">
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => setOpen(open === row.employee ? null : row.employee)}
                          aria-expanded={open === row.employee}
                        >
                          {open === row.employee ? 'Hide' : 'Visits'}
                        </button>
                      </td>
                    </tr>
                    {open === row.employee && (
                      <tr className="detail-row">
                        <td colSpan={6}>
                          {visits.loading ? (
                            <Loading />
                          ) : (
                            <table className="table inner-table">
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  <th>Service</th>
                                  <th className="num">Amount</th>
                                  <th>Recorded by</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(visits.data ?? []).map((visit) => (
                                  <tr key={visit.id}>
                                    <td>{formatDate(visit.visit_date)}</td>
                                    <td>{visit.service_name}</td>
                                    <td className="num">{formatMoney(visit.price)}</td>
                                    <td>{visit.recorded_by_name ?? '—'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td className="cell-main">
                    Total · {data.totals.employees} employee{data.totals.employees === 1 ? '' : 's'}
                  </td>
                  <td />
                  <td className="num">{data.totals.visits}</td>
                  <td />
                  <td className="num cell-main">{formatMoney(data.totals.amount)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <EmptyState icon="users" title="No EUCL employees in this period">
            Use the Filters button to change the dates.
          </EmptyState>
        )}
      </Card>
    </>
  )
}
