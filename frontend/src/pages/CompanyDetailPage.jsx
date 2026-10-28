import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import CompanyStatus from '../components/CompanyStatus'
import { CompanyFormModal } from '../components/forms'
import Icon from '../components/Icon'
import ServicesManager from '../components/ServicesManager'
import { Alert, Avatar, Badge, Card, EmptyState, Loading, PageHeader, StatCard } from '../components/ui'
import useApi from '../hooks/useApi'
import useCompanyActions from '../hooks/useCompanyActions'
import { formatDate, formatMoney } from '../utils/format'

// Super admin: one service provider — details, services & prices, staff, money
export default function CompanyDetailPage() {
  const { companyId } = useParams()
  const company = useApi(`/companies/${companyId}/`)
  const staff = useApi('/users/', { company: companyId })
  const balance = useApi('/payments/balances/', { company: companyId })

  const location = useLocation()
  const [notice, setNotice] = useState(location.state?.notice ?? '')
  const [editingCompany, setEditingCompany] = useState(false)
  const actions = useCompanyActions((message) => {
    setNotice(message)
    company.reload()
    staff.reload()
  })

  const back = (
    <Link to="/eucl/companies" className="back-link">
      <Icon name="back" size={14} /> All companies
    </Link>
  )

  if (company.error) return <>{back}<Alert>{company.error}</Alert></>
  if (company.loading) return <Loading />

  const info = company.data
  const money = balance.data?.[0] ?? { total: 0, paid: 0, unpaid: 0, visits: 0 }

  return (
    <>
      <PageHeader
        back={back}
        title={info.name}
        subtitle={info.is_deleted ? `Deleted on ${formatDate(info.deleted_at.slice(0, 10))} · history kept` : `Partner since ${formatDate(info.created_at.slice(0, 10))}`}
        actions={
          info.is_deleted ? (
            <button type="button" className="btn btn-primary" onClick={() => actions.ask(info, 'restore')}>
              <Icon name="restore" size={16} /> Restore
            </button>
          ) : (
            <>
              <button type="button" className="btn btn-secondary" onClick={() => setEditingCompany(true)}>
                <Icon name="edit" size={16} /> Edit
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => actions.ask(info, info.is_active ? 'deactivate' : 'activate')}>
                <Icon name={info.is_active ? 'pause' : 'play'} size={16} /> {info.is_active ? 'Deactivate' : 'Activate'}
              </button>
              <button type="button" className="btn btn-danger-outline" onClick={() => actions.ask(info, 'delete')}>
                <Icon name="trash" size={16} /> Delete
              </button>
            </>
          )
        }
      />

      <Alert type="success">{notice}</Alert>

      <div className="stat-grid">
        <StatCard label="Status" value={<CompanyStatus company={info} />} icon="building" />
        <StatCard label="Visits" value={money.visits} hint="All time" icon="activity" tone="info" />
        <StatCard label="Unpaid" value={formatMoney(money.unpaid)} icon="card" tone="danger" />
        <StatCard label="Paid" value={formatMoney(money.paid)} icon="money" tone="success" />
      </div>

      <div className="grid-halves">
          <Card title="Company details">
            <dl className="details">
              <div>
                <dt><Icon name="mail" size={15} /> Email</dt>
                <dd>{info.email}</dd>
              </div>
              <div>
                <dt><Icon name="phone" size={15} /> Phone</dt>
                <dd>{info.phone || '—'}</dd>
              </div>
              <div>
                <dt><Icon name="map" size={15} /> Address</dt>
                <dd>{info.address || '—'}</dd>
              </div>
            </dl>
            {info.description && <p className="muted section-gap">{info.description}</p>}
          </Card>

          <Card title="Staff" subtitle="The company boss adds its staff from the company dashboard">
            {staff.data?.length ? (
              <ul className="list">
                {staff.data.map((member) => {
                  const name = `${member.first_name} ${member.last_name}`.trim() || member.username
                  return (
                    <li key={member.id}>
                      <div className="cell-person">
                        <Avatar name={name} size={32} />
                        <div>
                          <div className="cell-main">{name}</div>
                          <div className="cell-sub">@{member.username}</div>
                        </div>
                      </div>
                      <div className="badge-row">
                        {member.role_names.map((role) => (
                          <Badge key={role} tone="primary">
                            {role}
                          </Badge>
                        ))}
                        {!member.is_active && <Badge tone="warning">Blocked</Badge>}
                      </div>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <EmptyState icon="shield" title="No staff yet">
                The company boss adds staff after signing in.
              </EmptyState>
            )}
          </Card>
      </div>

      <ServicesManager companyId={companyId} canEdit={!info.is_deleted} canAdd={false} canChoose={!info.is_deleted} onNotice={setNotice} />

      {editingCompany && (
        <CompanyFormModal
          company={info}
          onClose={() => setEditingCompany(false)}
          onSaved={() => {
            setNotice('Company details saved.')
            setEditingCompany(false)
            company.reload()
          }}
        />
      )}

      {actions.dialog}
    </>
  )
}
