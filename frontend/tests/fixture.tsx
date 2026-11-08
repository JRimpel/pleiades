import { createRoot } from 'react-dom/client'
import { ExploreIn3D } from '../src/explore'
import '../src/index.css'
const object = new URLSearchParams(location.search).get('object') || undefined
createRoot(document.getElementById('root')!).render(<ExploreIn3D observation={{ lat: 42.7, lon: -78.4, time: '2026-11-08T04:00:00Z' }} initialObjectId={object} photoIdentification={object === 'saturn' ? { name: 'Saturn', confidence: .86 } : undefined} />)
