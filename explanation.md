# What I Built (Explained Like You're Little)

Hi! This is the story of the back part of Pleiades. You can't see the back part, but it does all the thinking. 🌟

---

## What is Pleiades?

Pleiades is a map. 🗺️
It shows you where the stars look the **prettiest** tonight.
Each square gets a number. A big number means "go here, lots of stars!" A small number means "too bright, not many stars."
You can also share pictures of the night sky. A smart robot tells you what's in your picture.

> *(Grown-up words: a web app that scores stargazing conditions across Western New York from 0–100 and hosts community sky photos analyzed by AI.)*

---

## The big pieces

### 🍳 The Kitchen
When you open the app, it's like ordering food at a restaurant.
You say "I want the star map, please!" and the kitchen cooks it up and sends it back.
The kitchen has a **menu** with 14 things you can order.

> *(Grown-up words: a Flask REST API with 14 routes under `/api`.)*

### 📓 The Giant Memory Notebook
We have a huge notebook that remembers **everything**.
It never erases old pages. Every time the weather changes its mind, we write the new guess on a **new** page.
So later we can flip back and say, "Yesterday we thought it would be cloudy, but today we think it'll be clear!"

> *(Grown-up words: a Tiger Data / TimescaleDB Postgres database. Forecasts and scores are stored in "hypertables", and every revision is kept, like a sensor log.)*

### 🟩 The Map Squares
We cut Western New York into about 350 little squares, like a checkerboard.
Each square gets its own star score.
Some special places, like big parks, get a ⭐ pin instead of a square.

> *(Grown-up words: a 0.1° grid stored in the `grid_cells` table, plus curated spots.)*

### 🤖 The Weather Robot
Every 3 hours, a little robot wakes up and asks the weather station:
"Will it be cloudy? Foggy? Windy?"
It asks about **every** square, then writes the answers in the notebook.

> *(Grown-up words: an ingest job that pulls Open-Meteo forecasts in batches, run by a systemd timer.)*

### 🌙 The Sun-and-Moon Clock
Once a day, another helper figures out where the sun and moon will be, hour by hour.
The sun has to be **way** down for stars to show. A big bright moon makes stars harder to see.
It also writes down fun sky events, like shooting-star showers! 🌠

> *(Grown-up words: the astro job writes sun/moon altitude and moon phase to `astro_conditions`, and meteor showers to `sky_events`.)*

### 🧮 The Star-Score Calculator
Every hour, the calculator looks at:
- clouds ☁️
- the moon 🌙
- city lights 💡
- haze 🌫️
- how high up the place is ⛰️

Then it gives every square a number from 0 to 100.
It also says **why**, like "you lost 20 points because of clouds."

> *(Grown-up words: the score job runs a vectorized scoring model and writes `score_snapshots`, including a factor breakdown. The model itself is a placeholder until the AI teammate finishes it.)*

### 📋 The Cheat-Sheet Pages
Reading the whole notebook would take forever.
So the notebook makes **cheat sheets**: "the best score for each square, every hour" and "the best score for each square, every night."
When you slide the time slider, the kitchen just reads the cheat sheet. Super fast! ⚡

> *(Grown-up words: TimescaleDB continuous aggregates, `cell_hourly_score` and the hierarchical `cell_nightly_best`.)*

### 📦 The Photo Cubbies
When you share a picture, it goes into a cubby, like at school.
The kitchen gives you a **special one-time key** that only opens one empty cubby.
You put your picture right in. The kitchen never has to carry it.

> *(Grown-up words: Vultr Object Storage, using presigned upload URLs so the browser uploads directly.)*

### 🧝 The Helper Elves
After your picture is in its cubby, little elves get to work:
1. They make a tiny copy of it, for the map.
2. They check which stars and planets were up in the sky when you took it.
3. They ask the smart robot, "What do you see?" They also tell it which stars were really there, so it doesn't make things up!
4. If the robot says "that's not the night sky," the picture gets hidden.

If something goes wrong, the elves try again (3 tries total) before they give up.

> *(Grown-up words: a background thread pool makes a thumbnail, builds an ephemeris-grounded list of candidate objects, and calls Gemini vision. Status: `pending` → `done`, `rejected` or `failed`.)*

### 🏷️ The Name Tags
To share pictures or vote 👍👎, you pick a name. You get a secret name tag.
Show the name tag and the kitchen knows it's you.

> *(Grown-up words: lightweight bearer-token auth. Only a hash of the token is stored.)*

---

## Who builds what?

There are three friends on the team:

- **Me (the back part):** the kitchen, notebook, robots, cubbies and elves.
- **The AI friend:** the *really smart* brains: the star-score math, the sun-and-moon math, and the robot that looks at pictures.
- **The screen friend:** the pretty map you actually touch and see.

I didn't know exactly how my friends would build their parts. So for the AI friend, I made **toy blanks**: pretend versions that work well enough to play with. My friend can swap in the real ones later, and nothing else breaks.

> *(Grown-up words: "seams". These are interface functions with placeholder bodies in `scoring/model.py`, `astro/ephemeris.py`, `ai/vision.py` and `ai/explain.py`.)*

For the screen friend, I wrote down the **menu**: exactly what you can order and what the food looks like.

> *(Grown-up words: Pydantic schemas form the API contract. It is documented in `backend-documentation.md`.)*

---

## How I built it

1. **First, I built the floor and walls myself:** the settings, the notebook pages, the menu, and the toy blanks.
2. **Then I made two helper copies of me.** They built at the same time, like two kids building two halves of a Lego castle.
   - Helper A built the kitchen, the cubbies and the elves.
   - Helper B built the weather robot, the calculator job, and the moving-in instructions for the real server.
3. **Then I checked their work.** I ran **112 little tests**, and they all passed! ✅

> *(Grown-up words: I wrote the foundation, ran two parallel subagents for the API and ingest/infra workstreams, then did an integration review and ran pytest: 112 passed, 1 skipped.)*

---

## What's not done yet

- 🧸 **We haven't played with the real big toy box yet.** The notebook has never been opened for real, because the toy box (Docker) was turned off. All the tests used pretend notebooks. The first real try might find a few oopsies.
  > *(Grown-up words: none of the SQL has been run against a real TimescaleDB yet.)*
- 🌙 **The moon guesser is wobbly.** It knows how full the moon is, but it's bad at guessing *where* the moon is. The AI friend will fix that with a real one.
  > *(Grown-up words: the placeholder ephemeris has a crude moon altitude.)*
- 📅 **One cheat sheet needs a newer notebook.** The "best of each night" cheat sheet might need a newer version of the notebook software.
  > *(Grown-up words: the nightly aggregate likely needs TimescaleDB 2.13 or later.)*
- 💾 **Nothing is saved yet.** All the work is on the table, but it isn't put away in the toy chest yet.
  > *(Grown-up words: nothing is committed to git.)*

The end! 🌌
