# Explore in 3D: current integration handoff

Updated November 8, 2026 (America/New_York). This is the current guide for the atlas, thumbnails, visibility sorting and viewer. It replaces the original five-object/standalone-only directions.

Documentation validation covers local links, command/script paths, code fences and catalog/test counts. The current filter implementation passed the application checks recorded below; the earlier documentation-only validation is historical.

The implementation and documentation are present in the working tree; this task has not committed or deployed them. Include untracked runtime assets, generated metadata, new components/scripts/tests and their manifests when preparing an integration commit. Use `git status --short --untracked-files=normal` rather than relying only on `git diff`.

Read [project integration](../INTEGRATION_HANDOFF.md) for API/database startup and map wiring, [frontend documentation](../frontend-documentation.md) for the surrounding UI, and [AI/ML handoff](../AI_ML_HANDOFF.md) for scoring and backend astronomy ownership.

## Current behavior and accepted decisions

| Area | Implemented behavior |
| --- | --- |
| Coverage | 263 objects: 73 constellations, 7 planets other than Earth, the Moon, 72 named stars, 55 clusters, 3 star fields/asterisms, 40 galaxies and 12 nebulae |
| Messier targets | All 110; M31 uses ID `andromeda`, M45 uses `pleiades` |
| Visual style | Detailed educational geometry with enhanced nebula colors/clouds; schematic depth, not measured volumetric reconstruction |
| Planet/Moon models | Existing NASA Jupiter/Saturn; NASA LRO/LROC lunar surface texture; other new planetary surfaces are procedural |
| Constellations | Catalog angular patterns, connecting lines, enlarged color-coded stars, toggleable named-star/nebula labels; appropriate Messier nebulae also appear in constellation scenes |
| Rotation | Starts automatically at 12 degrees/second with no startup delay, including reduced-motion mode, per explicit user preference; Pause / Resume is always available |
| Thumbnails | Dedicated, self-contained 400 x 300 SVG for every object; lazy card images, independent of detail reference images and GLBs |
| Default order | Visibility: above horizon first, unknown next, below horizon last; Name (A–Z) is optional |
| Browsing | Search, category filters, optional Visible tonight switch (off initially), 24-card batches and Show more; filters and sort apply before pagination |
| Shared context | Selected spot/cell, then valid WNY GPS, then region center; selected forecast time follows the map |
| Dependencies | Existing Flask sky endpoint and local assets; no Gemini, score calculation or photo service required to open models |

Coverage is year-round. The constellation filter includes regions whose J2000 boundary reaches declination greater than -48 degrees: a northern portion can rise from WNY's southern edge at 42 N. Partial southern figures are marked. Bright named stars use HYG visual magnitude <= 2.5 and declination > -48; the Sun is excluded. This is the selected observing catalog, not every detectable star or deep-sky object.

## Integration entry points

Import public feature exports from `src/explore/index.ts`:

```tsx
import { ExploreIn3D, ObjectExplorerModal, catalog, findObject } from './explore'
import type {
  ObservationContext, ObservingConditions, PhotoIdentification, CelestialObject,
} from './explore'
```

The app already mounts the explorer below its full-height map. Preserve that arrangement and reuse `src/lib/observingContext.ts` rather than introducing another location/time state.

```tsx
// Within a parent component; derive these from shared map/forecast state.
const observation: ObservationContext = {
  lat: 42.7,
  lon: -78.4,
  time: '2026-11-08T04:00:00Z',
}
const conditions: ObservingConditions = {
  cloudCoverPercent: 20,
  bortle: 4,
  source: 'Selected spot forecast and static light-pollution estimate',
}

<ExploreIn3D
  observation={observation}
  conditions={conditions}
  contextLabel="Selected map spot"
  hideControls
/>
```

| Prop | Contract |
| --- | --- |
| `observation?` | `{ lat: number; lon: number; time: string }`; use an ISO timestamp with UTC Z or an explicit offset |
| `onObservationChange?` | `(context: ObservationContext) => void`; required if a parent-controlled standalone form should edit shared state |
| `hideControls?` | Hides the standalone coordinate/time form and displays the selected-context caption |
| `contextLabel?` | Human-readable context origin, e.g. Selected map spot |
| `conditions?` | `{ cloudCoverPercent?: number; bortle?: number; source?: string }`; cloud cover is percent, not a 0–1 fraction |
| `initialObjectId?` | Opens an object at mount; later prop changes do not change selection |
| `photoIdentification?` | `{ name: string; confidence?: number }`; confidence is displayed as a fraction converted to percent, with explicit uncertainty |

Without `observation`, the feature owns internal context. With `observation` but no callback, it is read-only. Validation accepts latitude 42 through 43.4 and longitude -79.8 through -77, with a parseable timestamp; invalid context shows an error. Use timezone-qualified timestamps even though the parser itself accepts any parseable date.

`resolveObservingContext(time, cellId, spot, scores, location)` returns `{ observation, conditions, label }`. Priority: matching selected spot, selected score-cell center, in-coverage GPS, WNY center (42.7, -78.4). Navigation/panning bounds extend farther and must not be used as observing coverage. Weather/Bortle details are passed only when spot ID, coordinates and forecast hour match; stale cached weather is omitted.

For later photo or controlled-modal integration:

- `findObject` accepts a stable ID or case-insensitive full display name. Messier aliases are not generally resolved; translate M31/M45 to the existing IDs.
- `initialObjectId` initializes selection once. Re-key the explorer for a new initial selection, or control the exported `ObjectExplorerModal` directly.
- Direct modal props are `object` (possibly undefined), `observation`, `availability`, `onClose`, and optional `requestedName`, `conditions`, `identification`.
- Import `availabilityFor` and the `Availability` type directly from `./explore/astronomy`; they are not barrel exports.
- Unknown objects show an unsupported state. The explorer passes photo metadata only when its name matches the selected object's display name (case-insensitive). A possible photo match is not confirmation, and provider confidence is not a calibrated probability.

## Visibility and API contract

The existing endpoint is:

```text
GET /api/sky-events?lat=42.7&lon=-78.4&date=2026-11-07
```

`date` is the America/New_York night-start date: before local noon use the preceding local date. Use `nightDate`; do not derive it by slicing the UTC timestamp. The hook reuses a response for hour changes within one local night, cancels superseded requests, times out after 10 seconds, and rejects mismatched date/location responses.

The frontend consumes these existing response fields:

```ts
{
  date: string; lat: number; lon: number;
  twilight: {
    sunset: string | null; astronomical_dusk: string | null;
    astronomical_dawn: string | null; sunrise: string | null;
  };
  moon: {
    illumination: number; phase_name: string;
    rise: string | null; set: string | null;
  };
  planets: {
    name: string; rise: string | null; set: string | null;
    max_alt_deg: number | null;
  }[];
}
```

Additional backend fields are allowed. No new endpoint, database schema, scoring seam or AI contract was introduced by the atlas work.

- Fixed stars, clusters, galaxies, nebulae and constellation centers use `catalogPosition: { raHours, decDeg }` and `catalogAltitude` to estimate geometric altitude at the selected time/location. These estimates continue when the API is unavailable.
- The implementation uses approximate mean sidereal time and spherical altitude. UTC approximates UT1; precession, nutation, proper motion and atmospheric refraction are omitted. Formula references: [USNO sidereal time](https://aa.usno.navy.mil/faq/GAST), [USNO altitude](https://aa.usno.navy.mil/faq/alt_az).
- Constellation availability describes its catalog center. Parts of the extended figure can be on either side of the horizon.
- Planets/Moon use matched local-night rise/set crossings. Missing/identical/unparseable crossings, unlisted planets, stale responses or API failure remain unknown. The nightly maximum altitude is not the selected-hour altitude.
- `Availability` adds optional `aboveHorizon: boolean | null` and `altitudeDeg: number` to the existing label/detail/tone/rise/set fields. Missing or null horizon state sorts as unknown.
- `sortByVisibility` returns a new array. It groups above / unknown / below, then uses descending altitude where available (missing altitude sorts after computed altitudes within that group), then numeric-aware English name order and ID. It does not mutate `catalog`.
- The UI recomputes sorting for selected context and sky-summary changes, before the 24-item slice. Do not sort only the displayed page or use label text/color as a data contract.

### Visible tonight filter

The accessible **Visible tonight** switch defaults off and is independent of category, search and sort. When enabled, only objects for which `visibleTonightFor(object, context, summary) === true` remain. It resets the displayed count to 24 and filters the full collection before sorting/pagination. Toggle state persists across observing context changes and results recalculate for the new location/night.

This means estimated above the horizon **sometime during the selected local night**, not necessarily at the slider hour. Card statuses and default visibility sorting still describe the selected hour. `observingNightWindow(context, summary)` returns epoch-millisecond `{ start, end }` for a valid matched astronomical-dusk/dawn pair; if incomplete it tries sunset/sunrise. It rejects stale coordinates/date, invalid timestamps, reversed/overlong intervals and an interval belonging to another local night. These helpers are direct exports from `explore/astronomy`, not barrel exports.

For fixed objects, the filter checks both endpoints and whether an upper transit falls inside the interval, including brief southern arcs with below-horizon endpoints. Planets/Moon require usable rise/set crossings and an overlap with the window; a rise exactly at dawn or a set exactly at dusk does not establish a positive observing interval. No matched window, missing coordinates, unlisted planets or incomplete crossing data returns unknown (`null`), which is excluded. While night data are loading/unavailable, the enabled filter explains the missing information and shows no matches; turning it off restores normal browsing, including offline fixed-object estimates. Above-horizon remains a geometric estimate, subject to weather, daylight fallback twilight, equipment, brightness and terrain.

An above-horizon estimate is not guaranteed observability. Weather, daylight, terrain, brightness and equipment still matter. Exact ephemeris-based fixed-object positions and selected-time planetary altitudes remain future work.

## Viewer lifecycle and controls

Opening an object lazy-loads the viewer/library and its GLB. Merely browsing thumbnails fetches no GLBs. WebGL2 unavailable, failed assets, timeout or library failure shows the detail reference image; the user can switch to image mode and retry 3D with a fresh query-string URL.

- Auto-rotation is on for each newly opened model. Left/right camera buttons and Reset pause it. Pointer dragging does not set the pause state; use Pause rotation to stop it.
- Reduced motion still snaps programmatic camera changes and removes card transitions. It does not suppress automatic turntable rotation, per the user's explicit instruction.
- Reset restores camera orbit/FOV and turntable orientation. Image mode/retry leaves rotation paused until resumed.
- Modal close/Escape/backdrop restores opener focus and body scroll. Tab cycling remains inside the dialog. Escape closes a 3D dialog before the underlying spot panel.
- Teardown disables rotation, pauses animation, detaches listeners, clears the source, removes the element and disables the model cache. Preserve cleanup when changing the renderer.
- `labels[].position` is a local GLB-space coordinate in metres for model-viewer hotspots. It is separate from celestial RA/declination and must not be used for visibility.

## Files and boundaries

Paths below are relative to `frontend/`, except the map bridge reference.

| Path | Responsibility |
| --- | --- |
| `src/App.tsx`, `src/lib/observingContext.ts` | Shared map/forecast context and matching conditions |
| `src/explore/ExploreIn3D.tsx` | Search, category, sort, pagination and selected object |
| `src/explore/catalog.ts` | Types, original five records, merged generated records, thumbnail URLs and lookup |
| `src/explore/expanded-catalog.json` | Generated expanded metadata; edit its generator instead of hand-editing this file |
| `src/explore/star-catalog.json` | Original HYG member subset used by Vega/Pleiades |
| `src/explore/astronomy.ts` | Context validation, local night, horizon estimates and sorting |
| `src/explore/useNightSummary.ts` | Existing API request lifecycle and context validation |
| `src/explore/ObservationControls.tsx` | Optional standalone UTC coordinate/time form |
| `src/explore/ObjectThumbnail.tsx` | Lazy 2D image and accessible failure fallback |
| `src/explore/ObjectExplorerModal.tsx` | Dialog, object facts, observing context and credits |
| `src/explore/ObjectModelViewer.tsx` | Model-viewer, rotation/camera controls, labels and cleanup |
| `src/explore/explore.css` | Feature styles, responsive layouts and focus indicators |
| `public/explore/` | Runtime GLBs, reference images, SVG illustrations and provenance |
| `public/explore/thumbnails/` | 263 standalone card SVGs plus manifest |
| `scripts/prepare-explore-assets.py` | Original downloads, HYG subset and base schematic generation |
| `scripts/expand-explore-assets.py` | Expanded catalog/models, improved base models and lunar texture |
| `scripts/prepare-explore-thumbnails.py` | Complete dedicated 2D thumbnail set |
| `scripts/verify-explore-assets.py` | Coverage, SVG, finite-coordinate and GLB buffer/index validation |

## IDs, assets and extension workflow

Stable IDs are part of integration: `saturn`, `jupiter`, `vega`, `pleiades`, `andromeda`; new planets/Moon use lowercase names; other Messier targets use `m1` through `m110`; constellations use `constellation-<three-letter-code>`; new named stars use `star-<slug>`.

`catalog.ts` prefixes models/images with `import.meta.env.BASE_URL + 'explore/'`. Card thumbnails always use `thumbnails/<object-id>.svg`. Model filenames can differ from IDs (`vega-illustration.glb`, `andromeda-illustration.glb`); use the metadata, not guessed filenames. `thumbnail/thumbnailAlt` are separate from `image/imageAlt/imageCaption`; do not overwrite scientific reference imagery to change card art.

To add/change an object:

1. Change original-five metadata in `catalog.ts`, or expanded generation in `expand-explore-assets.py`. Keep IDs unique/stable and add a valid catalog position for fixed-object estimates.
2. Supply model, reference/illustration, source, credit, model limitations, camera orbit and observing guidance. Label procedural/color-enhanced material honestly.
3. Update `prepare-explore-thumbnails.py` if changing original-five metadata or introducing a category/rendering style. It contains a small original-five record list separate from the expanded JSON.
4. Run the generators in the order below; running original prep alone overwrites the improved Vega/Pleiades/Andromeda models with earlier schematics.
5. Run verification and relevant browser checks. Coverage assertions currently expect 263 objects and 73 constellations; update counts deliberately if the selected catalog changes.
6. Include generated runtime assets/metadata, thumbnail manifest and provenance/licenses with the source change. Download caches, node_modules, dist, test-results and secrets are not integration artifacts.

From repository root, with standard-library Python:

```powershell
python frontend/scripts/prepare-explore-assets.py
python frontend/scripts/expand-explore-assets.py
python frontend/scripts/prepare-explore-thumbnails.py
python frontend/scripts/verify-explore-assets.py
```

Normal app startup uses the shipped local assets and does not need regeneration. Regeneration downloads missing NASA/HYG/d3-celestial sources, requires network access if caches are absent, and uses `frontend/scripts/.cache/`. The source catalogs come from upstream URLs; preserve source manifests and recheck upstream changes when refreshing.

Attribution: keep [asset attribution](public/explore/ATTRIBUTION.md), `sources.json`, `atlas-credits.json`, `d3-celestial-LICENSE.txt` and thumbnail manifest. HYG-derived layouts retain CC BY-SA 4.0 attribution/share-alike; d3-celestial includes its BSD license; original illustrations use CC BY 4.0. NASA assets retain item-specific credit and [NASA media guidance](https://www.nasa.gov/nasa-brand-center/images-and-media/). Nebula clouds, stellar surface detail, galaxy arms/depth and new procedural planetary surfaces are educational; the lunar texture is [NASA SVS CGI Moon Kit](https://svs.gsfc.nasa.gov/4720/).

## Setup, verification and troubleshooting

From repository root:

```powershell
Set-Location frontend
# Stop an existing Vite process before npm ci on Windows to avoid native-file locks.
npm ci
npm run dev
```

Run Flask separately on 5001; see the project handoff. Vite proxy precedence is `API_PROXY_TARGET`, then `PLEIADES_DEV_API_TARGET`, then `http://127.0.0.1:5001`. Restart Vite after changing those variables. Production requests remain same-origin `/api`, with nginx/Gunicorn internally on 8000.

Latest application verification, including Visible tonight, November 8, 2026:

| Command / working directory | Recorded result |
| --- | --- |
| `npm run build` / frontend | Passed; existing large-bundle advisory |
| `npm run test:unit` / frontend | 10 passed |
| `npm run test:browser -- visible-tonight.spec.ts visibility-sort.spec.ts explore.spec.ts integration.spec.ts thumbnails.spec.ts` / frontend | 17 passed |
| `python frontend/scripts/verify-explore-assets.py` / repo root | Passed; all models, full Messier coverage and 263 thumbnails |
| `git diff --check` | Passed; Windows line-ending notices are informational |

Browser breakdown: 7 explorer, 3 map/API integration, 2 thumbnail, 2 sorting and 3 Visible tonight checks. They cover actual rotation/pause/resume, real GLBs, mobile/focus, fallback/retry, shared coordinates/time, all thumbnail decoding with no GLB requests, default visibility order, context-time updates and sorting before pagination/filtering. Ten unit checks cover DST/night dates, rise/set, stale contexts, invalid inputs, altitude geometry, non-mutating grouping, Moon/planet availability, matched night windows/fallbacks, brief fixed-object transits and night-overlap boundaries. Lint passed during an earlier integration pass; it was not rerun for the latest atlas/sorting changes. These fixture-based browser tests do not prove current live database, Gemini, storage or deployment availability.

If Chromium is missing, from `frontend/`:

```powershell
npm run test:browser:install
npm run test:browser -- visible-tonight.spec.ts visibility-sort.spec.ts explore.spec.ts integration.spec.ts thumbnails.spec.ts
```

Playwright uses project-local `node_modules/.cache/playwright/` and starts a Vite test server at 127.0.0.1:4173. Free that port before testing; the configuration does not reuse another server. Screenshots/traces are ignored under `frontend/test-results/`. Desktop/mobile screenshots, including the new thumbnail grid and lunar/nebula scenes, were visually reviewed. The blocked-asset test deliberately logs a failed fetch. Existing Lit development, missing `circle-11` map-sprite and large-bundle warnings remain. A sandboxed run once stalled during process teardown; the final normally permitted browser run exited successfully.

Score proxy `ECONNREFUSED` means Flask is not listening at the proxy target. A structured 503 `database_unavailable` means the API is reachable but its configured database is not. Inspect `/api/scores/range` and `/api/scores`; health can be degraded only because photo storage is unconfigured. A missing thumbnail requires checking its stable-ID file/manifest; a missing model requires checking `object.model`, not its thumbnail URL.

## Remaining integration work

Exact ephemeris-based fixed-object positions, selected-time planetary altitudes, physical phase/orientation synchronization, real volumetric reconstructions, real-handset GPU/touch verification, photo upload/voting and end-to-end storage/vision, and deployment remain outside this implementation. Preserve the working score model/API contracts when extending the explorer.
