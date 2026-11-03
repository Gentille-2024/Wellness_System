import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import Icon from '../components/Icon'
import { Alert, Avatar, Card, EmptyState, Field, FilterButton, Loading, PageHeader, SearchInput, SelectField, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import useDebounced from '../hooks/useDebounced'
import { formatDate, formatMoney, monthStartISO, todayISO } from '../utils/format'
import { exportEmployeeSummaryExcel } from '../utils/statement'

const EMPTY_FILTERS = { date_from: '', date_to: '', company: '', service: '' }

/**
 * Every EUCL employee who came, the services they used, how many times,
 * the amount for each employee and the total for all of them.
 * scope="company": company staff, their own company only ("See employees attended").
 * scope="eucl":    EUCL HR, every company, with a company filter
 *                  ("See employees attended (all companies)").
 */
export default function EmployeesAttendedPage({ scope = 'company' }) {
  const { user } = useAuth()
  const eucl = scope === 'eucl'

  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS, date_from: monthStartISO(), date_to: todayISO() })
  const debouncedSearch = useDebounced(search)
  // EUCL: the company chosen in the filter (or every company); staff: their own
  const companyId = eucl ? filters.company : user.company?.id

  const report = useApi('/visits/by-employee/', { ...filters, company: companyId, search: debouncedSearch })
  const companies = useApi(eucl ? '/companies/' : null, { status: 'current' })
  // Services are per company, so EUCL picks a company before a service
  const services = useApi(companyId ? '/services/' : null, { company: companyId })
  const companyList = companies.data?.results ?? companies.data ?? []
  const companyName = eucl ? companyList.find((c) => String(c.id) === String(filters.company))?.name : user.company?.name

  const changeFilter = (event) => {
    const { name, value } = event.target
    // A different company has different services
    setFilters((prev) => ({ ...prev, [name]: value, ...(name === 'company' ? { service: '' } : {}) }))
  }
  const activeCount = Object.values(filters).filter(Boolean).length

  const data = report.data ?? { employees: [], totals: { employees: 0, visits: 0, amount: 0 } }

  const periodText = () => {
    const parts = []
    if (filters.date_from || filters.date_to) {
      parts.push(`${filters.date_from ? formatDate(filters.date_from) : 'start'} to ${filters.date_to ? formatDate(filters.date_to) : 'today'}`)
    }
    if (eucl && filters.company) parts.push(companyName)
    if (filters.service) parts.push(services.data?.find((s) => String(s.id) === filters.service)?.name)
    if (search) parts.push(`Search: "${search}"`)
    return parts.filter(Boolean).join('  ·  ')
  }

  const [exporting, setExporting] = useState('')
  const [exportError, setExportError] = useState('')

  const exportAs = async (format) => {
    setExporting(format)
    setExportError('')
    const title = `EUCL employees attended — ${companyName || 'all companies'}`
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
        subtitle={
          eucl
            ? `Every EUCL employee who used services at ${companyName || 'any partner company'}, what they used, where, and the amount.`
            : `Every EUCL employee who used services at ${user.company?.name}, what they used, and the amount.`
        }
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
            {eucl && (
              <SelectField label="Company" name="company" value={filters.company} onChange={changeFilter}>
                <option value="">All companies</option>
                {companyList.map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.name}
                  </option>
                ))}
              </SelectField>
            )}
            {companyId && (
              <SelectField label="Service" name="service" value={filters.service} onChange={changeFilter}>
                <option value="">All services</option>
                {(services.data?.results ?? services.data ?? []).map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
              </SelectField>
            )}
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
                  <th className="num">Total services</th>
                  <th className="num">Days</th>
                  <th className="num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {data.employees.map((row) => (
                  <tr key={row.employee}>
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
                          <span key={`${service.company}-${service.service}`} className="service-chip">
                            {service.service}
                            {eucl && !filters.company && <span className="muted"> · {service.company}</span>} <strong>×{service.count}</strong>
                            <span className="muted"> {formatMoney(service.amount)}</span>
                          </span>
                          ))}
                        </div>
                      </td>
                      <td className="num">{row.visits}</td>
                      <td className="num">{row.days}</td>
                      <td className="num cell-main">{formatMoney(row.total)}</td>
                    </tr>
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
