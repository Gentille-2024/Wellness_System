import { useState } from 'react'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Icon from '../components/Icon'
import { Alert, Badge, Card, ConfirmDialog, EmptyState, Field, FilterButton, Loading, PageHeader, SearchInput, Segmented, SelectField, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import useDebounced from '../hooks/useDebounced'
import { formatDate, formatMoney, formatTime, monthStartISO, todayISO } from '../utils/format'

const PAID_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'no', label: 'Unpaid' },
  { value: 'yes', label: 'Paid' },
]

const EMPTY_FILTERS = { date_from: '', date_to: '', company: '', service: '', department: '', paid: '' }

/**
 * Usage records (visits), with filters and PDF export.
 * scope="eucl"    -> every company (EUCL staff)
 * scope="company" -> the user's own company (boss / receptionist)
 * scope="mine"    -> the logged-in employee's own visits
 */
export default function VisitsPage({ scope }) {
  const { user } = useAuth()
  const isEucl = scope === 'eucl'
  const isMine = scope === 'mine'

  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS, date_from: monthStartISO(), date_to: todayISO() })
  const debouncedSearch = useDebounced(search)

  const scopeParams = isMine ? { mine: 1 } : scope === 'company' ? { company: user.company?.id } : {}
  const visits = useApi('/visits/', { ...filters, ...scopeParams, search: debouncedSearch })
  const companies = useApi(isEucl ? '/companies/' : null)
  // Services to filter by: one company's, or all of them
  const services = useApi('/services/', scope === 'company' ? { company: user.company?.id } : filters.company ? { company: filters.company } : {})
  const departments = useApi(isMine ? null : '/employees/departments/')

  const [undoing, setUndoing] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')

  const setFilter = (name, value) => setFilters((prev) => ({ ...prev, [name]: value }))
  const changeFilter = (event) => setFilter(event.target.name, event.target.value)
  const activeCount = Object.values(filters).filter(Boolean).length

  const rows = visits.data ?? []
  const total = rows.reduce((sum, visit) => sum + Number(visit.price), 0)
  const unpaid = rows.filter((visit) => !visit.is_paid).reduce((sum, visit) => sum + Number(visit.price), 0)
  const people = new Set(rows.map((visit) => visit.employee)).size
  const places = new Set(rows.map((visit) => visit.company)).size

  // Undo: super admin any unpaid visit; reception today's unpaid visits at their company
  const canUndo = (visit) =>
    !visit.is_paid && (user.is_superuser || (scope === 'company' && user.role_permissions.includes('record_visits') && visit.visit_date === todayISO()))

  const filtersText = () => {
    const parts = []
    if (filters.date_from || filters.date_to) parts.push(`${filters.date_from ? formatDate(filters.date_from) : 'start'} to ${filters.date_to ? formatDate(filters.date_to) : 'today'}`)
    if (filters.company) parts.push(companies.data?.find((c) => String(c.id) === filters.company)?.name)
    if (filters.service) parts.push(services.data?.find((s) => String(s.id) === filters.service)?.name)
    if (filters.department) parts.push(`Department: ${filters.department}`)
    if (filters.paid) parts.push(filters.paid === 'yes' ? 'Paid only' : 'Unpaid only')
    if (search) parts.push(`Search: "${search}"`)
    return parts.filter(Boolean).join('  ·  ')
  }

  const exportPdf = async () => {
    // The PDF library is large, so it is only downloaded when someone exports
    const { exportVisitsPdf } = await import('../utils/pdf')
    const title = isMine ? `My visits — ${user.full_name || user.username}` : scope === 'company' ? `Visits at ${user.company?.name}` : 'Usage records — all companies'
    exportVisitsPdf({
      title,
      filtersText: filtersText(),
      rows,
      columns: { employee: !isMine, company: !(scope === 'company') },
      filename: `${isMine ? 'my-visits' : 'usage-records'}-${todayISO()}.pdf`,
    })
  }

  const undo = async () => {
    setBusy(true)
    setActionError('')
    try {
      await api.delete(`/visits/${undoing.id}/`)
      setNotice(`${undoing.service_name} for ${undoing.employee_name} was removed.`)
      setUndoing(null)
      visits.reload()
    } catch (err) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title={isMine ? 'My visits' : 'Usage records'}
        subtitle={isMine ? 'Every service you used at partner companies.' : scope === 'company' ? `Services EUCL employees used at ${user.company?.name}.` : 'Every service EUCL employees used, at every company.'}
        actions={
          <button type="button" className="btn btn-secondary" onClick={exportPdf} disabled={!rows.length}>
            <Icon name="file" size={16} /> Export PDF
          </button>
        }
      />

      <Alert type="success">{notice}</Alert>

      <div className="stat-grid">
        <StatCard label="Visits" value={rows.length} icon="activity" />
        {!isMine && <StatCard label="Employees" value={people} icon="users" tone="info" />}
        {scope !== 'company' && <StatCard label="Companies" value={places} icon="building" tone="neutral" />}
        <StatCard label={isMine ? 'Value of my visits' : 'Amount'} value={formatMoney(total)} icon="money" tone="success" />
        {!isMine && <StatCard label="Unpaid" value={formatMoney(unpaid)} icon="card" tone="danger" />}
      </div>

      <Card flush>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder={isMine ? 'Search service or company…' : 'Search employee, service or company…'} />
          <FilterButton activeCount={activeCount} onClear={() => setFilters(EMPTY_FILTERS)}>
            <div className="form-grid">
              <Field label="From" type="date" name="date_from" value={filters.date_from} max={filters.date_to || undefined} onChange={changeFilter} />
              <Field label="To" type="date" name="date_to" value={filters.date_to} min={filters.date_from || undefined} onChange={changeFilter} />
            </div>
            {isEucl && (
              <SelectField label="Company" name="company" value={filters.company} onChange={(event) => setFilters((prev) => ({ ...prev, company: event.target.value, service: '' }))}>
                <option value="">All companies</option>
                {(companies.data ?? []).map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.name}
                  </option>
                ))}
              </SelectField>
            )}
            <SelectField label="Service" name="service" value={filters.service} onChange={changeFilter}>
              <option value="">All services</option>
              {(services.data ?? []).map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                  {scope !== 'company' && !filters.company ? ` — ${service.company_name}` : ''}
                </option>
              ))}
            </SelectField>
            {!isMine && (
              <SelectField label="Department" name="department" value={filters.department} onChange={changeFilter}>
                <option value="">All departments</option>
                {(departments.data ?? []).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </SelectField>
            )}
            {!isMine && (
              <div className="field">
                <span className="field-label">Payment</span>
                <Segmented options={PAID_OPTIONS} value={filters.paid} onChange={(value) => setFilter('paid', value)} />
              </div>
            )}
          </FilterButton>
        </div>

        {visits.error && <Alert>{visits.error}</Alert>}
        {visits.loading ? (
          <Loading />
        ) : rows.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Time</th>
                  {!isMine && <th>Employee</th>}
                  {scope !== 'company' && <th>Company</th>}
                  <th>Service</th>
                  <th className="num">Amount</th>
                  {!isMine && <th>Paid</th>}
                  {!isMine && <th className="actions-col" aria-label="Actions" />}
                </tr>
              </thead>
              <tbody>
                {rows.map((visit) => (
                  <tr key={visit.id}>
                    <td className="nowrap">{formatDate(visit.visit_date)}</td>
                    <td>{formatTime(visit.visited_at)}</td>
                    {!isMine && (
                      <td>
                        <div className="cell-main">{visit.employee_name}</div>
                        <div className="cell-sub">
                          {visit.employee_code} · {visit.department}
                        </div>
                      </td>
                    )}
                    {scope !== 'company' && <td>{visit.company_name}</td>}
                    <td>{visit.service_name}</td>
                    <td className="num">{formatMoney(visit.price)}</td>
                    {!isMine && <td>{visit.is_paid ? <Badge tone="success">Paid</Badge> : <Badge tone="warning">Unpaid</Badge>}</td>}
                    {!isMine && (
                      <td className="actions-col">
                        {canUndo(visit) && (
                          <button type="button" className="btn-icon danger" title="Remove (mistake)" aria-label={`Remove ${visit.service_name} for ${visit.employee_name}`} onClick={() => setUndoing(visit)}>
                            <Icon name="trash" size={16} />
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="activity" title="No visits match these filters">
            Use the Filters button to widen the dates or clear filters.
          </EmptyState>
        )}
      </Card>

      {undoing && (
        <ConfirmDialog
          title="Remove this visit?"
          confirmLabel="Remove visit"
          danger
          busy={busy}
          error={actionError}
          onConfirm={undo}
          onCancel={() => {
            setUndoing(null)
            setActionError('')
          }}
        >
          <p>
            Only do this to correct a mistake. {undoing.employee_name}'s {undoing.service_name} visit on {formatDate(undoing.visit_date)} ({formatMoney(undoing.price)}) will be removed.
          </p>
        </ConfirmDialog>
      )}
    </>
  )
}
