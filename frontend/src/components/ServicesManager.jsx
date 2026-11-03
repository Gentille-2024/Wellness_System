import { useState } from 'react'
import api, { errorMessage } from '../api/client'
import useApi from '../hooks/useApi'
import { formatMoney } from '../utils/format'
import { ServiceFormModal } from './forms'
import Icon from './Icon'
import { Alert, Badge, Card, EmptyState, Loading } from './ui'

// The saved choice: the ids of the services EUCL covers
const savedChoiceOf = (rows) => rows.filter((s) => s.is_approved).map((s) => s.id)

/**
 * Everything a company offers, at its own prices.
 *  canEdit   -> edit / switch services on or off (company boss, or EUCL)
 *  canEditPrice -> only change prices (e.g. a receptionist)
 *  canAdd    -> add new services (only the company itself lists what it offers)
 *  canChoose -> EUCL ticks the services its employees may use
 *               (EUCL pays the company's own price)
 */
export default function ServicesManager({ companyId, canEdit, canEditPrice = false, canAdd = canEdit, canChoose = false, onNotice }) {
  const showActions = canEdit || canEditPrice
  const services = useApi('/services/', { company: companyId })
  const [editing, setEditing] = useState(null) // null = closed, {} = new, service = edit
  const [chosen, setChosen] = useState(null) // null = unchanged, otherwise [serviceId, …]
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const rows = services.data ?? []
  const choice = chosen ?? savedChoiceOf(rows)
  const changed = chosen !== null
  const tickedIds = choice
  const allTicked = rows.length > 0 && rows.every((service) => choice.includes(service.id))

  const tick = (service) =>
    setChosen(choice.includes(service.id) ? choice.filter((id) => id !== service.id) : [...choice, service.id])
  const tickAll = () => setChosen(allTicked ? [] : rows.map((s) => s.id))

  const saveChoice = async () => {
    setSaving(true)
    setError('')
    try {
      const payload = tickedIds.map((id) => ({ id }))
      const { data } = await api.post(`/companies/${companyId}/covered-services/`, { services: payload })
      services.setData(data)
      setChosen(null)
      onNotice(`EUCL now covers ${tickedIds.length} of ${rows.length} service${rows.length === 1 ? '' : 's'} here.`)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const toggleOffered = async (service) => {
    setError('')
    try {
      await api.patch(`/services/${service.id}/`, { is_active: !service.is_active })
      onNotice(`${service.name} is now ${service.is_active ? 'switched off' : 'offered'}.`)
      services.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Card
      title="Services & prices"
      subtitle={
        canChoose
          ? 'Everything this company offers at its own prices. Tick the services EUCL covers.'
          : 'Everything you offer, at your prices. EUCL decides which services it covers.'
      }
      flush
      actions={
        <>
          {canChoose && changed && (
            <>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setChosen(null)}>
                Undo
              </button>
              <button type="button" className="btn btn-primary btn-sm" onClick={saveChoice} disabled={saving}>
                {saving ? 'Saving…' : `Save choice (${tickedIds.length})`}
              </button>
            </>
          )}
          {canAdd && !changed && (
            <button type="button" className="btn btn-primary btn-sm" onClick={() => setEditing({})}>
              <Icon name="plus" size={14} /> Add service
            </button>
          )}
        </>
      }
    >
      <Alert>{error || services.error}</Alert>
      {services.loading ? (
        <Loading />
      ) : rows.length ? (
        <div className="table-wrap">
          <table className="table services-table">
            <colgroup>
              {canChoose && <col className="col-check" />}
              <col />
              <col className="col-price" />
              <col className="col-cover" />
              <col className="col-used" />
              <col className="col-offered" />
              {showActions && <col className="col-actions" />}
            </colgroup>
            <thead>
              <tr>
                {canChoose && (
                  <th className="check-col">
                    <input type="checkbox" checked={allTicked} onChange={tickAll} aria-label="Select all services" title="Select all" />
                  </th>
                )}
                <th>Service</th>
                <th className="num">Price</th>
                <th className="center">For EUCL employees</th>
                <th className="center">Times used</th>
                <th className="center">Offered</th>
                {showActions && <th className="actions-col">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((service) => {
                const isTicked = choice.includes(service.id)
                return (
                  <tr key={service.id} className={service.is_active ? '' : 'row-muted'}>
                    {canChoose && (
                      <td className="check-col">
                        <input
                          type="checkbox"
                          checked={isTicked}
                          onChange={() => tick(service)}
                          aria-label={`EUCL covers ${service.name}`}
                        />
                      </td>
                    )}
                    <td>
                      <div className="cell-main">{service.name}</div>
                      <div className="cell-sub">{service.description || '—'}</div>
                    </td>
                    <td className="num">{formatMoney(service.price)}</td>
                    <td className="center">{service.is_approved ? <Badge tone="success">Covered</Badge> : <Badge tone="warning">Not covered</Badge>}</td>
                    <td className="center">{service.visit_count}</td>
                    <td className="center">{service.is_active ? <Badge tone="neutral">Yes</Badge> : <Badge>Switched off</Badge>}</td>
                    {showActions && (
                      <td className="actions-col">
                        <div className="row-actions">
                          {canEdit ? (
                            <>
                              <button type="button" className="btn-icon" title="Edit" aria-label={`Edit ${service.name}`} onClick={() => setEditing(service)}>
                                <Icon name="edit" size={16} />
                              </button>
                              <button type="button" className="btn btn-ghost btn-sm" onClick={() => toggleOffered(service)}>
                                {service.is_active ? 'Switch off' : 'Switch on'}
                              </button>
                            </>
                          ) : (
                            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing(service)} aria-label={`Change the price of ${service.name}`}>
                              <Icon name="edit" size={14} /> Change price
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState icon="sparkles" title="No services yet">
          {canAdd
            ? 'Add every service you offer, with its price.'
            : 'This company hasn’t listed any services yet. It adds them from its own dashboard.'}
        </EmptyState>
      )}

      {editing && (
        <ServiceFormModal
          service={editing.id ? editing : null}
          priceOnly={!canEdit}
          companyId={companyId}
          onClose={() => setEditing(null)}
          onSaved={(saved, created) => {
            onNotice(
              created
                ? `${saved.name} added at ${formatMoney(saved.price)}.${canChoose ? ' Tick it to cover it for EUCL employees.' : ' EUCL will decide whether to cover it.'}`
                : `${saved.name} saved.`,
            )
            setEditing(null)
            services.reload()
          }}
        />
      )}
    </Card>
  )
}
