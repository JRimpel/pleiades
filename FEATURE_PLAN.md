# Pleiades: feature feasibility and build plan

Written November 7, 2026. This is a future-work plan. *Update, Nov 8:* C (Tonight's best and the dusk/dawn ticks) and F (the forecast-drift chart) are built, and the Gemini blocker below is resolved. The rest is not implemented yet.

## Context
The team wants to add two features to the UB Hacking 2026 submission:
1. **Photo "sky stories":** users upload night-sky photos, the photos appear as clickable pins on the map (like Snapchat Map stories), and AI identifies constellations or other notable objects in them.
2. **A chatbot:** users ask questions like "where can I go to see Orion?" or "how does the score look near Letchworth tonight?"

This plan judges whether each idea is feasible given the current code, lists the blockers, and suggests extra features that fit the prize tracks (Best AI/ML, Best General Hack, Radial Atoms, Spirit of the Hackathon, UI/UX, Tiger Data).

---

## Shared blocker: Gemini returns HTTP 400 (resolved Nov 8)
**Resolved:** the cause was a request deadline under 10 s, which Gemini rejects with 400 INVALID_ARGUMENT. Live explanations now work with `gemini-3.5-flash` (see AI_ML_HANDOFF.md). Note for the chatbot: keep any Gemini call's timeout at 10 s or more. The original notes follow.

Both ideas depend on Gemini. Every live call failed with **HTTP 400 and an HTML body** (AI_ML_HANDOFF.md). This should be fixed first, within the first 30 minutes:
- Create a fresh key at aistudio.google.com, enter it with `data/configure_gemini.py`, then run `data/diagnose_gemini.py`.
- If the error persists, test the key with `curl "https://generativelanguage.googleapis.com/v1beta/models?key=$KEY"`. A 400 HTML page usually means the request is malformed, often from a stray character, quote, or BOM in the key. Several source files are saved with a UTF‑8 BOM, which suggests they were edited on Windows.
- **Fallback:** if Gemini can't be fixed, `_generate_json` in `backend/app/ai/explain.py` is the only call site. Another provider with vision and tool use could be swapped in behind it in about an hour.

---

## Idea 1: Photo stories on the map. Feasibility: HIGH (about 70% built)

**Already done on the backend:**
- `api/photos.py`: presign, create, list (`bbox`, `sort`), detail, and vote routes.
- `workers/photo_analysis.py`: thumbnail, `ephemeris.visible_objects`, `vision.analyze_photo`, with 3 retries.
- `ai/vision.py`: grounded Gemini analysis. It keeps only objects that match the above-horizon candidates, with confidence ≥ 0.75.
- Users and bearer-token auth (`api/users.py`); `score_at_capture` is filled in at upload.

**Missing:**
1. **Vultr bucket and credentials** (`VULTR_S3_*` in `.env`), plus a bucket CORS rule allowing PUT and GET from `localhost:5173` and the production origin. The S3 path has never been tested end to end.
2. **All frontend work** (Role A):
   - `api/client.ts` and `hooks.ts`: `createUser`, `presign`, `createPhoto`, `fetchPhotos(bbox)`, `fetchPhoto(id)` (polling every ~2 s while pending), and `vote`.
   - `components/UploadFlow.tsx`: pick a file, read GPS and time with `exifr`, show a "drop a pin" fallback, upload with an XHR progress bar, then show the "Analyzing the sky…" state.
   - `components/UsernamePrompt.tsx`: shown on the first 401; stores the token in `localStorage`.
   - Photo layer in `StargazingMap.tsx`: a clustered GeoJSON source built from `/api/photos`. Use circular thumbnail markers with a glowing ring, which gives the story look. Clicking one opens `PhotoStory.tsx`.
   - `PhotoStory.tsx`: a full-screen story viewer. Tap or swipe through the photos in a cluster in time order, with a progress bar on top. Each photo shows its AI description, object chips (for example "Orion · constellation"), the score at capture, and up/down votes.
3. **"Stories expire" behavior** (optional, small backend change): add a `since` query parameter to `GET /api/photos` (new repo filter) so the map shows "last 24 h" by default, with a toggle for "all time".

**Honest limits on constellation recognition:**
- Gemini on its own is unreliable at naming constellations in wide-field photos.
- The current grounding (candidates above the horizon, plus the 0.75 filter) cuts down hallucinations, but it doesn't confirm that an object is actually in the photo.
- See **Spice idea A** for a real fix.

**Estimate:** 6–8 hours of frontend work plus about 1 hour of bucket setup.

---

## Idea 2: Chatbot. Feasibility: HIGH, if built as an agent that calls tools

The project already has the data the bot needs. A Gemini function-calling loop over existing repo and ephemeris functions gives grounded answers, so the bot doesn't invent numbers. This is also a strong Best AI/ML story: an agent that answers with real time-series data.

**Key product insight:** "Where can I see Orion?" is really a **when** question. Every constellation rises over all of WNY at almost the same time. So the right answer is: *"Orion is above 20° after about 11 PM. At that hour the best dark spot near you is Allegany State Park (score 72, Good)."* The bot combines `visible_objects` over time with `/best` at that hour.

**Backend (new, Role B and C):**
- `backend/app/schemas/chat.py`: `ChatRequest {messages: [{role, content}] (max ~10 turns), lat?, lon?}` and `ChatResponse {reply, tool_calls: [{name, args}], spots: [{cell_id, name, lat, lon, score}]}`. The frontend uses `spots` to highlight or fly to locations on the map.
- `backend/app/ai/chat.py`: a bounded loop of at most 4 tool rounds, with a timeout of about 15 s. It reuses the client setup and the system instruction about untrusted input from `_generate_json`. It uses Gemini's `tools=[...]` with these functions:
  | Tool | Wraps |
  |---|---|
  | `geocode_place(name)` | Curated spot names in `grid_cells` first, then the Open-Meteo geocoding API (free, no key), then the nearest cell via `repo/cells.py` |
  | `best_spots(time?, near?, radius_km?)` | `repo/scores.py`, the same queries used by `/api/best` |
  | `spot_conditions(cell_id, time?)` | The same repo calls as `api/spots.py` (score, factors, conditions) |
  | `when_visible(object_name, night?)` | Calls `ephemeris.visible_objects` hourly across the night and returns the hours the object is above 20° |
  | `sky_tonight(date?)` | `ephemeris.night_summary` (moon, twilight, planets, Leonids) |
- `backend/app/api/chat.py`: `POST /api/chat`, rate limited per IP or token, registered in `api/__init__.py`.
- Tests: mock the Gemini client and check that the tool dispatch and the round limit work offline.

**Frontend:**
- `ChatPanel.tsx`: a floating "Ask the sky" button that opens a side sheet. It shows suggested prompts such as "Best spot tonight near Buffalo?", "When is Orion up?", and "Will the Leonids be visible?"
- When a reply includes `spots`, the map flies to them and pulses their markers. This link between the chat and the map is what will impress judges.

**Estimate:** about 5–7 hours (backend 3–4, frontend 2–3).

---

## Spice ideas (ranked by payoff for the effort)

A. **Real constellation identification with astrometry.net (plate solving)** (Best AI/ML, Spirit)
- The free nova.astrometry.net API takes a photo and returns the exact sky coordinates and the constellations and bright stars actually in the frame.
- In the worker: solve the photo first, then pass the **solved** objects to Gemini as confirmed facts. Gemini keeps the description, sky quality, and Milky Way tasks.
- Pitch: *"We don't ask an LLM to guess the stars. We mathematically solve the photo, then let the LLM describe it."*
- The API can overlay constellation lines on the image, which makes the story viewer striking.
- Solving is asynchronous and takes about 30 s to a few minutes, which fits the existing pending/poll flow. Effort: about 3–4 hours.

B. **Close the loop: community photos validate the model** (Best AI/ML, Radial Atoms)
- Every analyzed photo has a `score_at_capture` and Gemini's `sky_quality`.
- Add a small "Model vs. reality" view that plots the photos' sky quality against the predicted score. This is Architecture.md §6.4, made visible.
- Even with a few seeded demo photos, it shows a live sensor loop. Effort: about 2 hours.

C. **"Tonight's best" button and dusk/dawn ticks on the slider** (UI/UX, Tiger Data)
- **Built (Nov 8).** The data exists in `/api/best` and `/api/sky-events`. Effort: about 1–2 hours.

D. **Red night-vision mode** (UI/UX, Spirit)
- A CSS filter toggle across the whole app. Easy to demo, and real stargazers care about it. Effort: about 30 minutes.

E. **Color-blind-safe palette option** (UI/UX)
- Fixes the open item in Architecture §10.1. Switch `SCORE_STOPS` in `frontend/src/lib/scoreColors.ts` to a viridis or cividis toggle. Effort: about 30 minutes.

F. **Forecast-drift chart in the spot panel** (Tiger Data, Radial Atoms)
- **Built (Nov 8).** `/spots/:id/drift` already exists. Use Recharts to show how tonight's prediction changed over time. This is the "sensor log" demo beat. Effort: about 2 hours, and it depends on the spot panel.

G. **ISS passes** (Spirit)
- CelesTrak TLE data with Skyfield in `sky_events`. Adds a "the ISS flies over at 6:42 PM" moment. Effort: about 2 hours.

---

## Recommended order (assumes about 14–16 build hours remain)
1. Fix the Gemini key, then create the Vultr bucket and CORS rule (0–1 h). Both features are blocked until this is done.
2. **In parallel:** Role A builds the upload flow, photo layer, and story viewer. Role B and C build the `/api/chat` backend and tools.
3. Role C adds astrometry.net solving to the photo worker (spice A).
4. Role A builds the chat panel with map fly-to, then night mode, the palette toggle, and "Tonight's best" (C, D, E).
5. If time allows: the model-vs-reality view (B) and the drift chart (F).
6. Seed 5–10 real WNY night-sky photos for the demo before judging.

## Verification
- **Backend:** `cd backend && .venv/bin/python -m pytest -q tests ../data/tests` (offline). Add new tests for the chat tool dispatch and the photo `since` filter.
- **Gemini:** `data/live_gemini_smoke.py` passes both calls.
- **Photos, end to end:** with Flask on :5001 and Vite on :5173, upload a real JPEG with GPS EXIF. It should reach the bucket, then `ai_status` should move from `pending` to `done`. The pin should appear on the map, the story viewer should open, and votes should persist.
- **Chat:** asking "Where should I go to see Orion tonight from Buffalo?" should return a reply that cites a real score and time, and the map should fly to the named spot. Check the `tool_calls` in the response to confirm the answer is grounded.
- **Frontend:** run `npm run build` and `npm run lint`, then test manually in a browser at desktop and phone widths.
