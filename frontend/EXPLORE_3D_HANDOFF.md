# Explore in 3D — frontend handoff

Updated November 8, 2026. Work is confined to `frontend/`.

## User decisions and scope

- Six or more hours available.
- Polished planets and stars, with simpler clusters and galaxies.
- Keep this feature separate from map selection for now; expose an integration interface.

Read `Architecture.md`, `backend-documentation.md`, `AI_ML_HANDOFF.md`, the actual sky route/types, and the existing frontend before implementation. No backend endpoints, schemas, or shared contracts were changed.

## Implemented

- Separate Explore section below the existing map, with its own WNY latitude/longitude and UTC time controls and an America/New_York time preview.
- Five object cards: Saturn, Jupiter, Vega, Pleiades (correctly labeled a star cluster), and Andromeda Galaxy.
- Responsive native-dialog viewer with rotation, zoom, reset, optional auto-rotation, keyboard camera buttons, Escape/backdrop/close behavior, focus restoration, and body scroll locking.
- Lazy viewer/library loading; GLBs load only after an object is opened. Model cache is disabled, disconnected elements are removed, rotation/animation is stopped, and source references are cleared on teardown.
- User-selectable reference image mode plus loading, failed-asset, unavailable-WebGL, unsupported-object, failed-reference-image and viewer-library-failure views.
- Reduced-motion preference disables automatic rotation and snaps programmatic camera changes.
- Sourced descriptions, equipment guidance, model/image credit, educational-view labels, and optional uncertain-photo-identification text.
- Existing `/api/sky-events` integration, request cancellation/timeout and stale-context protection. No Gemini dependency.

## Files

| Path | Purpose |
|---|---|
| `src/explore/ExploreIn3D.tsx` | Standalone feature and object selection/filtering |
| `src/explore/ObservationControls.tsx` | Independent observing-context form |
| `src/explore/ObjectExplorerModal.tsx` | Accessible dialog, educational content, observing context, credits |
| `src/explore/ObjectModelViewer.tsx` | Lazy model-viewer registration, camera controls, teardown and reference fallbacks |
| `src/explore/catalog.ts` | Supported objects, source links, representations and observing guidance |
| `src/explore/star-catalog.json` | Bundled HYG coordinate subset, mirrored from the public attribution copy by the generator |
| `src/explore/astronomy.ts` | Existing-response validation, local-night dates and conservative rise/set estimates |
| `src/explore/useNightSummary.ts` | Abortable, timeout-bounded existing API fetch |
| `src/explore/explore.css` | Scoped dark-theme and mobile styles |
| `src/explore/index.ts` | Reusable component/type exports |
| `public/explore/` | Local models, reference images, coordinate subset and source manifest |
| `scripts/prepare-explore-assets.py` | Reproducible asset download and schematic GLB generation; standard-library Python |
| `tests/astronomy.test.ts` | Date/DST, event, stale-response and invalid-context checks |
| `tests/browser/explore.spec.ts` | Real rendering, mobile, focus, reduced motion, context and failure checks |
| `tests/fixture.html`, `tests/fixture.tsx` | Development/test integration fixture; not an application build entry |
| `playwright.config.ts`, `scripts/install-browser.mjs` | Browser verification with project-local Chromium |

`src/App.tsx` mounts `<ExploreIn3D />` after the map. The existing map constructor-failure handler had a pre-existing lint error; its state update is now queued and canceled on unmount. Map navigation/reset behavior was preserved. `vite.config.ts` now proxies the existing `/api` namespace to `http://127.0.0.1:5000` in development; `PLEIADES_DEV_API_TARGET` can override that development target. Production remains same-origin `/api`.

## Integrate with shared map/time state later

```tsx
import { ExploreIn3D } from './explore'
import { useState } from 'react'
import type { ObservationContext } from './explore'

// Inside the parent component. Timestamp includes UTC Z or an explicit offset.
const [observingContext, setObservingContext] = useState<ObservationContext>({
  lat: 42.7,
  lon: -78.4,
  time: '2026-11-08T04:00:00Z',
})

<ExploreIn3D
  observation={observingContext}
  onObservationChange={setObservingContext}
  hideControls
  conditions={{ cloudCoverPercent: 20, bortle: 4, source: 'selected spot forecast' }}
/>
```

When `observation` is supplied, the parent owns it. Without a callback, shared context is displayed read-only. Without the prop, the explorer uses internal state; changing it does not move the map. Supplied invalid/out-of-WNY context displays an error instead of fetching misleading astronomy.

For photo integration, `ObjectExplorerModal`, `catalog`, `findObject` and the context/identification types are exported. A parent can open a supported object with `identification={{name, confidence}}`; the dialog describes it as a possible identification and never treats model confidence as a calibrated probability. `ExploreIn3D` also accepts `initialObjectId` and `photoIdentification` for an initially opened object. Re-key the component for a new initial selection, or use the exported modal for ongoing controlled selection. Unknown objects show an explicit unsupported state.

## Honest astronomy behavior and backend needs

- Existing endpoint: `GET /api/sky-events?lat=...&lon=...&date=YYYY-MM-DD`.
- `date` is the New York local night-start date. Before local noon it is the previous date; DST transitions are handled through Intl time-zone formatting.
- The endpoint returns a nightly planet list and rise/set events, **not exact altitude/azimuth at the selected instant**.
- When both rise and set crossings are provided, the UI estimates above/below horizon at the selected time and labels it “estimated.” Incomplete crossings are shown as nightly listing only. Omission from the list is not treated as exact selected-time invisibility.
- Vega, Pleiades and Andromeda explicitly show **“Visibility not calculated”**. Their static models can still be explored. No fixed “visible tonight” claims are used.
- Backend failure, timeout, stale date, or mismatched coordinates results in unknown visibility, not fabricated conditions.
- Weather/Bortle context is displayed only if the parent supplies it; standalone mode says it has not been checked.
- Future Role B/C integration: provide a coordinated exact-time object-position response containing canonical name, altitude/azimuth, computation time/location/source, and uncertain photo provenance. No new route was invented here.

## Assets, science and attribution

`public/explore/sources.json` records original URLs, NASA model checksums, credits and generated-model provenance. All runtime model/image requests are same-origin local files. No decoder CDN is required by the shipped GLBs.

- Saturn GLB: unchanged [NASA VTAD model](https://science.nasa.gov/resource/saturn-3d-model/), about 5.5 MB. Reference from [NASA Saturn](https://science.nasa.gov/saturn/), Cassini image credited to NASA/JPL-Caltech/Space Science Institute.
- Jupiter GLB: unchanged [NASA VTAD model](https://science.nasa.gov/resource/jupiter-3d-model/), about 11.5 MB. Reference from [NASA Jupiter](https://science.nasa.gov/jupiter/). These are educational close-ups, not time-synchronized cloud, lighting, ring-orientation, or rotation simulations.
- Vega: original schematic blue-white sphere/gradient and SVG poster, CC BY 4.0. It is **not** a resolved surface image. [NASA educational source](https://science.nasa.gov/solar-system/skywatching/night-sky-network/summer-triangle-corner-vega/).
- Pleiades: nine named members from [HYG v4.0](https://github.com/astronexus/HYG-Database/blob/main/hyg/README.md), David Nash/Astronexus, **CC BY-SA 4.0**. Angular layout uses J2000 RA/declination. Displayed depth and enlarged radii are schematic; no parallax reconstruction is claimed. Coordinate subset and derived GLB are CC BY-SA 4.0; preserve attribution, change notice, and share-alike terms. [WISE reference](https://science.nasa.gov/photojournal/seven-sisters-get-wise/) is infrared, NASA/JPL-Caltech/UCLA.
- Andromeda: original procedural illustrative spiral, CC BY 4.0. Its arms, stars, depth and scale are not measured Andromeda geometry. [GALEX reference](https://science.nasa.gov/photojournal/andromeda/) is ultraviolet, NASA/JPL-Caltech. Both representation and wavelength are labeled in the UI.
- NASA media use: [official guidance](https://www.nasa.gov/nasa-brand-center/images-and-media/). Acknowledge NASA and item-specific credits; no endorsement is implied. No NASA logos were added.
- `@google/model-viewer`: Apache 2.0; its renderer dependency Three.js is MIT. Keep package license notices with distribution.

Regenerate assets from repository root:

```powershell
python frontend/scripts/prepare-explore-assets.py
```

Raw HYG catalog cache stays under ignored `frontend/scripts/.cache/`; only the ten-star subset and generated runtime files are shipped. The generator does not edit downloaded NASA imagery or models. The Vega/galaxy schematics are code-native geometry, not AI-generated photographs.

## Setup and checks

From `frontend/`:

```powershell
npm install
npm run dev
npm run build
npm run lint
npm run test:unit
npm run test:browser:install
npm run test:browser
```

The browser install uses ignored `node_modules/.cache/playwright/`. Browser checks use a mocked existing astronomy response and real local GLBs; no DB or Gemini key is needed. Test-only unknown/photo states use `tests/fixture.html`, which is not part of the production build. Screenshots/traces are under ignored `test-results/`.

Verification completed November 8, 2026:

- `npm run build`: passed; TypeScript and production bundling succeeded.
- `npm run lint`: passed.
- `npm run test:unit`: **4 passed** (DST/night date, rise/set, stale/incomplete summaries, invalid context).
- `npm run test:browser`: **6 passed**, Chromium with software WebGL, about 30 seconds in the final run. Real local GLBs rendered for all five objects. Assertions verify camera angle changes, zoom changes, reset, Saturn pointer-drag rotation, no GLB requests before opening, no remaining model-viewer after closing, and focus restoration.
- Mobile checks: 390×844 viewport, reduced motion, keyboard focus containment, scroll lock, no horizontal overflow. Desktop screenshots: 1440×1000. Visually reviewed all five desktop views plus the top and lower content of the mobile Pleiades dialog.
- Failure checks: blocked GLB request shows its reference image, retry successfully renders; WebGL disabled + astronomy HTTP 503 still allows educational exploration; unsupported objects and uncertain photo identification have explicit states.
- Existing API mock verifies updated coordinates and correct local-night date. These tests do **not** establish live backend availability or scientifically validate an exact-time position engine.
- `git diff --check`: passed (only pre-existing Windows line-ending notices outside this frontend change).

Screenshots include `test-results/saturn-desktop.png`, `jupiter-desktop.png`, `vega-desktop.png`, `pleiades-desktop.png`, `andromeda-galaxy-desktop.png`, `pleiades-mobile-top.png` and `pleiades-mobile.png`. They are ignored local QA artifacts, regenerated by browser tests. The expected failed-fetch console error in the blocked-asset test is intentional. Development builds also log model-viewer/Lit warnings and the existing map's missing `circle-11` sprite warning.

## Limits and operational notes

- Largest assets are the unchanged NASA planet models; only the opened object downloads its GLB. Future optimization can reduce texture resolution/mesh size with visual comparison against the originals.
- Existing map bundle is already large. New renderer is a separate lazy chunk (~291 KB gzip at the first build), not part of the initial map bundle. Vite reports its standard large-chunk warning.
- Installation audit reported ten moderate advisories in the existing ESLint/TypeScript-ESLint/minimatch development-tool chain; no high/critical advisory was reported. A forced major-version audit fix was not applied as part of this feature.
- Browser tests verify representative desktop/mobile sizes in Chromium, not every device. Model-viewer provides touch rotation/pinch controls; physical touch/pinch and actual handset GPU limits should still be checked before the demo.
- Live backend availability and exact-time object data remain integration work. Educational exploration remains functional when the astronomy API is down.

## Work log

- Inspected docs/frontend and obtained user decisions before expanding beyond planet MVP.
- Baseline build passed; baseline lint failed in the map constructor error handler. Fixed that small existing issue.
- Added local NASA GLBs/reference images, verified HYG subset, and generated transparent schematic star/cluster/galaxy representations.
- Added standalone UI, reusable interfaces, API-state handling, native dialog and lazy model lifecycle.
- Browser checks found a cached rejected GLB request during retry and focus escaping at the end of the tab sequence. Added a fresh local retry URL, explicit dialog tab cycling, and opener capture before autofocus. Retested successfully.
- Moved the imported catalog subset into `src/explore/` to remove Vite's public-file import warning; the reproducible script maintains both copies.
- Completed production build, lint, four unit checks, six real-browser checks and screenshot review. This feature is ready for frontend review and shared location/time integration; exact-time star/cluster/galaxy visibility remains an explicitly documented backend need.
