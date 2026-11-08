# AI / ML data, operation, and reproducibility

See [AI_ML_HANDOFF.md](../AI_ML_HANDOFF.md) for implementation status and team integration notes. Commands below start at the repository root. On Linux replace `backend/.venv/Scripts/python.exe` with `backend/.venv/bin/python`.

## Install and verify

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
Set-Location backend
.venv/Scripts/python.exe -m pytest -q tests ../data/tests
Set-Location ..
```

Skyfield uses the DE421 kernel bundled in `skyfield-data` and its built-in timescale. Requests/tests never download astronomy files. An optional absolute `PLEIADES_EPHEMERIS_PATH` selects a locally provisioned alternative kernel; restart the process after changing it. DE421 covers this project's historical training and 2026 forecast dates, not arbitrary future dates. No ISS/TLE integration has been implemented.

## Model modes

- Default: physics-informed observing index, `MODEL_VERSION=2`. It estimates sky-background NELM and multiplies transparency and twilight effects. It does not predict an exact visible-star count.
- Opt-in: set `PLEIADES_USE_CALIBRATION=1` in the server environment and restart API **and** jobs. `MODEL_VERSION=3` loads `data/models/calibration.json`. Ship that artifact with the deployment and load the real grid first. An invalid or absent artifact fails visibly on startup.
- Both versions return the existing `ScoreBatch` contract. `calibration` is an additional point-factor key; the six standard keys remain present. UI code should render arbitrary factor keys and label this one “observational calibration.”
- Points use sequential differences in this order: light pollution, calibration, Moon, clouds, haze, twilight, elevation. They reconcile to score minus 100 within rounding, but depend on order and are not measured causal contributions.
- Physics index maps NELM 4–7 to 0–100. Trained mode maps corrected observed NELM 1–7 to 0–100. Explain the index version when comparing scores; equal numbers across versions are not calibrated equivalents.
- Learned calibration covers clear, moonless **background NELM** only. Cloud, humidity, Moon, and twilight effects remain modeled. NELM output describes estimated sky-background visibility before explicit cloud/transparency penalties.
- Missing cloud information uses conservative defaults; absent solar altitude produces NaN so the existing ingest job drops that row. Synthetic Bortle-derived brightness is a fallback estimate. Out-of-training-range or missing sky brightness retains physics behavior.
- Wind and precipitation probability are passed through the backend contract but currently do not directly affect this optical index. Terrain, access hours, target direction, seeing, camera exposure, and current local lighting are not modeled.

Verify both paths without a database or network:

```powershell
backend/.venv/Scripts/python.exe data/verify_runtime.py
backend/.venv/Scripts/python.exe data/verify_runtime.py --trained
```

These commands use real static inputs and ephemeris with **synthetic clear weather**, and save `runtime_report_v2.json` / `runtime_report_v3.json`. They do not claim to be live forecasts.

## Reproduce supervised training

Raw files are ignored by Git. Download these published public archives into `data/raw/`:

- [Kyba et al., Globe at Night observations and code](https://doi.org/10.5880/GFZ.1.4.2022.008), [current ZIP](https://datapub.gfz.de/download/10.5880.GFZ.1.4.2022.008-Mcvwue/2022-008_Kyba-et-al_GaN-code-and-data.zip) → `globe_at_night_2022.zip` (about 10 MB).
- [Falchi et al., World Atlas dataset](https://doi.org/10.5880/GFZ.1.4.2016.001), [ZIP](https://datapub.gfz.de/download/10.5880.GFZ.1.4.2016.001/World_Atlas_2015.zip) → `World_Atlas_2015.zip` (about 653 MB). Extract only `World_Atlas_2015.tif` into `data/raw/` (about 3 GB).

The source DOI landing pages should be used if a download URL changes. Keep the archive README and current license provenance with local data. Do not execute the archived third-party scripts; our trainer reads CSV data only.

```powershell
backend/.venv/Scripts/python.exe data/train_calibration.py
```

The trainer samples the same artificial-only **mcd/m²** atlas used by the grid, adds 0.171 mcd/m² natural background, converts to mag/arcsec², and computes the physics baseline NELM. It learns an affine correction with a positive bounded slope using observed NELM labels. It excludes SQM-paired potentially automatic labels, duplicate location/times, nonclear or invalid records, and observations outside 2014–2017. Skyfield verifies Sun below −18° and Moon below −5°.

Spatial blocks are 2° × 2°, shuffled with seed 2026. Train uses selected blocks in 2014–2016; test uses separate blocks in 2017. Cross-boundary rows are embargoed. This prevents shared locations and nights across splits, though broader regional biases remain. The stored test set is also used as a deployment gate; treat reported performance as development evidence rather than a fresh final audit after model selection.

Outputs:

- `models/calibration.json`: coefficients, source hashes, preprocessing/split rules, metrics, enable gate, and limitations.
- `models/split_manifest.json`: observation IDs, years, hashed spatial-block identity, and split assignment; no exact observer coordinates or comments.

Recorded run: 7,845 training and 528 held-out observations. Held-out NELM MAE: 0.8603 learned, 2.2869 uncalibrated physics, 0.9846 constant training mean. These citizen-science labels are noisy and ordinal. Historical global agreement does not establish 2026 WNY accuracy or prove the full weather-dependent score is calibrated.

## Prepare/load the real WNY grid

```powershell
backend/.venv/Scripts/python.exe data/build_grid.py
# Offline alternative: --no-elevation (preserves null elevation in the artifact)
# Only after backend coordination and DB configuration:
backend/.venv/Scripts/python.exe data/build_grid.py --load
```

Default generation writes `wny_grid.geojson` and fetches Open-Meteo elevation. It does not modify the database. The artifact has 356 regular centres and eight curated spots, with source metadata and approximate Bortle classes. All artifact geometries are centre Points; the existing API constructs map squares for noncurated cells using `GRID_STEP_DEG=0.1`.

The optional loader merges matching centres within 1 metre, preserving IDs and existing elevation when a new value is unavailable. It refuses ambiguous duplicate matches and never deletes old cells. Database execution remains unverified. The reused development lake polygons are coarse; shoreline cells require a better land/water mask for production accuracy.

## Gemini configuration and live checks

Set `GEMINI_API_KEY` and `GEMINI_MODEL` in the ignored project `.env`; never put keys in manifests or reports. Restart long-running API/job processes after configuration changes.

To replace the key safely, run `backend/.venv/Scripts/python.exe data/configure_gemini.py` in an interactive terminal. It uses hidden input, preserves unrelated settings, and accepts newer authorization-key formats as well as legacy keys. Get the complete key value from [Google AI Studio](https://aistudio.google.com/apikey); never paste it into chat.

```powershell
backend/.venv/Scripts/python.exe data/live_gemini_smoke.py
backend/.venv/Scripts/python.exe data/diagnose_gemini.py
backend/.venv/Scripts/python.exe data/live_weather_smoke.py
```

The first command makes two real Gemini calls: one synthetic score explanation and one synthetic non-sky test card. This tests service integration and rejection, not real-photo identification accuracy. The diagnostic reads model availability without printing secrets. Weather smoke fetches three real WNY forecasts and saves 72 scored hours without using a DB; its local ordinals are not database IDs. Reports contain source/fetch metadata and are snapshots, not continuously current data.

Vision enforces MIME/content agreement, 15 MB, 40 megapixels, structured output, and candidate-name/confidence filtering. Confidence is model self-assessment, not calibrated probability. Candidates establish possible visibility only; a constellation anchor does not establish the whole constellation is visible. Camera orientation and capture-time provenance are absent from the seam contract. Model descriptions still require evaluation; candidate filtering cannot prove every prose statement.

One SDK attempt is made per invocation. HTTP timeouts are 6.5 seconds or less for explanations and 20 seconds for vision. The worker handles retries. The SDK's transport timeout is not a hard deadline for the entire worker pipeline; test end-to-end behavior in the deployment environment.

When unconfigured, explanations return clearly deterministic offline text; the current route can cache that text. When configured calls fail, exceptions reach the route so its fallback is not cached. Vision always raises failures to the worker; it does not fabricate successful analysis.

## Reviewed-photo evaluation

The publisher's [1,750-image constellation dataset](https://universe.roboflow.com/astro-tc3uc/constellation-detection) is a candidate for visual labels, but its capture metadata and image provenance have not been audited. [SWINSEG](https://malea.winkler.site/swinseg.html) provides cloud masks rather than object identities. Do not substitute either type of label for the other, or invent photo coordinates/time.

Create a local manifest with real files and manually reviewed, exhaustive labels for objects in our supported catalog. Keep evaluation photos/manifest under ignored `data/raw/`. Example schema (replace every example value with verified data):

```json
[
  {
    "id": "photo-001",
    "path": "photos/photo-001.jpg",
    "source": "Photographer/source URL and permission or license",
    "lat": 42.7,
    "lon": -78.4,
    "taken_at": "2026-11-08T04:00:00Z",
    "reviewed": true,
    "metadata_verified": true,
    "is_night_sky": true,
    "objects": ["Pleiades"]
  }
]
```

```powershell
backend/.venv/Scripts/python.exe data/evaluate_vision.py data/raw/photos_manifest.json --dry-run
# Makes two real Gemini calls per image:
backend/.venv/Scripts/python.exe data/evaluate_vision.py data/raw/photos_manifest.json
```

Labels never enter prompts. Evaluation reports object precision/recall, abstentions, night-sky classification, failures, and per-image latency. Comparison changes both candidate prompting and output filtering, so it measures the grounded pipeline rather than isolating prompt grounding alone. Exact-name scoring requires canonical reviewed names. No real-photo accuracy result has been obtained yet.

## Sources and attribution

- Kyba, Altıntaş, Walker, Newhouse (2022), [Globe at Night code/data archive](https://doi.org/10.5880/GFZ.1.4.2022.008). Observation data CC BY 4.0; archived software Apache 2.0. We wrote our own trainer.
- Falchi et al. (2016), [dataset](https://doi.org/10.5880/GFZ.1.4.2016.001) and [The New World Atlas of Artificial Night Sky Brightness](https://doi.org/10.1126/sciadv.1600377). Current DOI metadata records CC BY-NC 4.0, updated November 2019; the ZIP's older 2016 embargo text predates that update. Cite both dataset and paper. Preserve attribution and noncommercial terms with derived artifacts.
- Krisciunas & Schaefer (1991), [A Model of the Brightness of Moonlight](https://ui.adsabs.harvard.edu/abs/1991PASP..103.1033K/abstract). Scoring uses a simplified zenith proxy, not their complete target-dependent observing model.
- [Skyfield almanac documentation](https://rhodesmill.org/skyfield/almanac.html), [bundled data package](https://pypi.org/project/skyfield-data/). JPL DE421 kernel; Skyfield built-in timescale.
- [IMO 2026 meteor-shower calendar](https://www.imo.net/files/meteor-shower/cal2026.pdf), for the Leonids predicted maximum only. No generic annual-date extrapolation is presented as an exact event.
- [Google Gen AI SDK](https://googleapis.github.io/python-genai/), for structured outputs, client lifecycle and request configuration.
- Open-Meteo supplies the [forecast](https://open-meteo.com/en/docs) and [elevation](https://open-meteo.com/en/docs/elevation-api) inputs through the existing backend client.
