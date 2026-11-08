# Pleiades AI / ML / Astronomy Handoff

Living Role C implementation and integration record. Last updated: November 8, 2026 (America/New_York). Latest cross-team integration: [INTEGRATION_HANDOFF.md](INTEGRATION_HANDOFF.md). Historical work-log entries below retain their original verification context.

## Current status

**Latest frontend astronomy integration:** [Explore in 3D handoff](frontend/EXPLORE_3D_HANDOFF.md) documents the 263-object atlas, complete 2D thumbnail set, default visibility sorting and existing API boundary. Fixed objects now have local approximate geometric altitude estimates from J2000 coordinates and selected WNY time/location; they are not precision ephemeris positions or weather/brightness-aware observability predictions. Constellations use their catalog centers. Planets/Moon still use matched nightly rise/set events, with incomplete information kept unknown; the nightly maximum is not used as a selected-hour altitude. No scoring seam, backend endpoint/schema or Gemini behavior changed. Any future exact-position integration should replace these estimates through a coordinated typed contract while preserving unknown/stale-context handling. Latest frontend checks were 7 unit and 14 browser tests, separate from the backend/ML results below. The later local Docker/score-service startup success is recorded in [the project handoff](INTEGRATION_HANDOFF.md#local-apidatabase-startup-resolved-follow-up); older startup blockers below are historical.

- **Implemented:** physics scoring v2; opt-in trained calibration v3; Skyfield astronomy; grounded Gemini vision/explanation code; real WNY grid; training, evaluation, and smoke-test tools.
- **Offline verification:** **149 passed, 1 skipped** in the combined backend/Role C suite (`tests` + `data/tests`; 12 of those are Role C tests). The skipped module is the live-DB integration test; run it with `pytest -m db` (below). One upstream Skyfield/NumPy deprecation warning remains.
- **Real DB verified (Role B):** the new `python -m app.ingest grid` job loads `data/wny_grid.geojson` into `grid_cells`. On local TimescaleDB 2.31 + PostGIS, `ingest bootstrap --reset-grid` loaded 364 cells (8 curated; Beaver Meadow 21.3995 mag/arcsec²) and wrote 26,208 live Open-Meteo forecast rows. It then scored all 26,208 cell-hours end to end with model v2. `pytest -m db`: 6 passed.
- **Real data:** 364 WNY cells with atlas brightness and Open-Meteo elevation. Live weather-to-score smoke produced 72 hourly scores across three WNY spots.
- **Training:** 7,845 training observations and 528 spatially/temporally withheld observations; learned NELM MAE 0.8603 versus physics 2.2869 and constant-mean 0.9846.
- **Gemini HTTP 400 resolved (Nov 8):** Gemini rejects request deadlines under 10 s (400 INVALID_ARGUMENT). `explain_score` now sends at least 10 s, `EXPLAIN_TIMEOUT_S` defaults to 12 s, and the model is `gemini-3.5-flash`. A live score explanation was verified. Vision has not been verified live.
- **Not verified:** S3 upload-to-result integration, deployment, real-photo recognition accuracy, and WNY-specific learned-model accuracy.
- The original Role C implementation preserved backend seam signatures. Later Role B ingestion/deadline fixes and Role A map features are recorded below. The integration pass resolves committed merge markers, connects frontend observing context, and updates the old timeout test; it does not change scoring behavior or database contents.

## Scope and accepted plan

Role C owns scoring, astronomy, Gemini vision/explanations, static geographic preprocessing, and model evaluation. Priorities: **Best AI/ML**, **Best General Hack**, **Radial Atoms**, **Spirit of the Hackathon**.

Reviewed context: `Architecture.md`, `plan.txt`, `prize_tracks.txt`, `backend-documentation.md`, `explanation.md`, actual seam types, worker/spot integration, and existing tests. The backend guide is the integration boundary: preserve the four seam signatures and coordinate shared-contract changes.

The user specified **8–12 hours**, **both** physics-informed/LLM functionality and a trained scoring component, and requested real evaluation datasets. The accepted order was baseline verification → physics and astronomy → real-data training → Gemini → integration/evaluation → demo/handoff. The implementation follows that order; trained artifact creation is complete, with learned deployment opt-in pending local validation.

## What changed and where

| File | Implemented behavior |
|---|---|
| `backend/app/scoring/model.py` | Shape checks, conservative missing-data policy, vectorized optical score, zenith Moon-scattering proxy, auditable point attribution, optional trained inference, version selection |
| `backend/app/astro/ephemeris.py` | Offline DE421 Sun/Moon state, twilight/rise/set, planet visibility, bright-object candidates, cached local-night summary, Moon events, verified 2026 Leonids prediction |
| `backend/app/ai/explain.py` | Bounded structured Gemini request, one SDK attempt, finite HTTP timeout, fact-constrained prompt, deterministic fallback |
| `backend/app/ai/vision.py` | Actual image validation, grounded structured Gemini analysis, candidate-name/type filtering, uncertainty guidance, failure propagation |
| `backend/requirements.txt` | Added `skyfield-data`, `tzdata`, `rasterio` |
| `backend/tests/test_foundation.py` | Replaced the old fake two-byte JPEG assumption with a valid fixture and mocked Gemini; fallback check remains offline |
| `backend/tests/conftest.py` | Isolated process settings for offline tests so explanation helper threads cannot inherit real developer credentials |
| `data/atlas.py` | Shared atlas sampling and unit conversion for training and grid preprocessing |
| `data/build_grid.py` | Real WNY grid artifact; optional transactional DB merge preserving existing IDs |
| `data/train_calibration.py` | Supervised monotone affine NELM fit, filtering, disjoint holdout, metrics, bootstrap comparison, reproducible artifacts |
| `data/models/calibration.json` | Fitted coefficients, source hashes, splits, metrics, evaluation gate, limitations |
| `data/models/split_manifest.json` | Observation IDs/years, hashed spatial blocks, train/test/embargo assignment; no exact observer locations/comments |
| `data/wny_grid.geojson` | 356 regular centres plus eight curated spots, real brightness and elevation, approximate Bortle, provenance |
| `data/tests/test_role_c.py` | Numerical behavior, astronomy sanity checks/DST, trained inference, SDK/vision failure behavior, evaluation-label isolation |
| `data/verify_runtime.py` | Full-grid offline integration/performance and region-centroid approximation checks |
| `data/live_weather_smoke.py` | Live three-spot weather → exact-location astronomy → scoring without a DB |
| `data/live_gemini_smoke.py` | Two explicit live calls: explanation and synthetic non-sky rejection; redacted failure reports |
| `data/diagnose_gemini.py` | Safe read-only model-list diagnosis; no secret output |
| `data/configure_gemini.py` | Hidden terminal input to replace duplicate key assignments while preserving other runtime configuration |
| `data/evaluate_vision.py` | Reviewed-photo grounded/ungrounded pipeline evaluation; dry-run mode and metrics |
| `data/README.md` | Setup, commands, model semantics, data acquisition/reproduction, evaluation schema, attribution, known limits |
| `data/.gitignore` | Keeps downloaded raw archives/raster/photos out of Git |

The two existing-test adjustments are limited AI integration repairs, outside the original seam-only production ownership. They make the real seam compatible with the backend guide's offline-testing requirement. Other new ML checks live under `data/tests/`.

## Scoring contract and interpretation

Existing `FeatureBatch`/`ScoreBatch` signatures and field units are unchanged. Arrays have shape `(N,)`; missing numerical inputs are NaN. Cloud/humidity values are percent, Moon illumination is a fraction, altitude is degrees, visibility/elevation are metres, wind is km/h, and timestamps are UTC.

- **Default physics mode:** `MODEL_VERSION=2`; original NELM 4–7 index anchors retained.
- **Trained mode:** set `PLEIADES_USE_CALIBRATION=1` before process startup; `MODEL_VERSION=3`; loads `data/models/calibration.json` and maps corrected observed NELM 1–7 to 0–100. Ship the artifact with the backend and use the real atlas grid first.
- These are relative observing indices with different anchors. Compare versions explicitly; do not present equal scores from the two versions as calibrated equivalents.
- Learned coefficients adjust dark background NELM. Moon decrements, clouds, haze, elevation and twilight remain physics/heuristic modeled. Historical clear/moonless training does not validate those weather-dependent effects.
- Standard factor keys remain present. Added `calibration` key uses signed points. Attribution order: light pollution → calibration → Moon → clouds → haze → twilight → elevation. Effects reconcile to score minus 100, depend on order, and are not causal measurements.
- Missing clouds default conservatively; missing solar altitude yields an invalid score for the existing backend to drop. Unknown or out-of-training-range static brightness retains physics behavior. Bortle fallback is approximate.
- The zenith Moon model lacks target direction/separation. NELM is an estimated background quantity before explicit cloud/transparency score penalties. Wind and precipitation probability currently do not directly affect this optical index.

## Training evidence and provenance

Real observation archive: [Kyba et al., GFZ 2022](https://doi.org/10.5880/GFZ.1.4.2022.008), data CC BY 4.0. The archive includes 58,359 prefiltered clear/night observations. The trainer selects 2014–2017 near the atlas epoch, rejects potentially automatic SQM-paired labels, duplicate location/times and invalid records, and verifies Sun below −18° and Moon below −5° with Skyfield.

Matching input: [Falchi et al., World Atlas](https://doi.org/10.5880/GFZ.1.4.2016.001), with its [paper](https://doi.org/10.1126/sciadv.1600377). Current DOI metadata specifies **artificial mcd/m²**; add natural background **0.171 mcd/m²** before conversion. The DOI records a November 2019 license update to **CC BY-NC 4.0**; the ZIP contains an older embargo README. Preserve current license provenance and both required citations with derived artifacts. Raw files remain ignored under `data/raw/`.

| Evidence | Result |
|---|---:|
| Usable selected observations | 13,007 |
| Training: 2014–2016 in training spatial blocks | 7,845 |
| Test: 2017 in separate spatial blocks | 528 |
| Cross-boundary observations embargoed | 4,634 |
| Spatial blocks | 517 |
| Physics test NELM MAE / RMSE | 2.2869 / 2.5524 mag |
| Learned test NELM MAE / RMSE | 0.8603 / 1.1597 mag |
| Constant training-mean test MAE | 0.9846 mag |
| Exploratory block-bootstrap learned-minus-physics MAE interval | [−1.2788, −0.6287] mag |

Splits use deterministic 2° spatial blocks and separate years, preventing shared sites/nights. Broader geographic bias and noisy ordinal labels remain. The test report is also used as an enable gate, so treat it as development evidence rather than a fresh post-selection audit. **These numbers are not WNY 2026 forecast accuracy or Gemini recognition accuracy.**

## Verified commands and results

From repository root unless noted; Linux uses `.venv/bin/python` instead of `.venv/Scripts/python.exe`.

```powershell
# From backend/:
.venv/Scripts/python.exe -m pytest -q tests ../data/tests
# 149 passed, 1 skipped; one upstream deprecation warning (skipped = live-DB test)
```

```powershell
backend/.venv/Scripts/python.exe data/train_calibration.py
backend/.venv/Scripts/python.exe data/build_grid.py
backend/.venv/Scripts/python.exe data/verify_runtime.py
backend/.venv/Scripts/python.exe data/verify_runtime.py --trained
backend/.venv/Scripts/python.exe data/live_weather_smoke.py
```

- Python 3.12 project environment is installed at `backend/.venv`. Default machine Python was a 3.15 beta without pytest. Windows Store interpreter calls needed approved execution outside the sandbox.
- Full-grid benchmark: **26,208 cell-hours**, all finite and accepted by backend batch/snapshot conversion. Last reports: physics ~160 ms, trained ~109 ms. Earlier runs varied ~82–148 ms; these are local timings, not deployment promises.
- Latest night summary: ~41–50 ms cold and ~0.17–0.19 ms warm. Reports are `data/runtime_report_v2.json` and `data/runtime_report_v3.json`.
- Benchmark weather is explicitly **synthetic clear weather**, combined with real static inputs and computed ephemeris.
- At the four bounding-box corners over the sampled 72 hourly timestamps, centroid Sun/Moon altitude differences reached ~1.25°. Twilight-gate difference reached **0.191** near a boundary. Retain this approximation as a hackathon limitation; exact per-cell twilight would require backend data/contract coordination. Photo grounding and live spot smoke use exact locations.
- Live weather smoke: three WNY curated spots × 24 hours → **72 scored rows**; report `data/live_weather_report.json`. It uses local fixture ordinals, not database IDs.
- Grid output has elevation for all 364 cells. Default generation makes no DB changes. Optional `--load` updates matching centres/inserts missing cells in one transaction and never deletes cells/renumbers IDs. Live SQL execution remains unverified.
- **Supported DB load path (Role B):** `python -m app.ingest grid` (from `backend/`) reads the committed GeoJSON (override with `GRID_GEOJSON_PATH`). It needs no atlas raster and validates every feature before touching the DB. It does nothing if `grid_cells` is populated. `--reset` truncates the grid **and everything referencing it** (forecasts, scores, explanations, photos, votes). Use `build_grid.py --load` only when IDs must be preserved.

```bash
# From backend/ (Role B, verified):
.venv/bin/python -m app.ingest bootstrap --reset-grid   # grid -> astro -> weather -> score
# job grid: ok (364) · astro: ok (100) · weather: ok (26208) · score: ok (26208)
TEST_DATABASE_URL=postgres://…/pleiades_test .venv/bin/python -m pytest -m db
# 6 passed (throwaway DB; the test truncates tables)
```

## Historical Gemini configuration and failure diagnostics

These diagnostics precede the later Role B deadline/model fix and successful explanation recorded under Current status. They preserve earlier evidence, not a current provider-readiness claim; no live Gemini check was repeated during the atlas or documentation passes.

**Earlier check after the user's “saved” reply:** the configured value had a recognized modern auth-key format and runtime equality with the project `.env` was verified without exposing it. Google returned JSON HTTP 401 `UNAUTHENTICATED`, reason `ACCESS_TOKEN_TYPE_UNSUPPORTED`, message “API key not valid. Please pass a valid API key.” Both actual SDK smoke calls failed with this response. A direct `gemini-2.5-flash-lite:generateContent` probe also returned 401, so changing only the model did not resolve authentication at that point. Earlier HTTP 400 notes below are historical.

Google support discusses this exact pattern [here](https://discuss.ai.google.dev/t/401-access-token-type-unsupported-for-all-new-aq-auth-keys-fresh-project-all-endpoints-latest-sdk/198104): check environment overrides/copy fidelity, use the native API key header, test Flash Lite, then verify AI Studio origin/active status if 401 persists. We already explicitly pass `x-goog-api-key`, have checked the file/runtime match, and tested Flash Lite. No Bearer/OAuth workaround or account-permission change was made. The user has been asked only for key origin/active status, not its value.

- Verified key presence without printing it. User confirmed configuration. The model name was found only in `.env.example`; added the nonsecret `GEMINI_MODEL=gemini-2.5-flash` setting to the ignored runtime `.env`. Did not print or replace the key.
- `data/live_gemini_smoke.py` attempted one grounded synthetic explanation and one synthetic non-sky rejection. Both received **ClientError / HTTP 400 / HTML**. No successful live inference is claimed.
- `data/diagnose_gemini.py` made a direct authenticated request to `/v1beta/models` using Requests, outside the SDK. It also received HTTP 400 with HTML. Provider/account/network diagnosis remains open; do not assume the key itself is invalid from this response alone.
- User reproduced the same HTTP 400 HTML response from a normal terminal. Additional structural checks found no expected legacy token, no recognized modern auth prefix, no assignment text or whitespace in the configured value, and no proxy environment. These checks print no credential characters.
- An initial legacy-only format check was too narrow; corrected it after consulting Google's current auth-key documentation. `configure_gemini.py` accepts single-value ASCII credentials without enforcing the old `AIza` prefix. No secret has been replaced automatically. Use the helper with the complete value from AI Studio, then retry diagnosis.
- User was given this safe terminal command and asked for its output:

```powershell
Set-Location 'C:\Users\PC\Documents\Documents\TheWatchtower\pleiades'
.\backend\.venv\Scripts\python.exe .\data\diagnose_gemini.py
```

- Live reports redact secret values and record status/error type. Never paste keys into chat, reports, test fixtures, or committed files.
- Structured calls use finite HTTP timeouts and one SDK attempt. Explanation API errors reach the route's uncached fallback. Vision errors reach the worker's existing three-attempt/failed path.
- If Gemini is unconfigured, `explain_score` returns deterministic offline template text. The existing route treats that return as cacheable; clear those cached templates when configuring Gemini (`DELETE FROM score_explanations;`), or add provenance-aware caching with Role B. On Nov 8 all 85 cached rows in the local DB were template text.
- Transport timeouts do not establish a hard deadline for the entire background pipeline. The endpoint issue is resolved locally; verify the deployed SDK/network path separately.

## Integration actions for teammates

1. Install updated `backend/requirements.txt`; keep `data/models/calibration.json` with the deployed repository if enabling v3.
2. **Done (Role B):** `data/wny_grid.geojson` loads through `python -m app.ingest grid`, and `bootstrap` runs grid → astro → weather → score. `infra/deploy.sh` runs `bootstrap` on every deploy; the grid step does nothing once loaded. If you regenerate the GeoJSON, commit it and then run `ingest bootstrap --reset-grid`, but **only before real photos exist** (the reset cascades to photos/votes). After that, use `build_grid.py --load` (its SQL is still untested).
3. Restart API and scoring jobs together after model/config changes. Default v2 is ready for integration; use v3 explicitly after local validation. Preserve model-version labels in comparisons/history.
4. Frontend: support the additional `calibration` factor label. Grid artifact Points are centres; existing API makes noncurated squares at `GRID_STEP_DEG=0.1`. Curated locations remain Points.
   - **Done (Role A, Nov 7):** `FACTOR_LABELS` in `frontend/src/lib/scoreColors.ts` maps `calibration` to "Calibration". Unknown keys fall back to a readable version of the key.
   - **Note for Role C:** the frontend's smooth score surface assumes the 0.1° spacing and the current grid extent (centres −79.8 to −77.0, 42.0 to 43.3). So do its hard-coded map bounds (`DATA_BOUNDS` / `PAN_BOUNDS`). If you regenerate `data/wny_grid.geojson` with a different spacing or extent, tell Role A.
5. **Fix forecast-sensitive explanation caching in Role B's route/repository layer:** current identity is cell/hour/model version, so forecast updates can leave stale text. Include score revision or input hash and test invalidation. Seam changes alone cannot fix this.
6. **Extend photo context provenance with Role B before using capture metadata as strong evidence:** `VisionContext` lacks `taken_at_source` and camera orientation. Current worker substitutes upload time when capture time is absent. The prompt explicitly treats metadata as uncertain, but the API cannot yet distinguish that case.
7. The spot route currently leaves `ExplainContext.visible_planets` empty. Populate it from verified astronomy if the UI needs planet-specific explanation text. Never infer moonset/event times absent from context.
8. Helper threads lack Flask request context and use process settings. Production should keep environment settings consistent; backend tests now isolate that path from real keys. Coordinate explicit settings/context propagation if per-app settings are needed.
9. **Partly done:** real-DB migrations, aggregates, grid load, ingest jobs and score persistence are verified (`pytest -m db` and the local bootstrap above). The hourly aggregate now uses the same `America/New_York` timezone and 12 h offset as the nightly one, which TimescaleDB 2.2x+ requires (`002_aggregates.sql`, uncommitted). Still open: S3 upload, worker recovery and a production deploy. The existing worker already has retry/stale-pending startup recovery; it was not rebuilt here.

## Evaluation and remaining work

### Competition readiness priorities

**3D exploration feasibility (user idea):** a bounded object-detail viewer is feasible as optional frontend work, coordinated with Role A. Start with one visible planet and a sourced, rotatable model opened from its astronomy card; lazy-load it and provide a static fallback/attribution. A star-system scene can use a clearly labeled schematic; galaxy depth/structure should be labeled illustrative unless backed by suitable scientific data. A close-up model is an educational view, not what the naked eye/photo necessarily resolves. Bind availability to exact location/time astronomy and preserve uncertain photo-identification labels. NASA Eyes offers documented embedding examples; a custom GLB viewer can use model-viewer. No frontend or runtime dependency changes made for this assessment. Keep live API/upload integration ahead of a full universe simulator.

Based on the supplied `prize_tracks.txt`, prioritize a complete demonstrated user outcome and evidence for the AI behavior before adding more APIs or astronomy extras.

1. **End-to-end demo:** deployed map → real forecast time window → spot score/factors → photo upload → actual AI result. Verify DB, storage, and UI together with Roles A/B. A local unit-test result does not establish this path works in production.
2. **Resolve Gemini authentication:** current 401 remains the immediate AI dependency. After access works, verify both live structured calls and the worker persistence path.
3. **Show real ML evidence:** present the existing held-out NELM comparison fairly (learned 0.8603, physics 2.2869, constant mean 0.9846 mag MAE; n=528), split methodology, and historical/global limitations. Obtain a small reviewed real-photo set and compare grounded/ungrounded vision before claiming reduced identification errors.
4. **Radial Atoms story:** show the WNY atlas + live weather + computed astronomy driving an actual recommendation and a real forecast revision. Hardware is not required by the supplied track description. Do not label cached examples as live sensor observations.
5. **Space experience:** show accurate local twilight/Moon/planet information and explain what the user could attempt to observe. Add ISS/full meteor coverage only after the core path works.
6. **Judging package:** rehearse a three-minute walkthrough using actual conditions, capture a backup video, label cached examples, prepare source/model evidence and a working public URL/QR code. Describe the user benefit before implementation details.

Suggested demo sequence: WNY stargazing decision → compare locations/time windows → explain the score → analyze a reviewed real photo with uncertainty → show real environmental-data provenance and measured model evidence. Current readiness gaps are operational integration and real-photo/live-AI verification; additional weather/time APIs do not close those gaps by themselves.

- **Timeanddate API assessment (user question):** useful as an external reference or optional astronomy fallback. Its documented [event service](https://dev.timeanddate.com/docs/astro/astronomy) supplies Sun/Moon rise/set and twilight; its [position service](https://dev.timeanddate.com/docs/astro/astrodata) supplies altitude, azimuth and Moon illumination. These overlap implemented local Skyfield functionality and do not resolve Gemini access, image evaluation, or DB integration. [Packages](https://dev.timeanddate.com/astro/pricing) have credits/location limits and a trial. No integration or account creation performed. Recommendation: retain Skyfield for runtime and validate a few WNY location/date cases against an external source, including the [USNO daily Sun/Moon API](https://aa.usno.navy.mil/data/api), before adding another production dependency.

- `data/evaluate_vision.py` accepts reviewed real photos, verified capture metadata, canonical exhaustive supported-object labels, and source/permission information. `--dry-run` validates without model calls. Normal evaluation makes grounded and ungrounded calls per image and reports precision/recall, abstentions, classification, failures and latency. Labels never enter prompts.
- Dataset research: [1,750-image constellation candidate](https://universe.roboflow.com/astro-tc3uc/constellation-detection), [SWINSEG cloud masks](https://malea.winkler.site/swinseg.html), and [LenghuSky-8](https://github.com/ruiyicheng/LenghuSky-8). Their suitability for reliable capture metadata/object labels has not been verified. Cloud masks do not label celestial identities or stargazing scores.
- No real-photo benchmark has run and no recognition-accuracy percentage is available. Need reviewed real images/metadata and working Gemini endpoint first.
- Grounded candidates are possibilities, not confirmed detections. Constellation anchors approximate an extended region. Confidence is self-assessment, not calibrated probability; candidate filtering does not validate every generated prose claim.
- Star coordinates are rounded J2000 candidate anchors, not a plate-solving catalog. No camera orientation/field of view, terrain horizon, access hours, or current local lighting model exists.
- Moon/twilight night-summary times interpolate five-minute samples; planet magnitudes are currently null. Only the sourced 2026 Leonids prediction and computed Moon events are emitted; ISS passes and a full meteor calendar remain unimplemented.
- Shoreline masking reuses coarse development polygons. Better land/water data and local observing validation are follow-up work.

## Work log

- **Planning/context:** read architecture, backend guide and explanation; created this living document; recorded user scope and dataset request.
- **Baseline/scoring:** installed Python environment; replaced scoring placeholder; first post-edit run 112 passed, 1 skipped. A true pre-edit baseline was unavailable because interpreter setup initially failed.
- **Astronomy/AI:** replaced remaining seams; bundled offline kernel; repaired placeholder-only smoke assumptions and isolated test credentials.
- **Real data/training:** obtained observation/atlas archives through current DOI links after obsolete paths returned 403; trained and evaluated the two-coefficient model; saved reproducible artifacts.
- **Grid/integration:** generated real WNY brightness/elevation, verified both full-grid modes, measured centroid approximation, and scored real three-spot weather.
- **Latest verification:** combined suite 123 passed, 1 skipped; Gemini live and direct API checks failed with HTTP 400 HTML; user is running safe diagnosis. No DB/deployment success or real-photo accuracy is claimed.
- **Gemini follow-up:** user confirmed the same failure outside the agent. Added safe configuration helper and an offline test for replacing duplicate assignments without altering model/other settings. Removed an overly narrow legacy-key assumption. Next action requires a complete AI Studio credential entered privately, followed by endpoint verification.
- **Follow-up verification:** combined suite **124 passed, 1 skipped** after adding the configuration helper test.
- **New credential verification:** key presence/modern format and file/runtime equality verified; direct listing, both SDK smoke calls, and a Flash Lite probe returned **401 ACCESS_TOKEN_TYPE_UNSUPPORTED**. Updated `data/live_gemini_report.json`; added an optional `--probe-model` diagnostic flag without changing the configured model. Waiting for AI Studio active/origin status before further credential requests.
- **User-requested retry:** reran `data/diagnose_gemini.py`; runtime still matches the project `.env`, but Google again returned JSON **401 UNAUTHENTICATED / ACCESS_TOKEN_TYPE_UNSUPPORTED**. Did not repeat generation calls after authentication failed. No credentials printed or changed.
- **Subsequent “try now” check:** direct model listing still returns **401 ACCESS_TOKEN_TYPE_UNSUPPORTED** with file/runtime credential equality confirmed. Generation tests remain deferred until authentication succeeds.
- **Role B grid ingestion (Nov 7):**
  - Added the `ingest grid [--reset]` and `ingest bootstrap [--reset-grid]` jobs, the `GRID_GEOJSON_PATH` setting, and a bootstrap step in `deploy.sh`.
  - Relabelled `seed_dev_grid.py` as a synthetic fallback.
  - Fixed the hourly/nightly aggregate timezone mismatch for TimescaleDB 2.31.
  - Replaced the synthetic grid in the local DB with the real one and verified live ingest and scoring. `pytest -m db` 6 passed; combined suite **149 passed, 1 skipped**.
  - Not committed yet.

- **Role A frontend integration (Nov 7):**
  - The map now consumes model v2 scores through `GET /api/scores` and `/api/scores/range`, via the Vite proxy to Flask on :5001.
  - Scores are drawn as a smooth red → yellow → green surface, with curated spots as circles. Click popups show the score, label, Bortle class, and top factor.
  - Observed live ranges:
    - 0.4–16 at 2026-11-08T02:00Z (all cells scored, none null).
    - Up to 44 at 05:00Z on Nov 8.
    - Up to 69 at 05:00Z on Nov 9.
  - No seam, contract, or backend code was changed.

- **Gemini fix and frontend features (Nov 8):**
  - Cause of the HTTP 400: the SDK forwards the HTTP timeout as a server deadline, and Gemini rejects deadlines under 10 s. `_generate_json` now defaults to 10 s, `explain_score` uses `max(10 s, EXPLAIN_TIMEOUT_S − 0.25 s)`, and `EXPLAIN_TIMEOUT_S` defaults to 12 s (`config.py`, `.env.example`). `GEMINI_MODEL` in `.env.example` is now `gemini-3.5-flash`.
  - Live check: one `explain_score` call for Zoar Valley (cell 363, Nov 10 4 AM, score 50) returned grounded text and three tips in about 6 s. Nothing was written to the DB.
  - All 85 cached explanations in the local DB are template text from before the key was loaded. Clear them to see Gemini text for those cells and hours.
  - Role A frontend: spot panel (explanation, factors, history and drift charts), Tonight's best, Sky tonight, and user location now call `/spots/:id`, `/history`, `/drift`, `/best`, and `/sky-events`.

See [data/README.md](data/README.md) for detailed run commands, manifest schema, data retrieval, scientific references, and attribution.
