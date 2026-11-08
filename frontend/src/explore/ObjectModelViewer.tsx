import { useEffect, useRef, useState } from 'react'
import type { ModelViewerElement } from '@google/model-viewer'
import type { CelestialObject } from './catalog'

function supportsWebGL() {
  try {
    const gl = document.createElement('canvas').getContext('webgl2')
    if (!gl) return false
    gl.getExtension('WEBGL_lose_context')?.loseContext()
    return true
  } catch { return false }
}

export function ReferenceImage({ object, caption = true }: { object: CelestialObject; caption?: boolean }) {
  const [failed, setFailed] = useState(false)
  return <figure className="explore-reference">
    {failed ? <div className="explore-image-missing">Reference image unavailable. Read the original source below.</div> :
      <img src={object.image} alt={object.imageAlt} onError={() => setFailed(true)} />}
    {caption && <figcaption>{object.imageCaption}</figcaption>}
  </figure>
}

export default function ObjectModelViewer({ object }: { object: CelestialObject }) {
  const host = useRef<HTMLDivElement>(null)
  const viewer = useRef<ModelViewerElement | null>(null)
  const [available] = useState(supportsWebGL)
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>( 'loading')
  const [referenceOnly, setReferenceOnly] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [rotating, setRotating] = useState(true)
  const [showLabels, setShowLabels] = useState(true)
  const [reduceMotion, setReduceMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const change = () => setReduceMotion(query.matches)
    query.addEventListener('change', change)
    return () => query.removeEventListener('change', change)
  }, [])

  useEffect(() => {
    if (!available || referenceOnly) return
    let disposed = false
    let element: ModelViewerElement | null = null
    const timer = window.setTimeout(() => { if (!disposed) setState('failed') }, 30000)
    const loaded = () => { window.clearTimeout(timer); if (!disposed) setState('ready') }
    const failed = () => { window.clearTimeout(timer); if (!disposed) setState('failed') }
    import('@google/model-viewer').then(({ ModelViewerElement: ViewerClass }) => {
      if (disposed || !host.current) return
      // Evict disconnected model resources instead of retaining every opened GLB.
      ViewerClass.modelCacheSize = 0
      element = document.createElement('model-viewer')
      element.setAttribute('alt', `Interactive educational view of ${object.name}. Drag or use the camera buttons to rotate.`)
      element.setAttribute('camera-controls', '')
      element.setAttribute('tabindex', '0')
      element.setAttribute('disable-pan', '')
      element.setAttribute('touch-action', 'pan-y')
      element.setAttribute('camera-orbit', object.cameraOrbit)
      element.setAttribute('min-camera-orbit', 'auto auto 35%')
      element.setAttribute('max-camera-orbit', 'auto auto 250%')
      element.setAttribute('interaction-prompt', 'none')
      element.setAttribute('loading', 'eager')
      element.setAttribute('reveal', 'auto')
      element.setAttribute('shadow-intensity', '0')
      element.autoRotate = true
      element.autoRotateDelay = 0
      element.setAttribute('rotation-per-second', '12deg')
      element.setAttribute('exposure', '1.1')
      element.addEventListener('load', loaded)
      element.addEventListener('error', failed)
      element.addEventListener('webglcontextlost', failed)
      for (const [index, label] of (object.labels ?? []).entries()) {
        const marker = document.createElement('span')
        marker.slot = `hotspot-star-${index}`
        marker.className = 'explore-star-label'
        marker.textContent = label.name
        marker.dataset.position = label.position.map(value => `${value}m`).join(' ')
        element.appendChild(marker)
      }
      // A rejected request is cached by model-viewer. A retry needs a fresh URL.
      element.src = attempt ? `${object.model}?retry=${attempt}` : object.model
      viewer.current = element
      host.current.appendChild(element)
    }).catch(failed)
    return () => {
      disposed = true; window.clearTimeout(timer)
      if (element) {
        element.autoRotate = false
        element.pause()
        element.removeEventListener('load', loaded)
        element.removeEventListener('error', failed)
        element.removeEventListener('webglcontextlost', failed)
        element.removeAttribute('src')
        element.remove()
      }
      viewer.current = null
    }
  }, [available, referenceOnly, object, attempt])

  useEffect(() => { if (viewer.current) viewer.current.autoRotate = rotating && state === 'ready' }, [rotating, state])
  useEffect(() => { viewer.current?.querySelectorAll<HTMLElement>('.explore-star-label').forEach(label => { label.hidden = !showLabels }) }, [showLabels, state])

  function rotate(delta: number) {
    const element = viewer.current
    if (!element) return
    element.autoRotate = false; setRotating(false)
    const orbit = element.getCameraOrbit()
    element.cameraOrbit = `${orbit.theta * 180 / Math.PI + delta}deg ${orbit.phi * 180 / Math.PI}deg ${orbit.radius}m`
    if (reduceMotion) element.jumpCameraToGoal()
  }
  function reset() {
    const element = viewer.current
    if (!element) return
    setRotating(false); element.autoRotate = false
    element.resetTurntableRotation()
    element.cameraOrbit = object.cameraOrbit
    element.fieldOfView = 'auto'
    if (reduceMotion) element.jumpCameraToGoal()
  }
  const fallback = !available || referenceOnly || state === 'failed'
  const ready = !fallback && state === 'ready'
  return <section className="explore-model-section" aria-label={`${object.name} viewer`}>
    <div className={`explore-stage ${ready ? 'is-ready' : ''}`}>
      {!ready && <div className="explore-stage-reference"><ReferenceImage object={object} caption={false} /></div>}
      {!fallback && <div className="explore-model-host" ref={host} />}
      <div className="explore-stage-label">{['saturn', 'jupiter'].includes(object.id) ? 'NASA 3D model' : 'Educational illustration'}</div>
      {!fallback && state === 'loading' && <p className="explore-stage-status" role="status">Loading interactive view…</p>}
      {fallback && <p className="explore-stage-status" role="status">{!available ? '3D is unavailable in this browser. Showing the reference image.' : state === 'failed' ? 'The 3D model could not load. Showing the reference image.' : 'Reference image view'}</p>}
    </div>
    <div className="explore-camera-controls" aria-label="3D camera controls">
      <button type="button" disabled={!ready} onClick={() => rotate(-20)} aria-label="Rotate view left">↶</button>
      <button type="button" disabled={!ready} onClick={() => rotate(20)} aria-label="Rotate view right">↷</button>
      <button type="button" disabled={!ready} onClick={() => { viewer.current?.zoom(2); if (reduceMotion) viewer.current?.jumpCameraToGoal() }} aria-label="Zoom in">+</button>
      <button type="button" disabled={!ready} onClick={() => { viewer.current?.zoom(-2); if (reduceMotion) viewer.current?.jumpCameraToGoal() }} aria-label="Zoom out">−</button>
      <button type="button" disabled={!ready} onClick={reset}>Reset view</button>
      <button type="button" disabled={!ready} aria-pressed={rotating} onClick={() => setRotating(value => !value)}>{rotating ? 'Pause rotation' : 'Resume rotation'}</button>
      {!!object.labels?.length && <button type="button" aria-pressed={showLabels} onClick={() => setShowLabels(value => !value)}>{showLabels ? 'Hide star labels' : 'Show star labels'}</button>}
      {available && <button type="button" onClick={() => { setReferenceOnly(value => state === 'failed' ? false : !value); setRotating(false); setState('loading'); setAttempt(value => value + 1) }}>{referenceOnly || state === 'failed' ? 'Try 3D view' : 'Use image'}</button>}
    </div>
    <p className="explore-camera-hint">{ready ? 'Drag to rotate · pinch or scroll to zoom · camera buttons also work with a keyboard.' : 'You can still explore the object facts, observing context and source image.'}</p>
  </section>
}
