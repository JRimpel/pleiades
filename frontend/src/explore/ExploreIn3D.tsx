import { useState } from 'react'
import { availabilityFor, isObservation, localTime, nightDate } from './astronomy'
import type { ObservationContext, ObservingConditions, PhotoIdentification } from './astronomy'
import { catalog, findObject } from './catalog'
import ObjectExplorerModal from './ObjectExplorerModal'
import ObservationControls from './ObservationControls'
import { useNightSummary } from './useNightSummary'
import './explore.css'

export interface ExploreIn3DProps {
  observation?: ObservationContext
  onObservationChange?: (context: ObservationContext) => void
  hideControls?: boolean
  conditions?: ObservingConditions
  initialObjectId?: string
  photoIdentification?: PhotoIdentification
}

function initialContext(): ObservationContext {
  const now = new Date()
  now.setUTCMinutes(0, 0, 0)
  return { lat: 42.7, lon: -78.4, time: now.toISOString() }
}

export default function ExploreIn3D(props: ExploreIn3DProps) {
  const [internalContext, setInternalContext] = useState(initialContext)
  const context = props.observation ?? internalContext
  if (!isObservation(context)) return <section className="explore-section"><h2>Explore in 3D</h2><p role="alert">The supplied observing context is invalid. Supply WNY coordinates and a valid UTC timestamp.</p></section>
  function updateContext(next: ObservationContext) {
    if (!props.observation) setInternalContext(next)
    props.onObservationChange?.(next)
  }
  return <ExploreContent {...props} context={context} updateContext={updateContext} />
}

function ExploreContent({ context, updateContext, hideControls, conditions, initialObjectId, photoIdentification, observation, onObservationChange }: ExploreIn3DProps & { context: ObservationContext; updateContext: (value: ObservationContext) => void }) {
  const sky = useNightSummary(context)
  const [selectedId, setSelectedId] = useState<string | null>(initialObjectId ?? null)
  const [filter, setFilter] = useState('All objects')
  const selected = selectedId ? findObject(selectedId) : undefined
  const available = (object: typeof catalog[number]) => availabilityFor(object, context, sky.data)
  const visible = catalog.filter(object => filter === 'All objects' || (filter === 'Planets' && object.category === 'Planet') || (filter === 'Stars & clusters' && (object.category === 'Star' || object.category === 'Star cluster')) || (filter === 'Galaxies' && object.category === 'Galaxy'))
  return <section className="explore-section" aria-labelledby="explore-title">
    <header className="explore-heading"><div><span className="eyebrow">A closer look at the cosmos</span><h2 id="explore-title">Your sky, up close<span aria-hidden="true">.</span></h2><p>Discover the worlds and stars behind the points of light.</p></div><span className="explore-independent-badge">Explore in 3D</span></header>
    {!hideControls && (!observation || onObservationChange) ? <ObservationControls key={`${context.lat}:${context.lon}:${context.time}`} value={context} onChange={updateContext} /> : <p className="explore-context-caption">Observing context: {localTime(context.time)} · {context.lat.toFixed(4)}, {context.lon.toFixed(4)}</p>}
    <div className="explore-sky-status" aria-live="polite">
      {sky.loading ? <p>Checking astronomy for the local night starting {nightDate(context.time)}…</p> : sky.error ? <><p>{sky.error}</p><button type="button" onClick={sky.retry}>Retry astronomy</button></> : <p>Local night starting {sky.data?.date} · {sky.data?.moon.phase_name || 'Moon phase unavailable'}{typeof sky.data?.moon.illumination === 'number' ? ` · ${Math.round(sky.data.moon.illumination * 100)}% illuminated` : ''}{sky.data?.twilight.astronomical_dusk ? ` · astronomical dusk ${localTime(sky.data.twilight.astronomical_dusk)}` : ''}</p>}
    </div>
    <div className="explore-filter-row"><div className="explore-filters" role="group" aria-label="Filter celestial objects">{['All objects', 'Planets', 'Stars & clusters', 'Galaxies'].map(label => <button type="button" key={label} aria-pressed={filter === label} onClick={() => setFilter(label)}>{label}</button>)}</div><p>Above the horizon does not guarantee visibility.</p></div>
    <div className="explore-object-grid">{visible.map(object => {
      const availability = available(object)
      return <article className={`explore-object-card object-${object.id}`} key={object.id}>
        <div className="explore-card-image"><img src={object.image} alt={object.imageAlt} loading="lazy" onError={event => { event.currentTarget.hidden = true }} /><span>{object.category}</span></div>
        <div className="explore-card-body"><span className={`explore-card-status tone-${availability.tone}`}>{availability.label}</span><h3>{object.name}</h3><p>{object.subtitle}</p><button type="button" className="explore-open-button" onClick={() => setSelectedId(object.id)} aria-label={`Explore ${object.name} in 3D`}>Explore in 3D <span aria-hidden="true">↗</span></button></div>
      </article>
    })}</div>
    <p className="explore-footnote">Close-ups are educational models. Reference images may use spacecraft observations, infrared or ultraviolet light. They are not a prediction of an unaided-eye view.</p>
    {selectedId !== null && <ObjectExplorerModal key={selectedId} object={selected} requestedName={selectedId} observation={context}
      availability={selected ? available(selected) : { label: 'Visibility not calculated', detail: 'No supported object was selected.', tone: 'muted' }}
      conditions={conditions} identification={photoIdentification?.name.toLowerCase() === selected?.name.toLowerCase() ? photoIdentification : undefined} onClose={() => setSelectedId(null)} />}
  </section>
}
