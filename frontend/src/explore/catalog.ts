import starCatalog from './star-catalog.json'
import expandedCatalog from './expanded-catalog.json'

export type ObjectCategory = 'Planet' | 'Moon' | 'Star' | 'Star cluster' | 'Star field' | 'Galaxy' | 'Nebula' | 'Constellation'
export interface CelestialObject {
  id: string
  name: string
  category: ObjectCategory
  subtitle: string
  description: string
  model: string
  image: string
  imageAlt: string
  thumbnail: string
  thumbnailAlt: string
  imageCaption: string
  modelCredit: string
  modelNote: string
  source: string
  sourceLabel: string
  cameraOrbit: string
  observingTip: string
  catalogPosition?: { raHours: number; decDeg: number }
  labels?: { name: string; position: number[] }[]
  partialFromWny?: boolean
}

const base = import.meta.env.BASE_URL + 'explore/'
const vega = starCatalog.stars.find(star => star.name === 'Vega')!
const members = starCatalog.stars.filter(star => star.name !== 'Vega')
export const clusterMembers = members
const objects: Omit<CelestialObject, 'thumbnail' | 'thumbnailAlt'>[] = [
  {
    id: 'saturn', name: 'Saturn', category: 'Planet', subtitle: 'A world framed by rings',
    description: 'Saturn is a gas giant surrounded by rings made of countless pieces of ice and rock. This NASA model lets you examine the planet and its ring system from different angles.',
    model: base + 'saturn.glb', image: base + 'saturn.jpg',
    imageAlt: 'Saturn and its rings in a Cassini spacecraft image',
    imageCaption: 'Spacecraft reference image · NASA/JPL-Caltech/Space Science Institute',
    modelCredit: '3D model: NASA Visualization Technology Applications and Development (VTAD)',
    modelNote: 'Educational close-up. Lighting, orientation and ring presentation are not synchronized to the selected observing time.',
    source: 'https://science.nasa.gov/saturn/', sourceLabel: 'NASA · Saturn', cameraOrbit: '25deg 65deg 110%',
    observingTip: 'A telescope is needed to resolve the rings. An above-horizon prediction alone does not guarantee a useful view.',
  },
  {
    id: 'jupiter', name: 'Jupiter', category: 'Planet', subtitle: 'Cloud bands on a giant world',
    description: 'Jupiter is the largest planet in our solar system. Bands in its atmosphere and the Great Red Spot reveal a world of changing clouds and storms. Explore its appearance with this NASA model.',
    model: base + 'jupiter.glb', image: base + 'jupiter.jpg', imageAlt: 'Jupiter with cloud bands against black space',
    imageCaption: 'Planet reference image · NASA', modelCredit: '3D model: NASA VTAD',
    modelNote: 'Educational close-up using NASA imagery. Clouds, rotation and lighting are not a live simulation.',
    source: 'https://science.nasa.gov/jupiter/', sourceLabel: 'NASA · Jupiter', cameraOrbit: '0deg 75deg 110%',
    observingTip: 'Binoculars may reveal some of Jupiter’s larger moons; a telescope is needed for finer detail. Conditions and equipment matter.',
  },
  {
    id: 'vega', name: 'Vega', category: 'Star', subtitle: 'A bright point in Lyra',
    description: 'Vega is a bright star in the constellation Lyra and a corner of the Summer Triangle. Explore an enlarged blue-white stellar illustration with surface variation and a soft luminous halo.',
    model: base + 'vega-illustration.glb', image: base + 'vega.svg', imageAlt: 'Illustration of a blue-white star, not a resolved photograph of Vega',
    imageCaption: 'Original star illustration · Pleiades · CC BY 4.0', modelCredit: 'Original 3D star illustration: Pleiades · CC BY 4.0',
    modelNote: 'Illustration only. The apparent surface, colors and size are not resolved measurements of Vega.',
    source: 'https://science.nasa.gov/solar-system/skywatching/night-sky-network/summer-triangle-corner-vega/',
    sourceLabel: 'NASA · Vega', cameraOrbit: '0deg 75deg 110%',
    observingTip: 'Vega appears as a point of light to the unaided eye. This enlarged model does not represent its apparent size in the sky.',
    catalogPosition: { raHours: vega.ra_hours, decDeg: vega.dec_deg },
  },
  {
    id: 'pleiades', name: 'Pleiades', category: 'Star cluster', subtitle: 'Meet the namesake of our map',
    description: 'The Pleiades, also called Messier 45, is an open star cluster in Taurus. This scene places nine named members according to their cataloged angular positions and adds enhanced blue reflection-nebula clouds. Cloud depth is illustrative.',
    model: base + 'pleiades.glb', image: base + 'pleiades.jpg', imageAlt: 'Infrared WISE image of the Pleiades star cluster and surrounding dust',
    imageCaption: 'Infrared reference image · NASA/JPL-Caltech/UCLA · WISE',
    modelCredit: 'Angular coordinates: David Nash / Astronexus HYG v4.0 · CC BY-SA 4.0; adapted by Pleiades',
    modelNote: 'Catalog-based angular layout, J2000. Depth is schematic and star radii are enlarged. This is not a measured 3D reconstruction.',
    source: 'https://science.nasa.gov/photojournal/seven-sisters-get-wise/', sourceLabel: 'NASA · Pleiades / WISE',
    cameraOrbit: '0deg 90deg 110%', observingTip: 'Binoculars give a wider view of the cluster. The infrared reference reveals dust that will not look like this to the unaided eye.',
    catalogPosition: { raHours: members.reduce((sum, star) => sum + star.ra_hours, 0) / members.length,
      decDeg: members.reduce((sum, star) => sum + star.dec_deg, 0) / members.length },
  },
  {
    id: 'andromeda', name: 'Andromeda Galaxy', category: 'Galaxy', subtitle: 'Beyond our own Milky Way',
    description: 'Andromeda, or Messier 31, is a nearby large galaxy. This illustrative spiral scene introduces the idea of a disk with a brighter central region; the accompanying NASA image is an actual ultraviolet observation.',
    model: base + 'andromeda-illustration.glb', image: base + 'andromeda.jpg',
    imageAlt: 'Ultraviolet GALEX observation of the Andromeda Galaxy',
    imageCaption: 'Ultraviolet reference image · NASA/JPL-Caltech · GALEX',
    modelCredit: 'Original illustrative spiral: Pleiades · CC BY 4.0. Reference: NASA/JPL-Caltech.',
    modelNote: 'Illustrative spiral only. Star positions, arm structure, depth and scale are not reconstructed measurements of Andromeda.',
    source: 'https://science.nasa.gov/photojournal/andromeda/', sourceLabel: 'NASA · Andromeda / GALEX',
    cameraOrbit: '0deg 45deg 110%', observingTip: 'Dark skies and binoculars can help. Long-exposure and ultraviolet imagery show detail and colors that are not an unaided-eye view.',
    catalogPosition: { raHours: .712, decDeg: 41.269 },
  },
  ...expandedCatalog.map(object => ({ ...object, category: object.category as ObjectCategory,
    model: base + object.model, image: base + object.image })),
]

export const catalog: CelestialObject[] = objects.map(object => ({
  ...object,
  thumbnail: `${base}thumbnails/${object.id}.svg`,
  thumbnailAlt: `2D preview of ${object.name}`,
}))

export function findObject(id: string) {
  return catalog.find(object => object.id === id || object.name.toLowerCase() === id.toLowerCase())
}
