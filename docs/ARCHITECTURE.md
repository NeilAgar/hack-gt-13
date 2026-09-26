# Pop Quiz: product and architecture spec

## What it is
Pop Quiz is a web app built on public CMS data. For every Georgia nursing home, it measures whether staffing rises around state inspections and falls back afterward. It also gives state regulators an inspection calendar that homes can't predict.

There are two modes on one backend:
- **Family mode** is public.
- **Regulator mode** is the demo login.

## How it works for users

### Family mode (public)
1. The user searches a city or a home name, e.g. "Savannah," and sees a map with pins colored by **Staffing Consistency**, next to each home's Care Compare stars.
2. On a facility page:
   - **Headline:** "In the 2 weeks before past inspections, nurse hours per resident were 11% higher than a month later (range 6–16%, based on 7 inspections)."
   - **Chart:** a typical staffing curve across the inspection cycle, with inspection days marked.
   - **Plain-language explanation** written by Grok from the computed numbers.
   - **Questions to ask on a tour:** weekend staffing, agency staff, RN coverage at night.
3. The user can also call or talk to a voice line (Grok Voice): "How does Sunrise Manor staff when inspectors aren't around?"
4. Family mode never shows when the next inspection is likely.

### Regulator mode (demo login)
1. **Statewide table:** each facility's score, uncertainty, risk signals and **Trophy Check** flag. The flag means the home qualifies for CMS's lighter Risk-Based Survey even though its staffing rises only around inspections.
2. **Scheduler:** set inspector capacity per month, then press **Generate**. The app returns this month's randomized inspection list plus each facility's probability of being chosen.
3. **Simulation:** gaming exposure under the current near-annual rhythm vs. the Pop Quiz schedule, at the same inspector budget.
4. **Predictability panel:** internal only. Shows how guessable each home's next inspection is today.
5. Export to CSV.

## Architecture

```
 CMS public APIs                     Offline pipeline (Python)                  Serving
 ─────────────────                   ──────────────────────────                 ────────
 PBJ Daily Nurse Staffing ─┐
 Inspection Dates (svdt-c123) ─┼─▶ 1 Ingest → Parquet/DuckDB
 Provider Info (+stars, addr) ─┤   2 Daily HPRD + residuals
 Health Deficiencies ─┘            3 Event study → score + CI (per facility)   FastAPI ─▶ Next.js
                                   4 Hazard model (internal)                    │         Family / Regulator
                                   5 Stackelberg LP → marginals → sampled plan  │         Map + charts
                                   6 Simulation (status quo vs Pop Quiz)        │
                                   7 Trophy Check join                          ├─▶ Grok: explanation
                                        │                                       └─▶ Grok Voice line
                                        └──▶ precomputed tables (facility, curve, schedule)
```

### 1. Data
- **PBJ Daily Nurse Staffing**, from data.cms.gov, filtered to Georgia. Covers 2017 Q1 – 2026 Q1 and updates quarterly, with one API dataset ID per quarter (see data.cms.gov/data.json). Fields: CCN, WorkDate, MDScensus, and RN / LPN / CNA hours, including contract staff.
- **Inspection Dates:** CCN, survey date, survey type, cycle. Keep **Health Inspection Standard** only. ⚠ The current file (`NH_SurveyDates_Jul2026.csv`) holds only the **last 3 cycles (~2023–26)**. For 2017–22, stitch the monthly snapshots from the Provider Data archive (each has 3 cycles) and dedupe on CCN + date. Minimum viable: 3 surveys per home, with more shrinkage.
- ⚠ **"Survey Date"** is documented only as "Date of the Inspection", with no start/exit distinction. Check it empirically: align the PBJ spikes to the date. If they peak on days −4 to 0, the date is the exit date, so shift the windows.
- **Capacity for the scheduler:** no public roster of inspectors. Use Georgia's historical count of standard surveys per month as the capacity proxy.
- **Risk-Based Survey eligibility:** no public eligibility list found. Use the star-rating and citation proxy and label it as such.
- **Provider Info:** name, address, star ratings, ownership. Geocode if coordinates are missing.
- **Health Deficiencies:** harm-level citations, used for risk weights and the Trophy Check.
- All of it is small for Georgia (~356 homes; a few million rows). DuckDB on a laptop is enough.

### 2. Survey-Responsiveness Score
- **Daily HPRD** (nurse hours per resident day) = (RN + LPN + CNA hours) / census.
- **Residualize:** subtract each facility's day-of-week mean and a rolling 90-day trend, so weekend dips and seasonal drift don't read as gaming.
- **Windows** relative to the inspection start date (day 0):
  - **pre-ramp:** days −14 to −1 (the gaming signal, since inspections are unannounced);
  - **surge:** days 0 to +3 (includes staff called in after inspectors arrive; shown, not scored);
  - **baseline:** days +28 to +56.
- **Raw score** per facility = the mean over its inspections of (pre-ramp − baseline), as a percentage of baseline HPRD.
- **Shrinkage (empirical Bayes):** score = w·raw + (1−w)·state mean, where w = τ²/(τ² + σᵢ²). Homes with few or noisy inspections are pulled toward the state average.
- **Confidence interval:** bootstrap across each facility's inspections.
- **Public label:** "Staffing Consistency": High / Watch / Low, with the number and its interval.

### 3. Predictability (hazard) model: internal only
- A discrete-time logistic hazard model of P(inspection in week t | weeks since the last one, state, month).
- It should reproduce the concentration of inspections 40–60 weeks after the last one.
- Its outputs feed the scheduler and the regulator panel only. They are never exposed to Family mode or the public API.

### 4. Scheduler (Stackelberg)
- **Defender:** the state survey agency chooses each facility's inspection probability for the month, cᵢ ∈ [0, 1], with Σcᵢ ≤ K (the month's inspector capacity).
- **Attacker:** each facility cuts staff in the months it believes it is least likely to be inspected. Its payoff from cutting is weighted by its responsiveness score, so the homes that game hardest cause the most damage when missed.
- **Risk weight:** residents × (score + harm-citation history + weekend-dip and agency-staff signals).
- **Solve:** a linear program in the style of ORIGAMI (the standard security-game solver), using scipy or PuLP. With ~356 targets it solves in seconds.
- **Legal constraints:**
  - force cᵢ = 1 when a facility reaches 15.9 months since its last inspection;
  - capacity K is set so the statewide average stays at or below 12.9 months;
  - avoid the same calendar month as the facility's last inspection;
  - mark at least 10% of sampled inspections for off-hours starts.
- **Sample:** comb or systematic sampling turns the probabilities into a concrete list that uses exactly K inspections.
- **Fallback:** if the LP slips, use risk-weighted proportional probabilities under the same constraints.

### 5. Simulation
- Each facility responds as well as it can to what it believes: the historical hazard in the status-quo case, the Pop Quiz probabilities in ours.
- **Metric:** resident-weighted "undetected shirk-months" over 3 years, compared at the same total inspection count.
- Label it "illustrative model." Cite NBER's ~92 lives a year as the external benchmark and don't claim lives saved ourselves.

### 6. Trophy Check
- Build a proxy for CMS Risk-Based Survey eligibility: 5-star overall rating, staffing ≥ 3 stars, and no harm or immediate-jeopardy citations.
- Flag proxy-eligible homes whose score lower bound is above zero.

### 7. Serving and LLM
- **FastAPI** serves the precomputed tables:
  - `GET /facilities?q=`
  - `GET /facility/{ccn}` (score, CI, curve, stars)
  - `POST /schedule` (regulator only: capacity → sampled plan + probabilities)
  - `GET /simulate`
- **Frontend:** Next.js, Leaflet or Mapbox for the map, Recharts for the staffing curve.
- **Grok:** gets a JSON of the computed facts and returns a 3-sentence explanation.
  - Guardrail: it may only restate the numbers it is given, never invent them.
  - It uses "survey-responsive staffing," never "gaming," for named homes.
- **Grok Voice:** the same facts endpoint behind a voice agent.
- **Built with Cursor**, which is required for the SpaceXAI prize.

## Guardrails
- The public side never exposes predicted inspection timing.
- Every facility page shows uncertainty and a note that PBJ is self-reported: OIG (2026) found about 5% of RN hours were unsupported.
- Credit Chen & Dillender (NBER w34037) and Gandhi, Olenski & Shi (NBER w34491) in the app and on Devpost.

## Team split (4)
See docs/TEAM-PLAN.md for the full timeline.
- **A, data (`pipeline/`):** ingest, HPRD, event-study score, curves. First Georgia curve by ~01:00 Saturday (go/no-go).
- **B, models (`models/`):** hazard model, Stackelberg LP, sampler and constraints, simulation.
- **C, backend + integrator (`api/`, `hardware/`):** FastAPI, Grok explain and voice, Makefile/CI, merges, optional Call Clock.
- **D, frontend + story (`web/`):** Next.js family and regulator modes, map, charts, pitch and Devpost.
- Feature freeze candidate Saturday 18:00–21:30, bugfix only after. Devpost and video by Sunday 08:00.

## 3-minute demo
1. **Hook:** one Georgia home's staffing curve peaks right before inspections.
2. **Evidence:** the NBER predictability chart.
3. **Family mode:** search Savannah, open a facility page, play the voice question.
4. **Regulator mode:** Trophy Check list, set capacity, press Generate, run the simulation before vs. after.
5. **Close:** "Economists proved it. We built the score, the schedule, and the warning label."
