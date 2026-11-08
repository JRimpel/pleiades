import { useState } from 'react'
import type { CelestialObject } from './catalog'

export default function ObjectThumbnail({ object }: { object: CelestialObject }) {
  const [failedSource, setFailedSource] = useState<string | null>(null)
  const source = object.thumbnail
  if (!source || failedSource === source) {
    return <div className="explore-thumbnail-fallback" role="img" aria-label={`${object.name} 2D thumbnail unavailable`}>
      <svg viewBox="0 0 120 90" aria-hidden="true"><ellipse cx="60" cy="45" rx="42" ry="16" transform="rotate(-25 60 45)" /><circle cx="60" cy="45" r="22" /><circle cx="92" cy="22" r="3" /><path d="M24 18v12m-6-6h12M96 60v10m-5-5h10" /></svg>
      <span>{object.name}</span>
      <small>{object.category}</small>
    </div>
  }
  return <img className="explore-object-thumbnail" src={source} alt={object.thumbnailAlt}
    width="400" height="300" loading="lazy" decoding="async" onError={() => setFailedSource(source)} />
}
