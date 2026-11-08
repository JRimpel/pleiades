# Pleiades frontend

React, TypeScript and Vite serve the WNY score map and the Explore in 3D atlas. Start with [EXPLORE_3D_HANDOFF.md](EXPLORE_3D_HANDOFF.md) for the reusable explorer contract and asset details, and [../INTEGRATION_HANDOFF.md](../INTEGRATION_HANDOFF.md) for full-stack integration status. Broader map/UI documentation is in [../frontend-documentation.md](../frontend-documentation.md).

## Run locally

From the repository root, start the database and Flask using [../README.md](../README.md). Keep Flask on port 5001 running in a separate terminal. Then:

```powershell
# Repository root
Set-Location frontend
npm ci
npm run dev
```

Stop Vite with **Ctrl+C before `npm ci`** on Windows: the running server can lock Rolldown's native binding. Reuse an existing installed environment rather than reinstalling on every run. Vite forwards `/api` to `http://127.0.0.1:5001`; overrides are `API_PROXY_TARGET`, then `PLEIADES_DEV_API_TARGET`. A proxy change requires restarting Vite. Production keeps same-origin `/api` behind nginx.

## Current explorer behavior

- 263 objects: 73 wholly/partly rising WNY constellations, all seven other planets, the Moon, bright stars and all 110 Messier targets.
- Local 2D thumbnails on every card; only opening a model loads its GLB and the viewer library. No Gemini dependency.
- Search and category filtering, then **Visibility** sorting, then pagination in batches of 24. Above-horizon estimates come first, unknown next, below-horizon last. **Name (A–Z)** is optional.
- **Visible tonight** is an independent switch, **off by default**. When on, it intersects search/category matches before full-list sorting and pagination. It includes only objects known to be above the horizon sometime during the selected local night; unknown visibility is excluded. Card status and visibility sort still use the selected slider hour, so a tonight match can correctly say below horizon at that hour.
- The selected map coordinates and forecast hour drive the explorer. Without a selection it uses an in-region GPS fix or the WNY center. Matching cloud/Bortle information is passed through; stale spot conditions are omitted.
- Fixed-object visibility uses approximate J2000 catalog-based altitude. Constellation estimates refer to the center, not every star. Planets and Moon use matched backend night-summary rise/set events. Weather, daylight, terrain, brightness and equipment still affect practical visibility.
- Rotation starts automatically at 12 degrees/second with **Pause rotation / Resume rotation**. The user explicitly requested this even under reduced motion; camera-button changes still snap when reduced motion is requested. Left/right camera buttons and Reset pause auto-rotation; pointer dragging does not explicitly pause it.
- Nebula colors and depths are educational illustrations; the Moon uses NASA LRO surface imagery. See the canonical handoff and asset credits before reusing or changing representations.

The tonight filter requires a night summary matching the selected coordinates and America/New_York night. It prefers the astronomical dusk-to-dawn pair and falls back to sunset-to-sunrise. Missing, incomplete or stale night windows show an explanation and no results while the switch is on; turning it off restores normal browsing. Fixed-object overlap checks both night endpoints and upper transit, including brief low southern arcs that could rise and set between endpoints. Planets/Moon use rise/set interval overlap. The filter does not change endpoints, scoring or Gemini behavior.

## Rebuild assets

The generated assets in this checkout are ready to use; normal development needs no regeneration. Include new runtime files when integrating the working-tree changes. If changing the catalog or reproducing assets, run the standard-library Python scripts **from the repository root in this order**. The first two steps need network access when their caches are missing.

```powershell
python frontend/scripts/prepare-explore-assets.py
python frontend/scripts/expand-explore-assets.py
python frontend/scripts/prepare-explore-thumbnails.py
python frontend/scripts/verify-explore-assets.py
```

The first script creates the original assets and HYG subset; the expansion then replaces the simple original schematics with richer versions. Do not rerun only the first script after expansion. Thumbnail generation follows expansion. Ship `public/explore/` and preserve its source/license manifests. See [EXPLORE_3D_HANDOFF.md](EXPLORE_3D_HANDOFF.md) for stable object IDs, attribution and extension instructions.

## Verify changes

From `frontend/`:

```powershell
npm run build
npm run test:unit
npm run test:browser:install  # once, or after the Playwright browser revision changes
npm run test:browser -- visible-tonight.spec.ts visibility-sort.spec.ts explore.spec.ts integration.spec.ts thumbnails.spec.ts
npm run lint
```

The latest implementation run passed the production build, **10 unit tests** and **17 browser tests**. Asset validation also passed, including all 263 standalone thumbnails. Browser tests use API fixtures and real local models; they do not establish current live database, Gemini or storage readiness. Lint was not rerun for the latest atlas/sort update. The existing large-bundle build advisory remains.

Playwright starts its own Vite server on port 4173 and uses project-local Chromium. Keep that port free. If a restricted execution environment passes assertions but stalls during browser teardown, rerun with the appropriate normal process permissions; do not report a stalled invocation as a clean completed run.
