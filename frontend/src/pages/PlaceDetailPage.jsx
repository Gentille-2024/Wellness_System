import { Link, useParams } from 'react-router'
import Icon from '../components/Icon'
import { Alert, Badge, Card, EmptyState, Loading, PageHeader } from '../components/ui'
import useApi from '../hooks/useApi'
import { formatMoney } from '../utils/format'

// EUCL employee: one place and everything it offers, marked covered by EUCL or not
export default function PlaceDetailPage() {
  const { placeId } = useParams()
  const place = useApi(`/places/${placeId}/`)

  const back = (
    <Link to="/my-wellness/places" className="back-link">
      <Icon name="back" size={14} /> All places
    </Link>
  )

  if (place.error) return <>{back}<Alert>{place.error}</Alert></>
  if (place.loading) return <Loading />

  const info = place.data
  const covered = info.services.filter((service) => service.is_covered)
  const notCovered = info.services.filter((service) => !service.is_covered)

  return (
    <>
      <PageHeader back={back} title={info.name} subtitle={info.description || 'Partner place for EUCL employees'} />

      <div className="grid-halves">
        <Card title="Where and how">
          <dl className="details">
            <div>
              <dt><Icon name="map" size={15} /> Address</dt>
              <dd>{info.address || '—'}</dd>
            </div>
            <div>
              <dt><Icon name="phone" size={15} /> Phone</dt>
              <dd>{info.phone || '—'}</dd>
            </div>
          </dl>
          <p className="muted section-gap">
            Give reception your name or employee ID. Services covered by EUCL are free for you; you can use several in a day, all at the same company.
          </p>
        </Card>

        <Card title="At a glance">
          <div className="place-summary">
            <div>
              <div className="stat-value">{covered.length}</div>
              <div className="muted">covered by EUCL</div>
            </div>
            <div>
              <div className="stat-value">{notCovered.length}</div>
              <div className="muted">not covered</div>
            </div>
          </div>
        </Card>
      </div>

      <Card title="Covered by EUCL" subtitle="Free for you: EUCL pays the place" flush>
        {covered.length ? (
          <ul className="service-list">
            {covered.map((service) => (
              <li key={service.id}>
                <div>
                  <div className="cell-main">{service.name}</div>
                  {service.description && <div className="cell-sub">{service.description}</div>}
                </div>
                <div className="service-list-side">
                  <Badge tone="success">Covered by EUCL</Badge>
                  <span className="cell-sub">EUCL pays {formatMoney(service.eucl_price)}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState icon="gift" title="EUCL doesn’t cover any service here yet" />
        )}
      </Card>

      {notCovered.length > 0 && (
        <Card title="Not covered" subtitle="Available at the place, but you would pay yourself" flush>
          <ul className="service-list">
            {notCovered.map((service) => (
              <li key={service.id}>
                <div>
                  <div className="cell-main">{service.name}</div>
                  {service.description && <div className="cell-sub">{service.description}</div>}
                </div>
                <div className="service-list-side">
                  <Badge tone="warning">Not covered</Badge>
                  <span className="cell-sub">{formatMoney(service.price)} at the place</span>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  )
}
