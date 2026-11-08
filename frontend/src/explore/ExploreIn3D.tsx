import { useId, useState } from 'react'
import { availabilityFor, isObservation, localTime, nightDate, observingNightWindow, sortByVisibility, visibleTonightFor } from './astronomy'
import type { ObservationContext, ObservingConditions, PhotoIdentification } from './astronomy'
import { catalog, findObject } from './catalog'
import ObjectExplorerModal from './ObjectExplorerModal'
import ObjectThumbnail from './ObjectThumbnail'
import ObservationControls from './ObservationControls'
import { useNightSummary } from './useNightSummary'
import './explore.css'

export interface ExploreIn3DProps {
  observation?: ObservationContext
  onObservationChange?: (context: ObservationContext) => void
  hideControls?: boolean
  conditions?: ObservingConditions
  contextLabel?: string
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

function ExploreContent({ context, updateContext, hideControls, conditions, contextLabel, initialObjectId, photoIdentification, observation, onObservationChange }: ExploreIn3DProps & { context: ObservationContext; updateContext: (value: ObservationContext) => void }) {
  const sky = useNightSummary(context)
  const [selectedId, setSelectedId] = useState<string | null>(initialObjectId ?? null)
  const [filter, setFilter] = useState('All objects')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('visibility')
  const [tonightOnly, setTonightOnly] = useState(false)
  const [limit, setLimit] = useState(24)
  const nightFilterNoteId = useId()
  const selected = selectedId ? findObject(selectedId) : undefined
  const available = (object: typeof catalog[number]) => availabilityFor(object, context, sky.data)
  const categoryMatches = catalog.filter(object => (filter === 'All objects' || (filter === 'Planets & Moon' && ['Planet', 'Moon'].includes(object.category)) || (filter === 'Stars & clusters' && ['Star', 'Star cluster', 'Star field'].includes(object.category)) || (filter === 'Galaxies' && object.category === 'Galaxy') || (filter === 'Nebulae' && object.category === 'Nebula') || (filter === 'Constellations' && object.category === 'Constellation')) && `${object.name} ${object.subtitle}`.toLowerCase().includes(search.toLowerCase().trim()))
  const matches = tonightOnly ? categoryMatches.filter(object => visibleTonightFor(object, context, sky.data) === true) : categoryMatches
  const sorted = sort === 'visibility' ? sortByVisibility(matches, context, sky.data) : [...matches].sort((a, b) => a.name.localeCompare(b.name))
  const visible = sorted.slice(0, limit)
  return <section className="explore-section" aria-labelledby="explore-title">
    <header className="explore-heading"><div><span className="eyebrow">A closer look at the cosmos</span><h2 id="explore-title">Your sky, up close<span aria-hidden="true">.</span></h2><p>Discover the worlds and stars behind the points of light.</p></div><span className="explore-independent-badge">Explore in 3D</span></header>
    {!hideControls && (!observation || onObservationChange) ? <ObservationControls key={`${context.lat}:${context.lon}:${context.time}`} value={context} onChange={updateContext} /> : <p className="explore-context-caption">{contextLabel ?? 'Observing context'}: {localTime(context.time)} · {context.lat.toFixed(4)}, {context.lon.toFixed(4)}. Select a spot or change the map hour to update this view.</p>}
    <div className="explore-sky-status" aria-live="polite">
      {sky.loading ? <p>Checking astronomy for the local night starting {nightDate(context.time)}…</p> : sky.error ? <><p>{sky.error}</p><button type="button" onClick={sky.retry}>Retry astronomy</button></> : <p>Local night starting {sky.data?.date} · {sky.data?.moon.phase_name || 'Moon phase unavailable'}{typeof sky.data?.moon.illumination === 'number' ? ` · ${Math.round(sky.data.moon.illumination * 100)}% illuminated` : ''}{sky.data?.twilight.astronomical_dusk ? ` · astronomical dusk ${localTime(sky.data.twilight.astronomical_dusk)}` : ''}</p>}
    </div>
    <div className="explore-atlas-tools"><label htmlFor="explore-search">Find an object or constellation<input id="explore-search" type="search" placeholder="Try Orion, M42, Mars…" value={search} onChange={event => { setSearch(event.target.value); setLimit(24) }} /></label><p>{catalog.length} models · year-round WNY atlas<br />Includes partial southern constellations. Availability depends on season, time, horizon and equipment.</p></div>
    <div className="explore-filter-row"><div className="explore-filters" role="group" aria-label="Filter celestial objects">{['All objects', 'Planets & Moon', 'Stars & clusters', 'Galaxies', 'Nebulae', 'Constellations'].map(label => <button type="button" key={label} aria-pressed={filter === label} onClick={() => { setFilter(label); setLimit(24) }}>{label}</button>)}</div><label className="explore-sort">Sort objects<select value={sort} onChange={event => { setSort(event.target.value); setLimit(24) }}><option value="visibility">Visibility</option><option value="name">Name (A–Z)</option></select></label><p aria-live="polite">{matches.length} objects · {visible.length} shown</p></div>
    <div className="explore-night-filter"><label className="explore-night-toggle"><input type="checkbox" role="switch" checked={tonightOnly} aria-describedby={nightFilterNoteId} onChange={event => { setTonightOnly(event.target.checked); setLimit(24) }} /><span>Visible tonight</span></label><p id={nightFilterNoteId} aria-live="polite">{tonightOnly ? observingNightWindow(context, sky.data) ? 'Estimated above the horizon sometime during the selected night, not necessarily at the selected hour. Weather and equipment still matter. Unknown visibility is excluded.' : 'Nighttime astronomy is unavailable. Turn off Visible tonight to browse all objects.' : 'Filter by the selected observing night.'}</p></div>
    {sort === 'visibility' && <p className="explore-sort-note">Above-horizon objects first, then unknown, then below-horizon. Estimated visibility also depends on weather, daylight and equipment.</p>}
    <div className="explore-object-grid">{visible.map(object => {
      const availability = available(object)
      return <article className={`explore-object-card object-${object.id}`} key={object.id}>
        <div className="explore-card-image"><ObjectThumbnail object={object} /><span>{object.category}</span></div>
        <div className="explore-card-body"><span className={`explore-card-status tone-${availability.tone}`}>{availability.label}</span><h3>{object.name}</h3><p>{object.subtitle}</p><button type="button" className="explore-open-button" onClick={() => setSelectedId(object.id)} aria-label={`Explore ${object.name} in 3D`}>Explore in 3D <span aria-hidden="true">↗</span></button></div>
      </article>
    })}</div>
    {matches.length === 0 && <p role="status">{tonightOnly ? 'No objects match Visible tonight and your filters. Try another category or turn off Visible tonight.' : 'No matching objects. Try another name or category.'}</p>}
    {matches.length > limit && <button className="explore-load-more" type="button" onClick={() => setLimit(value => value + 24)}>Show more objects ({matches.length - limit} remaining)</button>}
    <p className="explore-footnote">Close-ups are educational models with enhanced colors and schematic depth. Reference images may use spacecraft observations, infrared or ultraviolet light. They are not a prediction of an unaided-eye view. <a href={`${import.meta.env.BASE_URL}explore/atlas-credits.json`} target="_blank" rel="noreferrer">Atlas sources and licenses</a> · <a href={`${import.meta.env.BASE_URL}explore/d3-celestial-LICENSE.txt`} target="_blank" rel="noreferrer">Constellation data license</a></p>
    {selectedId !== null && <ObjectExplorerModal key={selectedId} object={selected} requestedName={selectedId} observation={context}
      availability={selected ? available(selected) : { label: 'Visibility not calculated', detail: 'No supported object was selected.', tone: 'muted' }}
      conditions={conditions} identification={photoIdentification?.name.toLowerCase() === selected?.name.toLowerCase() ? photoIdentification : undefined} onClose={() => setSelectedId(null)} />}
  </section>
}
