import { useState } from 'react'
import { Link } from 'react-router'
import Icon from '../components/Icon'
import { Alert, Badge, EmptyState, Loading, PageHeader, SearchInput, Segmented } from '../components/ui'
import useApi from '../hooks/useApi'
import useDebounced from '../hooks/useDebounced'

const SHOW_OPTIONS = [
  { value: '', label: 'All places' },
  { value: 'yes', label: 'With EUCL-covered services' },
]

// EUCL employee: choose a place, then see what EUCL covers there
export default function PlacesPage() {
  const [search, setSearch] = useState('')
  const [covered, setCovered] = useState('')
  const debouncedSearch = useDebounced(search)
  const places = useApi('/places/', { search: debouncedSearch, covered })

  return (
    <>
      <PageHeader title="Places & services" subtitle="Choose a place to see all its services and which ones EUCL covers for you." />

      <div className="places-toolbar">
        <SearchInput value={search} onChange={setSearch} placeholder="Search a place or a service, e.g. massage…" />
        <Segmented options={SHOW_OPTIONS} value={covered} onChange={setCovered} />
      </div>

      <Alert>{places.error}</Alert>
      {places.loading ? (
        <Loading />
      ) : places.data?.length ? (
        <div className="place-grid">
          {places.data.map((place) => {
            const coveredNames = place.services.filter((service) => service.is_covered).map((service) => service.name)
            return (
              <Link key={place.id} to={`/my-wellness/places/${place.id}`} className="place-card place-link">
                <div className="place-card-head">
                  <span className="stat-icon tone-primary">
                    <Icon name="building" size={20} />
                  </span>
                  <div>
                    <h3>{place.name}</h3>
                    <div className="cell-sub">{place.address || 'Address not given'}</div>
                  </div>
                </div>
                {place.description && <p className="muted">{place.description}</p>}
                <div className="place-card-foot">
                  {place.covered_count ? (
                    <Badge tone="success">
                      EUCL covers {place.covered_count} of {place.services.length}
                    </Badge>
                  ) : (
                    <Badge tone="warning">Nothing covered by EUCL</Badge>
                  )}
                  <span className="place-link-cta">
                    See services <Icon name="back" size={14} className="flip" />
                  </span>
                </div>
                {coveredNames.length > 0 && <div className="cell-sub">{coveredNames.join(' · ')}</div>}
              </Link>
            )
          })}
        </div>
      ) : (
        <EmptyState icon="map" title={search || covered ? 'No place matches' : 'No partner places yet'}>
          {search || covered ? 'Try another word or show all places.' : 'EUCL will add partner companies soon.'}
        </EmptyState>
      )}
    </>
  )
}
