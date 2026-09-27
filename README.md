# ML FORGE

### Diagnose. Decide. Deploy.

A complete, working implementation of the ML Forge event platform: a
team-based ML competition where two-person teams diagnose and repair a
failing AI system under a countdown clock, across two independently
scored rounds.

This package contains a tested FastAPI backend, a precomputed ML engine
(no live model training during the event — real models are trained ahead
of time with **Orange3**), and a React frontend implementing the full
participant and admin experience. The backend and frontend are served as
a **single process** — build the frontend once, and the FastAPI server
serves both the API and the built UI from one port.

---

## What's included

```
ml/
├── backend/
│   ├── app/                    FastAPI application
│   │   ├── data/                Generated datasets + precomputed results
│   │   ├── routers/             rooms, teams, mission, admin, leaderboard
│   │   ├── models.py             SQLAlchemy ORM models
│   │   ├── schemas.py            Pydantic request/response schemas
│   │   ├── content.py            Datasets, twist text, Black Box question bank
│   │   ├── scoring.py            Deterministic deduction-based scoring engine
│   │   ├── core.py               Room/team/timer helper functions
│   │   ├── ml_lookup.py          Precomputed-results lookup + live threshold recompute
│   │   └── main.py               App entrypoint — also mounts the built frontend
│   ├── scripts/
│   │   ├── generate_datasets.py  Builds MEDIVISION-X and FRAUDNET-X with the 4 traps
│   │   └── precompute_results.py Trains every valid pipeline combination via Orange3
│   ├── tests/
│   │   ├── test_scoring_unit.py  Unit tests for the scoring engine
│   │   └── test_full_event.py    Full 12-team, 2-round event simulation via the live API
│   ├── requirements.txt
│   ├── setup.sh                  One-shot: venv + deps + generate data + precompute
│   ├── run.sh                    Starts the API server (also serves the built frontend)
│   └── run_tests.sh              Runs the full backend test suite standalone
│
└── frontend/
    ├── src/
    │   ├── pages/                Landing, TeamEntry, Mission, Admin, Leaderboard
    │   ├── components/            PageBackground, VideoBackground
    │   ├── lib/api.js             Central API client
    │   ├── App.jsx / main.jsx
    │   └── index.css              Dark charcoal + green Minecraft-metaphor theme
    ├── public/assets/             Background art (images + the Team Entry video)
    ├── package.json
    ├── .env.development           Local-dev-only API base override (not used in production build)
    └── setup.sh
```

---

## Quick start

Because the backend serves the built frontend itself, this is **one process**, not two.

### 1. Build the frontend

```
cd frontend
npm install
npm run build
cd ..
```

### 2. Set up and start the backend

```
cd backend
./setup.sh      # creates venv, installs deps, generates datasets, precomputes ML results
./run.sh or uvicorn app.main:app --reload --port 8000       # starts the API on http://localhost:8000 — also serves the built frontend
```

Open **http://localhost:8000** — that's the whole app.

The first run of `setup.sh` generates `MEDIVISION-X` (Round 1) and
`FRAUDNET-X` (Round 2) with the four intentional traps (target leakage,
irrelevant ID column, missing values, class imbalance), then trains
**every** valid combination of imputation × scaling × feature-toggle ×
model (288 result entries per dataset) using **Orange3** learners, once,
ahead of time. During the live event, clicking "Run Model" is a
dictionary lookup against this precomputed table — no live training
happens under event load, which is what makes it safe for many teams to
hit "Run Model" at the same moment. A decision-threshold slider in Model
Forge *is* computed live — but only as cheap arithmetic over each
config's cached prediction probabilities, never a retrain.

### Local frontend development (optional)

If you want frontend hot-reload while developing, run it as its own dev
server instead of the built version:
```
cd frontend
npm run dev      # http://localhost:5173, proxies API calls per .env.development
```
`.env.development` points this dev server at `http://localhost:8000` for
the backend. This file is **not** used by `npm run build` — the
production build defaults to calling whatever origin served the page,
which is what makes the same build work unchanged on a LAN machine, on
Render, or anywhere else.

---

## Running the event

1. Go directly to **`/#/admin`** (this is intentionally not linked
   anywhere in the navigation — only reachable by typing the URL) →
   enter a room key (e.g. `LIVE_2026`) and a name → **Create Room**.
2. Teams open the app, enter the same room key, and register their team
   name at Team Entry. If a team's browser disconnects or refreshes,
   re-entering the *same team name* resumes their workspace exactly
   where they left off — state lives server-side, keyed to team
   identity, not the browser session.
3. Admin clicks **START ROUND 1** — the 30-minute timer starts for every
   registered team simultaneously, and all teams see the same dataset.
4. Around the 15-minute mark, admin clicks **RELEASE TWIST** — all teams
   see the same mission-update banner.
5. At 30:00 (or when admin clicks **LOCK SUBMISSIONS**), no further
   changes are possible. Admin clicks **CALCULATE SCORES**, then
   **ADVANCE TOP 10**.
6. Admin clicks **START ROUND 2** for the 10 qualifying teams, and
   **RELEASE INCIDENT** partway through, following the same pattern.
7. Admin clicks **LOCK FINAL SUBMISSIONS**, then **CALC SCORES R2**,
   then **SHOW WINNER**.

The **Leaderboard** page (`/#/leaderboard`, linked in the nav) can be
projected live. It has two independent tabs:
- **Round 1 — Qualifying**: all registered teams, ranked by Round 1
  score. Decides who advances. Nothing here carries into Round 2.
- **Round 2 — Final**: only the 10 qualified teams, ranked by Round 2
  score alone. Rank 1 here is the winner.

Round 1 and Round 2 scores are **never blended or weighted together** —
each round is scored on its own 0–100 scale, and each round's score only
does the one job it's responsible for (qualifying, or winning).

### Rooms, not TEST/LIVE

Every team, score, and leaderboard entry is scoped to a `room_key`. Use a
disposable room key (e.g. `REHEARSAL`) for rehearsals — nothing there
will ever appear under a different room key like `LIVE_2026` on event
day. Just create a fresh room for the real event; rehearsal data is
structurally isolated, not just hidden by a status flag.

---

## Scoring engine

Every team starts at 100 points **per round**, and every deduction is
computed from logged, server-side state — never from a client claim:

**Round 1** (skipped investigation panels, wrong imputation choice,
leakage/irrelevant feature retained, wrong metric after the twist, weak
final performance, slow twist response, skipped post-twist feature
check) → produces a single **Round 1 score**, used only to rank the
top-10 cutoff.

**Round 2** (same panel/leakage/performance/twist-response checks
re-applied to the new dataset, plus the Black Box challenge) → produces
a completely separate **Round 2 score**, used only to rank the final
winner.

There is no judge-scored "defense" component and no weighted combination
of the two rounds — each round's score is the whole story for the one
thing it's responsible for.

---

## Testing

```
cd backend
./run_tests.sh
```

This runs:
- **`test_scoring_unit.py`** — isolated checks that every deduction
  category fires for the exact right amount (e.g. retaining the leakage
  feature costs exactly -20, wrong imputation costs exactly -15).
- **`test_full_event.py`** — spins up a temporary server and simulates a
  full 12-team event through both rounds via the live API: registration,
  disconnect/resume, investigation, preprocessing, model runs, the
  twist, submission locking, scoring, top-10 advancement, Round 2, Black
  Box, and final Round-2-only ranking. Confirms a team making correct
  decisions clearly outscores one that ignores the traps and the twist,
  and confirms no blended `overall_score` exists anywhere in the result.

**All 47 checks pass as of this build.**

---

## Deploying elsewhere (Render, or a LAN machine)

Because the backend serves the built frontend directly, deployment is
the same shape everywhere — one process, one port:

1. `cd frontend && npm install && npm run build`
2. `cd backend && pip install -r requirements.txt`
3. Start with `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`
   (`run.sh` already does this — Render provides `$PORT` automatically;
   locally/on a LAN machine it falls back to 8000)

`app/data/precomputed_results.json` and the two dataset CSVs are
committed to the repo rather than regenerated on every deploy — this
avoids re-running Orange3 training in an unfamiliar build environment
right before an event. Only run `precompute_results.py` again if the
datasets or scoring logic actually change.

On a LAN, every team's browser points at the host machine's local IP
(e.g. `http://192.168.1.50:8000`) instead of `localhost` — make sure
that port is allowed through the host machine's firewall.

---

## Known limitations / things to decide before a real event

- **Pause/resume timer control** is not implemented in the admin panel —
  the timer is a pure `(start_time + duration) - now` calculation. To
  extend a round for a real technical failure, adjust
  `round1_duration_seconds` / `round2_duration_seconds` directly via the
  admin API or database.
- **Investigation view** shows summary statistics from the full public
  dataset (not a per-team train/test split) — all teams see identical
  missing-value and class-distribution numbers, which is intentional.
- **No tab-switch detection and no per-team passwords yet** — both are
  planned but not yet implemented in this build.
- No authentication beyond team-name-within-room uniqueness — sufficient
  for a supervised in-person event, not intended for public internet
  exposure without additional hardening.