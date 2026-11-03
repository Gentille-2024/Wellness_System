import { useState } from 'react'
import { Alert, Avatar, Badge, Card, EmptyState, Field, Loading, PageHeader, Segmented, SelectField, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import { formatDateTime, formatMoney } from '../utils/format'

const SHOW_OPTIONS = [
  { value: 'yes', label: 'Price changes' },
  { value: '', label: 'Also new services' },
]

/**
 * Admin and HR ("See price changes"): every time a company's service got a
 * new price, who changed it (company boss, receptionist…) and when.
 */
export default function PriceChangesPage() {
  const [filters, setFilters] = useState({ company: '', date_from: '', date_to: '', changed: 'yes' })
  const setFilter = (name, value) => setFilters((prev) => ({ ...prev, [name]: value }))
  const changes = useApi('/price-changes/', filters)
  const companies = useApi('/companies/')
  const rows = changes.data ?? []
  const ups = rows.filter((row) => Number(row.difference) > 0).length
  const downs = rows.filter((row) => Number(row.difference) < 0).length

  return (
    <>
      <PageHeader title="Price changes" subtitle="Every new price a company gave its services: the old and new price, who changed it and when." />

      <div className="stat-grid">
        <StatCard label="Changes" value={rows.filter((row) => row.old_price !== null).length} icon="edit" />
        <StatCard label="Prices raised" value={ups} icon="activity" tone="danger" />
        <StatCard label="Prices lowered" value={downs} icon="activity" tone="success" />
      </div>

      <Card flush>
        <div className="toolbar toolbar-end">
          <SelectField label="Company" value={filters.company} onChange={(event) => setFilter('company', event.target.value)}>
            <option value="">All companies</option>
            {(companies.data ?? []).map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
          </SelectField>
          <Field label="From" type="date" value={filters.date_from} max={filters.date_to || undefined} onChange={(event) => setFilter('date_from', event.target.value)} />
          <Field label="To" type="date" value={filters.date_to} min={filters.date_from || undefined} onChange={(event) => setFilter('date_to', event.target.value)} />
          <div className="field">
            <span className="field-label">Show</span>
            <Segmented options={SHOW_OPTIONS} value={filters.changed} onChange={(value) => setFilter('changed', value)} />
          </div>
        </div>

        {changes.error && <Alert>{changes.error}</Alert>}
        {changes.loading ? (
          <Loading />
        ) : rows.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Company</th>
                  <th>Service</th>
                  <th className="num">Old price</th>
                  <th className="num">New price</th>
                  <th className="num">Change</th>
                  <th>Changed by</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const difference = row.difference === null ? null : Number(row.difference)
                  return (
                    <tr key={row.id}>
                      <td className="nowrap">{formatDateTime(row.changed_at)}</td>
                      <td>{row.company_name}</td>
                      <td className="cell-main">{row.service_name}</td>
                      <td className="num">{row.old_price === null ? <Badge tone="info">New service</Badge> : formatMoney(row.old_price)}</td>
                      <td className="num cell-main">{formatMoney(row.new_price)}</td>
                      <td className="num">
                        {difference === null ? (
                          <span className="muted">—</span>
                        ) : (
                          <span className={difference > 0 ? 'text-danger' : 'text-success'}>
                            {difference > 0 ? '+' : '−'}
                            {formatMoney(Math.abs(difference))}
                            {Number(row.old_price) > 0 && ` (${difference > 0 ? '+' : '−'}${Math.abs((difference / Number(row.old_price)) * 100).toFixed(0)}%)`}
                          </span>
                        )}
                      </td>
                      <td>
                        <div className="cell-person">
                          <Avatar name={row.changed_by_name} size={30} />
                          <div>
                            <div className="cell-main">{row.changed_by_name || row.changed_by_username || '—'}</div>
                            <div className="cell-sub">
                              {row.changed_by_roles || 'No role'}
                              {row.changed_by_username ? ` · @${row.changed_by_username}` : ''}
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="edit" title="No price changes">
            Changes are recorded from now on, each time a company boss, receptionist or EUCL changes a price.
          </EmptyState>
        )}
      </Card>
    </>
  )
}
