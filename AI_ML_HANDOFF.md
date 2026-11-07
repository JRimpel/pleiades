# Pleiades AI / ML / Astronomy Handoff

Living implementation and integration record. Update this file as work is completed, contracts change, or tests reveal limitations.

## Current status

- Last updated: November 7, 2026.
- Owner: AI / ML / Astronomy engineering (Role C in `Architecture.md`).
- Priority tracks: Best AI/ML, Best General Hack, Radial Atoms, Spirit of the Hackathon.
- Completed: reviewed `Architecture.md`, `plan.txt`, and `prize_tracks.txt`; proposed the implementation sequence below; created this handoff.
- Implementation: not started. No AI/ML modules, API contracts, dependency setup, or runtime tests have been completed.
- Repository at initial review: architecture and planning documents only; the code layout in `Architecture.md` is proposed.

## Goal and ownership

Help users choose where and when to stargaze in Western New York, explain recommendations using real conditions, and analyze sky photos with astronomical context.

Our responsibilities:

- Static geographic features: grid, light pollution, and elevation preparation.
- Physics-informed scoring and factor explanations.
- Astronomy calculations, observing events, and photo candidate grounding.
- Gemini vision and recommendation explanations.
- Evaluation, model versioning, and optional learned calibration.

Integration partners:

- Backend / Data: database migrations, weather ingestion, Flask routes, storage, background execution, and deployment.
- Frontend / UX: map, time slider, spot details, upload/results flow, and charts.
- Shared boundary: Pydantic schemas in the proposed `backend/app/schemas/` directory. Agree on schemas before integrating; coordinate changes with the team.

## Implementation sequence

Times are planning estimates relative to the start of the architecture's 24-hour build, not elapsed work or completed milestones.

| Order | Target hours | Deliverable | Completion evidence |
|---|---|---|---|
| 1 | 0–1 | Agree on scoring, astronomy, vision, and explanation contracts; UTC timestamps and explicit units | Shared example responses and agreed schemas |
| 2 | 1–2 | Reproducible WNY fixtures and configuration | Modules runnable against fixtures without external services |
| 3 | 2–4 | Sun, Moon, twilight, and exact-location astronomical candidates | Verified location/time cases |
| 4 | 3–5 | Grid, light-pollution sampling, and elevation inputs | Traceable values or explicit missing-data states |
| 5 | 4–7 | Vectorized baseline scoring | Reproducible cell-by-hour scores |
| 6 | 6–8 | Factor effects, provenance, forecast freshness, and quality flags | Displayed explanations traceable to computed inputs |
| 7 | 7–10 | Weather → scoring → database → API → map integration | Live map and time slider using real model output |
| 8 | 10–13 | Grounded photo analysis with validated structured output | Useful results plus pending, completed, and failed states |
| 9 | 12–14 | Grounded recommendation explanations and deterministic fallback | Text consistent with the current score revision |
| 10 | 14–17 | Numerical and AI evaluation | Recorded results, errors, abstentions, latency, and failures |
| 11 | 16–19 | Forecast-revision evidence and priority astronomy events | Traceable changes from environmental inputs to recommendations |
| 12 | 19–21 | Optional constrained calibration | Held-out evaluation, or an explicit deferral |
| 13 | 21–23 | Production failure handling and integrated verification | Usable experience during upstream failures |
| 14 | 23–24 | Demo and judging evidence | Three-minute walkthrough based on actual results |

Priority: working score map → grounded photo analysis → trustworthy explanations → evaluation → forecast revisions → extra astronomy events → optional calibration. Cut calibration and ISS passes first if time is limited.

## Design decisions and issues to resolve

These are planning decisions and review findings, not implemented behavior.

1. **Describe the baseline accurately.** The proposed score is a physics-informed model, not a trained ML model. Treat it as a relative observing-condition index until observations validate stronger claims about visible star counts.
2. **Validate units and approximations.** Check light-pollution raster units before conversion; label fallback estimates and approximate Bortle values. Check the region-centroid ephemeris approximation near twilight before accepting it.
3. **Clarify factor attribution.** Log contributions are not directly additive points lost, and zero factors need special handling. Choose a documented counterfactual breakdown or show factor multipliers.
4. **Ground vision conservatively.** Above-horizon objects are candidates, not confirmed detections. Capture time/location provenance and missing camera direction affect identification. Support uncertainty and unidentified objects.
5. **Keep explanation caches fresh.** Include the score revision or input hash in cache identity alongside location, time, and model version. Weather revisions can change the explanation without changing model version.
6. **Treat missing data explicitly.** Do not silently turn absent weather or static features into excellent observing conditions. Specify fallbacks and quality flags in the shared contract.
7. **Use credible calibration labels.** Votes measure popularity; Gemini sky-quality ratings are noisy and camera-dependent. Any learned improvement needs reviewed observations and evaluation withheld by location or night.
8. **Keep provenance honest.** Forecast revisions are environmental-data records, not readings from sensors we deployed. Record source and timestamps.
9. **Make background analysis recoverable.** Coordinate retries and restart recovery with the backend owner so photos cannot remain pending indefinitely.

## Files and modules

| Path | Status | Purpose |
|---|---|---|
| `AI_ML_HANDOFF.md` | Created | Living implementation and integration record |
| `backend/app/schemas/` | Planned; absent at initial review | Shared validated contracts |
| `backend/app/scoring/` | Planned; absent at initial review | Feature processing, moonlight, vectorized scoring |
| `backend/app/astro/` | Planned; absent at initial review | Ephemeris, events, photo candidates |
| `backend/app/ai/` | Planned; absent at initial review | Gemini client, vision, explanations, prompts |
| `backend/tests/` | Planned; absent at initial review | Numerical, astronomy, and AI validation |
| `data/build_grid.py` | Planned; absent at initial review | Static geographic preprocessing |

Add actual files, entry points, and usage examples here as they are implemented.

## Contracts and integration

No contracts have been implemented or agreed yet. `Architecture.md` contains proposed routes and payloads; do not treat them as verified runtime behavior.

As work proceeds, document:

- Feature names, units, ranges, missing-value handling, and UTC timestamp semantics.
- Scoring inputs/outputs, factor attribution, model version, and provenance.
- Astronomy candidate/event payloads and location/time assumptions.
- Vision and explanation schemas, uncertainty handling, and status transitions.
- Database fields, migrations, cache keys, and integration call sites.
- Frontend examples and backend commands needed to connect each module.

## Setup and operation

No executable setup commands have been verified yet.

- Proposed runtime: Python 3.11+, NumPy, Skyfield, Pydantic, and the Google Gen AI SDK; dependency versions remain to be established.
- Proposed AI configuration: `GEMINI_API_KEY` and `GEMINI_MODEL`, consumed server-side. Never record secret values in this file or commit them.
- Astronomy kernel, light-pollution dataset acquisition, local fixtures, and run commands: to be documented after implementation.
- Database, object-storage, and deployment configuration: coordinate with the backend owner and document only relevant integration details here.

## Verification record

| Date | Check | Result |
|---|---|---|
| 2026-11-07 | Read architecture and planning files; inspect repository file list | Planning documents present; no application code observed |
| 2026-11-07 | Runtime tests | Not run; implementation has not started |

Record exact meaningful commands, results, fixture provenance, and remaining concerns as work proceeds. Planned tests are not passing tests.

## Award evidence to collect

| Track | Evidence |
|---|---|
| Best AI/ML | Grounded vs. ungrounded vision comparison, validated outputs, error/abstention examples, reproducible scoring, honest model claims |
| Best General Hack | Complete location/time recommendation and photo-analysis journey |
| Radial Atoms | Real WNY environmental inputs, satellite-derived light pollution, and forecast revisions changing recommendations |
| Spirit of the Hackathon | Astronomy driving recommendations, object candidates, and observing events |

## Work log

### November 7, 2026 — Planning and handoff creation

- Reviewed the system architecture, project description, and local prize-track descriptions.
- Established AI / ML / Astronomy ownership and the implementation sequence above.
- Identified scoring attribution, cache freshness, astronomical grounding, and calibration-label issues to resolve during implementation.
- Created this file at the user's request; update it incrementally as implementation, integration, and testing occur.
- Next action: establish the shared contracts and initial fixtures before building scoring and astronomy modules.
