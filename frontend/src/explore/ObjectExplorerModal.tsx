import { Component, lazy, Suspense, useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import type { CelestialObject } from './catalog'
import { clusterMembers } from './catalog'
import type { Availability, ObservationContext, ObservingConditions, PhotoIdentification } from './astronomy'
import { localTime } from './astronomy'

const ModelViewer = lazy(() => import('./ObjectModelViewer'))

class ViewerBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

function Poster({ object, message }: { object: CelestialObject; message: string }) {
  return <div className="explore-static-fallback"><img src={object.image} alt={object.imageAlt} /><p role="status">{message}</p></div>
}

interface Props {
  object: CelestialObject | undefined
  requestedName?: string
  observation: ObservationContext
  availability: Availability
  conditions?: ObservingConditions
  identification?: PhotoIdentification
  onClose: () => void
}

export default function ObjectExplorerModal({ object, requestedName, observation, availability, conditions, identification, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const triggerRef = useRef(document.activeElement instanceof HTMLElement ? document.activeElement : null)
  const titleId = useId()
  useEffect(() => {
    const trigger = triggerRef.current
    const dialog = dialogRef.current!
    const overflow = document.body.style.overflow
    dialog.showModal()
    document.body.style.overflow = 'hidden'
    return () => { dialog.close(); document.body.style.overflow = overflow; if (trigger?.isConnected) trigger.focus() }
  }, [])
  return <dialog ref={dialogRef} className="object-dialog" aria-labelledby={titleId}
    onKeyDown={event => {
      if (event.key !== 'Tab') return
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], [tabindex="0"]')).filter(element => element.getClientRects().length > 0)
      if (!controls.length) return
      event.preventDefault()
      const current = controls.indexOf(document.activeElement as HTMLElement)
      controls[(current + (event.shiftKey ? -1 : 1) + controls.length) % controls.length].focus()
    }}
    onCancel={event => { event.preventDefault(); onClose() }}
    onClick={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className="object-dialog-inner">
      <header className="object-dialog-header"><div><span className="eyebrow">Explore in 3D · {object?.category ?? 'Object'}</span><h2 id={titleId}>{object?.name ?? requestedName ?? 'Unsupported object'}</h2></div>
        <button type="button" className="explore-close" aria-label="Close object explorer" onClick={onClose} autoFocus>×</button></header>
      {object ? <>
        <p className="explore-educational-note">An educational close-up, separate from the view through your eyes or in an uploaded photograph.</p>
        {identification && <p className="explore-photo-notice">Possible photo identification: {identification.name}{typeof identification.confidence === 'number' ? ` · model confidence ${Math.round(identification.confidence * 100)}%` : ''}. This viewer does not confirm that identification; model confidence is not a calibrated probability.</p>}
        <div className="object-dialog-layout">
          <div className="object-dialog-visual">
            <ViewerBoundary fallback={<Poster object={object} message="Interactive viewer unavailable. Showing the reference image." />}>
              <Suspense fallback={<Poster object={object} message="Preparing the 3D viewer…" />}><ModelViewer object={object} /></Suspense>
            </ViewerBoundary>
            <p className="explore-model-note">{object.modelNote}</p>
            {object.id === 'pleiades' && <div className="explore-members" aria-label="Cataloged cluster members">{clusterMembers.map(star => <span key={star.name}>{star.name}</span>)}</div>}
          </div>
          <aside className="object-dialog-details" aria-label="Object and observing information">
            <section><span className="eyebrow">About this object</span><p>{object.description}</p></section>
            <section className="explore-observing"><span className="eyebrow">Your selected sky</span><p className={`explore-availability tone-${availability.tone}`}>{availability.label}</p><p>{availability.detail}</p>
              <dl><div><dt>Time</dt><dd>{localTime(observation.time)}</dd></div><div><dt>Location</dt><dd>{observation.lat.toFixed(4)}, {observation.lon.toFixed(4)}</dd></div>
                {availability.rise && <div><dt>Rise</dt><dd>{localTime(availability.rise)}</dd></div>}{availability.set && <div><dt>Set</dt><dd>{localTime(availability.set)}</dd></div>}
                {conditions?.cloudCoverPercent !== undefined && <div><dt>Cloud cover</dt><dd>{conditions.cloudCoverPercent}%</dd></div>}
                {conditions?.bortle !== undefined && <div><dt>Approx. Bortle</dt><dd>{conditions.bortle}</dd></div>}</dl>
              {conditions?.cloudCoverPercent === undefined && <p className="explore-small">Cloud cover is unavailable for this location and time.</p>}
              {conditions?.bortle === undefined && <p className="explore-small">Sky brightness is unavailable for this location.</p>}
              {conditions?.source && <p className="explore-small">Conditions: {conditions.source}</p>}
            </section>
            <section><span className="eyebrow">At the telescope</span><p>{object.observingTip}</p></section>
            <figure className="explore-detail-reference"><img src={object.image} alt={object.imageAlt} loading="lazy" onError={event => { event.currentTarget.hidden = true }} /><figcaption>{object.imageCaption}</figcaption></figure>
            <footer className="explore-credits"><p>{object.modelCredit}</p><a href={object.source} target="_blank" rel="noreferrer">{object.sourceLabel} ↗</a>
              {object.id === 'pleiades' && <> · <a href="https://github.com/astronexus/HYG-Database/blob/main/hyg/README.md" target="_blank" rel="noreferrer">HYG catalog ↗</a></>}</footer>
          </aside>
        </div>
      </> : <div className="explore-unsupported"><h3>No supported model for this object yet</h3><p>Search the atlas for planets, the Moon, bright stars, Messier objects and WNY constellations.</p><button type="button" className="explore-button" onClick={onClose}>Back to objects</button></div>}
    </div>
  </dialog>
}
