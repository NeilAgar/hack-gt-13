# StaffTrace

**Does a nursing home staff up only when the inspectors are watching?**

StaffTrace scores every Georgia nursing home on *survey-responsive staffing*: nurse staffing that rises around
state inspections and falls back afterward. It is built entirely on public CMS data. It gives families a
clearer rating for each home and gives regulators a randomized, risk-weighted inspection schedule that is
harder to anticipate.

Built at HackGT 13 (Social Good track + SpaceXAI).

---

## Contents
- [The problem](#the-problem)
- [What we found](#what-we-found)
- [What StaffTrace does](#what-stafftrace-does)
- [How the numbers are made](#how-the-numbers-are-made)
- [Pages](#pages)
- [Run it](#run-it)
- [Repository layout](#repository-layout)
- [API](#api)
- [Data sources](#data-sources)
- [Call Clock (hardware)](#call-clock-hardware)
- [Limitations and language rules](#limitations-and-language-rules)
- [Research credits](#research-credits)

---

## The problem

Most nursing-home inspections in the US happen roughly once a year, on a predictable rhythm. Research shows
that homes respond: staffing rises when an inspection is expected and falls once it is over. Inspectors then
see a better-staffed home than residents usually get, and the CMS star ratings that families rely on inherit
that blind spot. The health-inspection rating is observed during inspections, and the staffing rating uses
quarterly averages that barely register a few days' spike.

## What we found

Across **356 Georgia nursing homes**, using every day of CMS's Payroll-Based Journal (PBJ) staffing data
from January 2024 to March 2026 (**287,901 facility-days**) and CMS inspection dates:

- Statewide, nurse hours per resident run about **+4.3% higher on days −4 to −1** before an inspection ends,
  peaking around **+9% on the day before**, and are back to normal right after.
- There is no ramp-up before inspectors arrive (about +0.1%). The rise happens while inspectors are on site.
- A **placebo test** with random fake inspection dates shows a flat line, so the pattern is tied to real
  inspections and is not an artifact of the method.
- **350** homes have enough data to score. **30** stand out: across at least two inspections, their whole
  uncertainty range is above the typical Georgia home's change.

The evidence page (`/evidence` on the API) shows the statewide curve and the placebo side by side.

## What StaffTrace does

### For families: look up any home
- **StaffTrace rating (1–5★).** We start from CMS's overall star rating and take off **exactly one star**
  only when we are confident a home's staffing rises around inspections more than a typical Georgia home's.
  We never add stars. On current data, 22 homes are lowered by a star (8 more already sit at 1★).
- **Staffing change around inspections.** The home's score (for example +3.1%), always shown with its
  **uncertainty range** and the number of inspections behind it.
- **Staffing consistency label:** **High**, **Watch** or **Low** (explained below).
- **A staffing chart.** Shows the home against its own normal days, with a dotted line marking the top of
  its usual range. An Advanced view shows the full inspection cycle against the Georgia average.
- **A plain-language explanation.** Written by Grok (xAI) from the numbers only, with a template fallback.
- **Questions to ask on a tour**, such as weekend staffing, agency staff, and RN coverage at night.
- **A map** of every home, colored by StaffTrace rating.

### For regulators: a schedule that is hard to predict
- **Risk score.** One number per home that decides its chance of being picked (formula below).
- **Monthly inspection schedule.** Legally overdue homes are always included. The rest of the capacity is
  shared out by risk and then drawn at random, so no home can count on not being picked this month.

## How the numbers are made

### 1. Daily staffing (`pipeline/`)
For each home and day: **hours per resident per day (HPRD)** = (RN + LPN + nurse-aide hours) ÷ residents that
day. A typical Georgia home gets about 3.5 nurse hours per resident per day. We then remove each home's
usual day-of-week pattern, monthly level and 90-day trend. What remains is the *residual*: how far that day
is from normal for that home.

### 2. The score: an event study around each inspection
Day 0 is the date the inspection ended (the CMS survey date). For every inspection:

```
score = (average HPRD on days −14 to −1  −  average HPRD on days +28 to +56) ÷ (days +28 to +56) × 100
```

In words, the score is how much higher nurse hours per resident were in the 14 days through the day before
the inspection ended than about a month later. Scores are combined across a home's inspections and shrunk
toward the state average when the home has few inspections (empirical Bayes). A bootstrap (500 draws) gives
the **95% uncertainty range**. Extreme values from bad census days are capped.

### 3. Labels and the star drop

The Georgia average score is **about 1.2%**. The typical home already staffs up slightly around inspections,
so homes are judged against that average, not against zero.

| Label | Rule |
|---|---|
| **Low** | At least 2 inspections, and the whole uncertainty range is above the Georgia average |
| **Watch** | Not Low, but the range reaches above the Georgia average |
| **High** | The whole range is at or below the Georgia average |

Current counts: 30 Low, 295 Watch, 25 High. **The star drop uses exactly the Low rule**, so a lowered star
and a Low label always go together. The reasoning for every choice (one star, the 95% range, two
inspections, never adding stars) is in [`docs/DECISIONS.md`](docs/DECISIONS.md).

### 4. The normal-day line on the chart
The line sits at the 95th percentile of the home's own *ordinary* days (more than 60 days from any
inspection), averaged over as many days as the home has inspections, with a fixed seed per home so it never
moves. About 1 ordinary day in 20 crosses it by chance.

### 5. Risk score and schedule (`models/`)

```
risk = residents × (0.25 + S + C + 0.25 × W + T)
```

| Term | Meaning |
|---|---|
| **residents** | Average residents per day; harm is counted in resident-months |
| **0.25** | Every home keeps some chance of being picked |
| **S** | The home's rank (0–1) among Georgia homes on its staffing score |
| **C** | 0.1 per harm citation + 0.2 per immediate-jeopardy citation (3 years), capped at 1 |
| **W** | The home's rank (0–1) on weekend staffing drop, a weaker signal |
| **T** | Time since the last standard inspection: 0 until 12 months, rising to 1 at the 15.9-month legal limit |

The weights are judgement calls, not fitted to inspection outcomes. The reasoning is in `docs/DECISIONS.md`.

Each month's schedule:
1. Homes more than **15.9 months** past their last standard inspection are overdue by law and always get
   picked.
2. Other homes whose last inspection fell in the **same calendar month** get 0%, so the next visit can't be
   guessed by adding a year to the last one.
3. A linear program (ORIGAMI, from Stackelberg security games) spreads the remaining capacity so that no
   home is left with much more *uncovered risk* (risk × chance of not being picked) than any other.
4. A weighted random draw picks the actual list, and at least 10% of visits are marked for evenings or
   weekends.

The default capacity is **22 inspections a month**, Georgia's recent real pace. The minimum is the number of
homes overdue that month.

**Inspection backlog.** Under the schedule, the regulator page shows every home grouped by months since its last
standard inspection (0–6, 6–12, 12–15.9, overdue). A scatter plot shows each home's chance of being picked
in the current plan. The page also shows how many homes will cross the 15.9-month limit within a month, and
how many of those the plan is expected to leave uninspected. Each group opens to list its homes, with months
since the last inspection, the chance of being picked, and whether the home is on this month's list. The charts
update each time you click Generate.

## Pages

| URL | What |
|---|---|
| `http://localhost:3000/` | Home: search, map, and the list of homes (the StaffTrace name in the header links here) |
| `http://localhost:3000/facility/<ccn>` | One home: rating card, chart, explanation, tour questions |
| `http://localhost:3000/regulator` | Regulator view: risk score, schedule, inspection backlog with each group's list of homes. **Not linked anywhere on the site** and marked `noindex` |
| `http://localhost:3000/live` | Call Clock live view (needs the hardware or its simulator) |
| `http://localhost:8000/evidence` | Statewide evidence: event-study curve vs placebo |
| `http://localhost:8000/docs` | Interactive API docs (FastAPI) |
| `http://localhost:8000/voice` | Grok voice line (experimental, not linked; needs `XAI_API_KEY`) |

## Run it

**Needs:** Python 3.11+, Node 18.18+ (Next.js 15).

```bash
git clone https://github.com/NeilAgar/hack-gt-13.git
cd hack-gt-13
pip install -r api/requirements.txt -r pipeline/requirements.txt -r models/requirements.txt
(cd web && npm install)
make demo          # API on :8000 and web on :3000
```

Open **http://localhost:3000**. The processed Georgia data is committed in `data/processed/`, so no download
is needed. If it is missing, the API falls back to the sample data in `fixtures/`.

**Optional: Grok explanations.** Copy `api/.env.example` to `.env` at the repo root and set `XAI_API_KEY`.
Without a key, explanations use a built-in template, and everything else works.

| Command | What |
|---|---|
| `make data` | Rebuild `data/processed/` from CMS (downloads PBJ, inspection dates, provider info, citations) |
| `make models` | Rebuild model outputs (hazard, schedule, simulation) |
| `make api` / `make web` | Run one side only |
| `make demo` | Both |
| `make test` | Every test suite: `test-pipeline`, `test-models`, `test-api`, `test-web` |

**Pulling updates:** if `git pull` refuses because of `web/package-lock.json`, run `git stash`, then
`git pull`. If the site looks stale, delete `web/.next` and restart.

## Repository layout

| Folder | Owner | What |
|---|---|---|
| `pipeline/` | A (data) | CMS download, cleaning, HPRD, event study, scores, labels, curves |
| `models/` | B (models) | Inspection hazard model, risk weights, ORIGAMI scheduler, simulation |
| `api/` | C (backend) | FastAPI: facilities, StaffTrace rating, normal-day line, Grok explain, evidence, voice, Call Clock intake |
| `web/` | D (frontend) | Next.js 15 + React 19, Leaflet map, Recharts charts |
| `hardware/` | | Call Clock firmware (ESP32 / Arduino Nano), serial bridge, simulator, log tools |
| `docs/` | shared | [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) spec, [`CONTRACTS.md`](docs/CONTRACTS.md) data and API contract, [`DECISIONS.md`](docs/DECISIONS.md) why each choice was made |
| `fixtures/` | shared | Sample API responses used when real data is missing |
| `data/processed/` | | Georgia outputs (parquet, under 20 MB). Raw downloads stay out of git |

`AGENTS.md` (also `CLAUDE.md` and `.cursorrules`) holds the rules every AI coding agent on this repo follows.

## API

Base `http://localhost:8000/api`. The full contract is in [`docs/CONTRACTS.md`](docs/CONTRACTS.md).

| Endpoint | Who | Returns |
|---|---|---|
| `GET /facilities?q=&limit=` | public | Search results with rating, score, range, label |
| `GET /facility/{ccn}` | public | One home, plus its staffing curve, the Georgia curve and the normal-day line |
| `POST /explain {ccn}` | public | Plain-language explanation (Grok rephrases the given numbers only) |
| `GET /evidence` | public | Statewide event study and placebo |
| `POST /schedule {month, capacity, seed?}` | regulator | Selected homes and each home's probability |
| `GET /backlog` | regulator | Weeks since each home's last standard inspection, and whether it is overdue |
| `GET /simulate`, `GET /predictability` | regulator | Kept in the contract; no longer shown on the site |
| `POST /bedside`, `GET /bedside/*`, `GET /facility/{ccn}/bedside` | device / public | Call Clock events, live stream and log verification |

Regulator endpoints need the header `X-Demo-Role: regulator`. This is a demo switch, not real access control.
Responses carry `X-Data-Source: processed` or `fixtures`.

## Data sources

All public, from CMS:
- **Payroll-Based Journal Daily Nurse Staffing:** daily RN, LPN and aide hours and resident census.
- **Inspection dates:** Health Inspection Standard surveys (the day-0 anchor).
- **Provider Information:** names, locations, beds, residents, CMS star ratings.
- **Health Deficiencies:** harm (G–I) and immediate-jeopardy (J–L) citations.

PBJ staffing data is self-reported by the facilities.

## Call Clock (hardware)

A camera-free, microphone-free device for a resident's room. A light sensor watches the call light, and a
motion sensor watches the doorway. It logs **how long until someone arrived** and **calls cancelled with no
one entering**, as a hash-chained, HMAC-signed log. This makes the log tamper-evident, though not
tamper-proof. The data shows at `/live`. Wiring, flashing, a no-hardware simulator and the tamper demo are
in [`hardware/README.md`](hardware/README.md).

## Limitations and language rules

- **This is a signal, not proof.** A Low label means the pattern shows up clearly and repeatedly in the data.
  It does not establish intent or poor care on its own. We say *survey-responsive staffing*, never "gaming",
  about a named home.
- **The uncertainty range is always shown next to a score.**
- **PBJ is self-reported.** Census errors can distort single days; we cap extreme values.
- **Families never see predicted inspection timing.** Schedule and prediction endpoints are regulator-only.
- **Grok only rephrases numbers it is given.** It never produces a new figure, and there is a template
  fallback.
- **Risk weights are judgement calls.** They are not fitted to inspection outcomes.

## Research credits

The methods follow:
- **Chen & Dillender**, NBER Working Paper w34037
- **Gandhi, Olenski & Shi**, NBER Working Paper w34491

## License

MIT. See [`LICENSE`](LICENSE).
