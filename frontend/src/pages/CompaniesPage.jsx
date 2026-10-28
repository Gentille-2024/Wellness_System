import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import CompanyStatus from '../components/CompanyStatus'
import { CompanyFormModal } from '../components/forms'
import Icon from '../components/Icon'
import { Alert, Card, EmptyState, Loading, PageHeader, SearchInput, Segmented } from '../components/ui'
import useApi from '../hooks/useApi'
import useCompanyActions from '../hooks/useCompanyActions'
import useDebounced from '../hooks/useDebounced'

const STATUS_OPTIONS = [
  { value: 'current', label: 'Current' },
  { value: 'open', label: 'Open' },
  { value: 'deactivated', label: 'Deactivated' },
  { value: 'deleted', label: 'Deleted' },
  { value: '', label: 'All' },
]

// Super admin: the service providers EUCL employees can visit
export default function CompaniesPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('current')
  const debouncedSearch = useDebounced(search)
  const companies = useApi('/companies/', { search: debouncedSearch, status })

  const [editing, setEditing] = useState(null) // null = closed, {} = new, company = edit
  const navigate = useNavigate()
  const [notice, setNotice] = useState('')
  const actions = useCompanyActions((message) => {
    setNotice(message)
    companies.reload()
  })

  return (
    <>
      <PageHeader
        title="Companies"
        subtitle="Places where EUCL employees can use wellness services."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setEditing({})}>
            <Icon name="plus" size={16} /> Add company
          </button>
        }
      />

      <Alert type="success">{notice}</Alert>

      <Card flush>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="Search companies…" />
          <Segmented options={STATUS_OPTIONS} value={status} onChange={setStatus} />
        </div>

        {companies.error && <Alert>{companies.error}</Alert>}
        {companies.loading ? (
          <Loading />
        ) : companies.data?.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Contact</th>
                  <th className="num">Services covered</th>
                  <th className="num">Staff</th>
                  <th>Status</th>
                  <th className="actions-col" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {companies.data.map((company) => (
                  <tr key={company.id} className={company.is_deleted ? 'row-muted' : ''}>
                    <td>
                      <Link to={`/eucl/companies/${company.id}`} className="cell-link">
                        {company.name}
                      </Link>
                      <div className="cell-sub">{company.address || '—'}</div>
                    </td>
                    <td>
                      <div>{company.email}</div>
                      <div className="cell-sub">{company.phone || '—'}</div>
                    </td>
                    <td className="num">{company.covered_count} of {company.service_count}</td>
                    <td className="num">{company.staff_count}</td>
                    <td>
                      <CompanyStatus company={company} />
                    </td>
                    <td className="actions-col">
                      <div className="row-actions">
                        {company.is_deleted ? (
                          <button type="button" className="btn btn-secondary btn-sm" onClick={() => actions.ask(company, 'restore')}>
                            <Icon name="restore" size={14} /> Restore
                          </button>
                        ) : (
                          <>
                            <button type="button" className="btn-icon" title="Edit" aria-label={`Edit ${company.name}`} onClick={() => setEditing(company)}>
                              <Icon name="edit" size={16} />
                            </button>
                            <button
                              type="button"
                              className="btn-icon"
                              title={company.is_active ? 'Deactivate' : 'Activate'}
                              aria-label={company.is_active ? `Deactivate ${company.name}` : `Activate ${company.name}`}
                              onClick={() => actions.ask(company, company.is_active ? 'deactivate' : 'activate')}
                            >
                              <Icon name={company.is_active ? 'pause' : 'play'} size={16} />
                            </button>
                            <button type="button" className="btn-icon danger" title="Delete" aria-label={`Delete ${company.name}`} onClick={() => actions.ask(company, 'delete')}>
                              <Icon name="trash" size={16} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="building" title="No companies found">
            {search ? 'Try a different search.' : 'Add the first place EUCL employees can visit.'}
          </EmptyState>
        )}
      </Card>

      {editing && (
        <CompanyFormModal
          company={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={(saved, note) => {
            if (note) {
              // New company: open its page, where EUCL chooses the covered services
              navigate(`/eucl/companies/${saved.id}`, { state: { notice: `${saved.name} added. ${note}` } })
              return
            }
            setNotice(`${saved.name} saved.`)
            setEditing(null)
            companies.reload()
          }}
        />
      )}
      {actions.dialog}
    </>
  )
}
