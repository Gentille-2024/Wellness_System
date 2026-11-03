import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { FEEDBACK_KINDS } from '../utils/feedback'
import Icon from '../components/Icon'
import { Alert, Avatar, Badge, Card, EmptyState, Field, Loading, PageHeader, SearchInput, Segmented, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import useDebounced from '../hooks/useDebounced'
import { formatDate, formatDateTime } from '../utils/format'

const KIND_OPTIONS = [{ value: '', label: 'All' }, ...FEEDBACK_KINDS.map((kind) => ({ value: kind.value, label: kind.label }))]
const toneOf = (kind) => (kind === 'complaint' ? 'danger' : 'info')

/**
 * The feedback EUCL employees sent about the services they used.
 * scope="eucl"    -> every company (HR, super admin: "See employees' feedback")
 * scope="company" -> this company (boss, receptionist: "See feedback on our services")
 */
export default function FeedbackPage({ scope }) {
  const { user } = useAuth()
  const isEucl = scope === 'eucl'
  const [kind, setKind] = useState('')
  const [search, setSearch] = useState('')
  const [dates, setDates] = useState({ date_from: '', date_to: '' })
  const debouncedSearch = useDebounced(search)

  const feedback = useApi('/feedback/', { kind, search: debouncedSearch, ...dates })
  const rows = feedback.data ?? []
  const count = (value) => rows.filter((row) => row.feedback_kind === value).length

  return (
    <>
      <PageHeader
        title="Feedback"
        subtitle={
          isEucl
            ? 'Comments and complaints EUCL employees sent about the services they used, at every company.'
            : `Comments and complaints EUCL employees sent about services at ${user.company?.name}.`
        }
      />

      <div className="stat-grid">
        <StatCard label="Comments" value={count('comment')} icon="edit" tone="info" />
        <StatCard label="Complaints" value={count('complaint')} icon="x" tone="danger" />
      </div>

      <Card flush>
        <div className="toolbar toolbar-end">
          <SearchInput value={search} onChange={setSearch} placeholder={isEucl ? 'Search employee, service or company…' : 'Search employee or service…'} />
          <div className="field">
            <span className="field-label">Type</span>
            <Segmented options={KIND_OPTIONS} value={kind} onChange={setKind} />
          </div>
          <Field label="Service from" type="date" value={dates.date_from} max={dates.date_to || undefined} onChange={(event) => setDates((prev) => ({ ...prev, date_from: event.target.value }))} />
          <Field label="to" type="date" value={dates.date_to} min={dates.date_from || undefined} onChange={(event) => setDates((prev) => ({ ...prev, date_to: event.target.value }))} />
        </div>

        {feedback.error && <Alert>{feedback.error}</Alert>}
        {feedback.loading ? (
          <Loading />
        ) : rows.length ? (
          <ul className="feedback-list">
            {rows.map((row) => (
              <li key={row.id}>
                <Avatar name={row.employee_name} size={36} />
                <div className="feedback-body">
                  <div className="feedback-top">
                    <span className="cell-main">{row.employee_name}</span>
                    <span className="cell-sub">{row.employee_code}{row.department ? ` · ${row.department}` : ''}</span>
                    <Badge tone={toneOf(row.feedback_kind)}>{row.feedback_kind_label}</Badge>
                  </div>
                  <div className="cell-sub">
                    <Icon name="sparkles" size={13} /> {row.service_name}
                    {isEucl ? ` at ${row.company_name}` : ''} · used on {formatDate(row.visit_date)} · sent {formatDateTime(row.feedback_at)}
                  </div>
                  {row.feedback_message ? <p className="feedback-message">{row.feedback_message}</p> : <p className="feedback-message muted">No message.</p>}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState icon="mail" title="No feedback yet">
            Employees can give feedback on each service from their My services page.
          </EmptyState>
        )}
      </Card>
    </>
  )
}
