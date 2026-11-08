import { createRoot } from 'react-dom/client'
import { useState } from 'react'
import { ExploreIn3D } from '../src/explore'
import '../src/index.css'
const object = new URLSearchParams(location.search).get('object') || undefined
export function Fixture() {
  const [observation, setObservation] = useState({ lat: 42.7, lon: -78.4, time: '2026-11-08T04:00:00Z' })
  return <ExploreIn3D observation={observation} onObservationChange={setObservation} initialObjectId={object} photoIdentification={object === 'saturn' ? { name: 'Saturn', confidence: .86 } : undefined} />
}
createRoot(document.getElementById('root')!).render(<Fixture />)
