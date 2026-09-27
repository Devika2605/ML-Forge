# ML FORGE
### Diagnose. Decide. Deploy.

A complete, working implementation of the ML Forge event platform: a
team-based ML competition where two-person teams diagnose and repair a
failing AI system under a countdown clock, across two rounds.

This package contains a tested FastAPI backend, a precomputed ML engine
(no live training during the event), and a React frontend implementing the
full participant, admin, and judge experience.

---

## What's included

```
mlforge/
├── backend/
│   ├── app/                    FastAPI application
│   │   ├── data/                Generated datasets + precomputed results
│   │   ├── routers/             rooms, teams, mission, admin, leaderboard, judge
│   │   ├── models.py             SQLAlchemy ORM models
│   │   ├── schemas.py            Pydantic request/response schemas
│   │   ├── content.py            Datasets, twist text, question banks (source of truth)
│   │   ├── scoring.py            Deterministic deduction-based scoring engine
│   │   ├── core.py               Room/team/timer helper functions
│   │   ├── ml_lookup.py          Precomputed-results lookup helper
│   │   └── main.py               App entrypoint
│   ├── scripts/
│   │   ├── generate_datasets.py  Builds MEDIVISION-X and FRAUDNET-X with the 4 traps
│   │   └── precompute_results.py Precomputes every valid ML pipeline combination
│   ├── tests/
│   │   ├── test_scoring_unit.py  Unit tests for the scoring engine
│   │   └── test_full_event.py    Full 12-team, 2-round event simulation via the API
│   ├── requirements.txt
│   ├── setup.sh                  One-shot: install deps + generate data + precompute
│   ├── run.sh                    Starts the API server
│   └── run_tests.sh              Runs the full backend test suite standalone
│
└── frontend/
    ├── src/
    │   ├── pages/                Landing, TeamEntry, Mission, Admin, Judge, Leaderboard
    │   ├── lib/api.js             Central API client
    │   ├── App.jsx / main.jsx
    │   └── index.css              Dark charcoal + green Minecraft-metaphor theme
    ├── tests/
    │   └── test_browser_e2e.py    Real headless-browser test of the built UI
    ├── package.json
    └── setup.sh
```

---

## Quick start

### 1. Backend

```bash
cd backend
./setup.sh      # installs deps, generates datasets, precomputes ML results
./run.sh        # starts the API on http://localhost:8000
```

The first run of `setup.sh` generates `MEDIVISION-X` (Round 1) and
`FRAUDNET-X` (Round 2) with the four intentional traps (target leakage,
irrelevant ID column, missing values, class imbalance), then precomputes
**every** valid combination of imputation × scaling × feature-toggle ×
model (288 result entries per dataset) into a lookup table. During the
live event, clicking "Run Model" is a dictionary read against this table —
no live `sklearn` training happens under event load.

### 2. Frontend

In a second terminal:

```bash
cd frontend
./setup.sh
npm run dev      # dev server, or:
npm run build && npm run preview   # production build
```

By default the frontend points at `http://localhost:8000` (see
`frontend/.env`, `VITE_API_BASE`). Change this if the backend is hosted
elsewhere.

Open the printed local URL (typically `http://localhost:5173` for `dev`,
or `http://localhost:4173` for `preview`).

---

## Running the event

1. **Admin** (`/#/admin` in the frontend) → enter a room key (e.g.
   `LIVE_2026`) and a name → **Create Room**.
2. Teams open the app, enter the same room key, and register their team
   name at **Team Entry**. If a team's browser disconnects or refreshes,
   re-entering the *same team name* resumes their workspace exactly where
   they left off — nothing is lost, because state lives server-side keyed
   to team identity, not the browser session.
3. Admin clicks **START ROUND 1** — the 30-minute timer starts for every
   registered team simultaneously, and all teams see the same dataset.
4. Around the 15-minute mark, admin clicks **RELEASE TWIST** — all teams
   see the same mission-update banner.
5. At 30:00 (or when admin clicks **LOCK SUBMISSIONS**), no further
   changes are possible. Admin clicks **CALCULATE SCORES**, then
   **ADVANCE TOP 10**.
6. Admin clicks **START ROUND 2** for the 10 qualifying teams, and
   **RELEASE INCIDENT** partway through, following the same pattern.
7. Admin clicks **LOCK FINAL SUBMISSIONS**, then judges use the **Judge**
   panel (`/#/judge`) to score each finalist's defense against the fixed
   checklist.
8. Admin clicks **CALC SCORES R2**, then **SHOW WINNER**.

The **Leaderboard** page (`/#/leaderboard`) can be projected live; it
polls automatically and is scoped to the room key entered.

### Rooms, not TEST/LIVE

Every team, score, and leaderboard entry is scoped to a `room_key`. Use a
disposable room key (e.g. `REHEARSAL`) for rehearsals — nothing there will
ever appear under a different room key like `LIVE_2026` on event day. Just
create a fresh room for the real event; rehearsal data is structurally
isolated, not just hidden by a status flag.

---

## Testing

### Backend (standalone, no manual server needed)

```bash
cd backend
./run_tests.sh
```

This runs:
- **`test_scoring_unit.py`** — isolated checks that every deduction
  category fires for the exact right amount (e.g. retaining the leakage
  feature costs exactly -20, wrong imputation costs exactly -15).
- **`test_full_event.py`** — simulates a full 12-team event through both
  rounds via the live API: registration, disconnect/resume, investigation,
  preprocessing, model runs, the twist, submission locking, scoring,
  top-10 advancement, Round 2, Black Box, judge scoring, and final
  ranking. Confirms a team making correct decisions clearly outscores one
  that ignores the traps and the twist.

### Frontend (real headless-browser test)

With the backend running and the frontend built + served:

```bash
cd backend && ./run.sh &
cd frontend && npm run build && npm run preview -- --port 4173 &
pip install playwright && python3 -m playwright install chromium
cd frontend && python3 tests/test_browser_e2e.py
```

This drives an actual Chromium browser through the real UI: landing page,
team registration, investigating the dataset, preprocessing, running a
model, submitting, reloading to confirm resume works, and checking the
admin and leaderboard pages — not just API calls.

**All backend and frontend tests pass as of this build.**

---

## Design notes carried over from the event spec

- **Deduction-based scoring**: every team starts at 100 and loses points
  for specific, deterministic, server-verified mistakes — never a
  subjective judgment call except the one explicit judge checklist item in
  Round 2's final defense.
- **Precomputed ML results**: the combination space (imputation × scaling
  × feature toggles × model) is small and fully known in advance, so it's
  computed once during `setup.sh`, not live per click.
- **Hidden test split**: precomputation uses a fixed train/test split;
  participants only ever see investigation data drawn from the full public
  CSV, and final metrics are computed against the held-out test rows baked
  into the precomputed table — not something the frontend can see or
  influence directly.
- **Two engineers, one computer**: there is deliberately no multi-device
  session sync. One team = one browser session = one set of server-side
  state.
- **Team size is 2**, per the finalized design.

## Known limitations / things to decide before a real event

- **Pause/resume timer control** is not implemented in the admin panel —
  the timer is a pure `(start_time + duration) - now` calculation. If you
  need to pause for a real technical failure, extend by adjusting
  `round1_duration_seconds` / `round2_duration_seconds` directly via the
  admin API or database, per the "Platform Failure" rule in the event
  rules document.
- **Investigation view** currently shows summary statistics from the full
  public dataset (not a per-team train/test split) — this matches "same
  dataset for everyone" but means all teams see identical missing-value
  and class-distribution numbers, which is intentional per the design.
- **Round 2 confusion-matrix / client-requirement panels** referenced in
  the design spec are simplified to reuse the same investigation panels;
  a dedicated Round 2 "existing broken model" starting view could be added
  if you want Round 2 to visually start from a different screen than
  Round 1.
- No authentication beyond team-name-within-room uniqueness — sufficient
  for a supervised in-person event, not intended for public internet
  exposure without additional hardening.
