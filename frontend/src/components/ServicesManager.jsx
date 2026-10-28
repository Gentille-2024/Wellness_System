import { useState } from 'react'
import api, { errorMessage } from '../api/client'
import useApi from '../hooks/useApi'
import { formatMoney } from '../utils/format'
import { ServiceFormModal } from './forms'
import Icon from './Icon'
import { Alert, Badge, Card, EmptyState, Loading } from './ui'

// The saved choice as { serviceId: "amount" } for the covered services
const savedChoiceOf = (rows) =>
  Object.fromEntries(rows.filter((s) => s.is_approved).map((s) => [s.id, String(Number(s.eucl_price ?? s.price))]))

/**
 * Everything a company offers, at its own prices.
 *  canEdit   -> edit / switch services on or off (company boss, or EUCL)
 *  canAdd    -> add new services (only the company itself lists what it offers)
 *  canChoose -> EUCL ticks the services its employees may use and sets the
 *               amount it pays per visit for each
 */
export default function ServicesManager({ companyId, canEdit, canAdd = canEdit, canChoose = false, onNotice }) {
  const services = useApi('/services/', { company: companyId })
  const [editing, setEditing] = useState(null) // null = closed, {} = new, service = edit
  const [chosen, setChosen] = useState(null) // null = unchanged, otherwise { id: amount }
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const rows = services.data ?? []
  const choice = chosen ?? savedChoiceOf(rows)
  const changed = chosen !== null
  const tickedIds = Object.keys(choice).map(Number)
  const allTicked = rows.length > 0 && rows.every((service) => service.id in choice)

  // Ticking a service starts its EUCL amount at the company's price
  const tick = (service) => {
    const next = { ...choice }
    if (service.id in next) delete next[service.id]
    else next[service.id] = String(Number(service.eucl_price ?? service.price))
    setChosen(next)
  }
  const setAmount = (service, amount) => setChosen({ ...choice, [service.id]: amount })
  const tickAll = () =>
    setChosen(allTicked ? {} : Object.fromEntries(rows.map((s) => [s.id, choice[s.id] ?? String(Number(s.eucl_price ?? s.price))])))

  const missingAmount = tickedIds.some((id) => choice[id] === '' || Number(choice[id]) < 0)

  const saveChoice = async () => {
    setSaving(true)
    setError('')
    try {
      const payload = tickedIds.map((id) => ({ id, eucl_price: choice[id] }))
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
          ? 'Everything this company offers at its own prices. Tick what EUCL covers and set the amount EUCL pays per visit.'
          : 'Everything you offer. EUCL decides which services it covers and the amount it pays.'
      }
      flush
      actions={
        <>
          {canChoose && changed && (
            <>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setChosen(null)}>
                Undo
              </button>
              <button type="button" className="btn btn-primary btn-sm" onClick={saveChoice} disabled={saving || missingAmount}>
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
      {missingAmount && <Alert>Every ticked service needs the amount EUCL pays.</Alert>}
      {services.loading ? (
        <Loading />
      ) : rows.length ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                {canChoose && (
                  <th className="check-col">
                    <input type="checkbox" checked={allTicked} onChange={tickAll} aria-label="Select all services" title="Select all" />
                  </th>
                )}
                <th>Service</th>
                <th className="num">Company price</th>
                <th className="num">EUCL pays</th>
                <th>For EUCL employees</th>
                <th className="num">Visits</th>
                <th>Offered</th>
                {canEdit && <th className="actions-col" aria-label="Actions" />}
              </tr>
            </thead>
            <tbody>
              {rows.map((service) => {
                const isTicked = service.id in choice
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
                    <td className="num">
                      {canChoose ? (
                        isTicked ? (
                          <input
                            className="amount-input"
                            type="number"
                            min="0"
                            step="1"
                            value={choice[service.id]}
                            onChange={(event) => setAmount(service, event.target.value)}
                            aria-label={`Amount EUCL pays for ${service.name}`}
                          />
                        ) : (
                          <span className="muted">—</span>
                        )
                      ) : service.is_approved ? (
                        formatMoney(service.eucl_price)
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>{service.is_approved ? <Badge tone="success">Covered</Badge> : <Badge tone="warning">Not covered</Badge>}</td>
                    <td className="num">{service.visit_count}</td>
                    <td>{service.is_active ? <Badge tone="neutral">Yes</Badge> : <Badge>Switched off</Badge>}</td>
                    {canEdit && (
                      <td className="actions-col">
                        <div className="row-actions">
                          <button type="button" className="btn-icon" title="Edit" aria-label={`Edit ${service.name}`} onClick={() => setEditing(service)}>
                            <Icon name="edit" size={16} />
                          </button>
                          <button type="button" className="btn btn-ghost btn-sm" onClick={() => toggleOffered(service)}>
                            {service.is_active ? 'Switch off' : 'Switch on'}
                          </button>
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
          companyId={companyId}
          onClose={() => setEditing(null)}
          onSaved={(saved, created) => {
            onNotice(
              created
                ? `${saved.name} added at ${formatMoney(saved.price)}.${canChoose ? ' Tick it and set the amount EUCL pays to cover it.' : ' EUCL will decide whether to cover it.'}`
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
