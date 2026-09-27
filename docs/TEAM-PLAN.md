# StaffTrace: 24-hour team plan (Fri 21:30 → Sat 21:30)
The remaining hours to the 08:00 Sunday deadline are for polish, Devpost, video and rehearsal.

## Roles (each person drives 1–2 agents inside their own directory)
| | Owner of | Deliverable | Agent-friendly tasks | Human judgment needed |
|---|---|---|---|---|
| **A: Data** | `pipeline/` | facilities, daily_staffing, surveys, scores, curves | download scripts, parsers, archive stitching, parquet writers | survey-date anchor, residualization choices, placebo test |
| **B: Models** | `models/` | hazard, scheduler, simulation | LP formulation, sampler, constraint code, sim harness | game payoffs, shirking model, sanity of results |
| **C: Backend + integrator** | `api/` | FastAPI per contract, Grok explain, voice, Makefile/CI | endpoints, fixtures server, Grok prompt | guardrails, merges, keeping `main` green |
| **D: Frontend + story** | `web/` | Family and Regulator modes, map, charts; owns the pitch | components, pages, styling | UX copy, demo flow, Devpost narrative |

## Timeline
**21:30–22:30, everyone (no coding yet)**
- Commit AGENTS.md (copy it to CLAUDE.md and .cursorrules), docs/CONTRACTS.md, fixtures/, Makefile stubs and .gitignore.
- Freeze contract v1. Each person creates a branch and a worktree.

**22:30–02:30, parallel build against the contract**
- **A:** pull Georgia PBJ (2017Q1–2026Q1, API filtered to GA), Inspection Dates and Provider Info. Stitch archived snapshots for older surveys.
  **Go/no-go by ~01:00:** a state-average staffing curve around survey dates. Decide whether the survey date is the start or exit date. Post the chart in team chat.
- **B:** build the hazard model and Stackelberg LP on *synthetic* surveys (fixtures), with constraints: forced at 15.9 months, capacity, no same-month repeat, ≥10% off-hours.
- **C:** FastAPI serving fixtures for every endpoint; Grok /explain with a facts-only prompt; `make demo`.
- **D:** Next.js skeleton, map, facility page with curve + CI, regulator shell, all on fixtures.

**Before sleeping:** start long agent jobs (archive download and stitching, full GA pull, LP parameter sweep) so they run overnight.

**02:30–08:00: sleep in two shifts** (A+C 02:30–07:00, B+D 03:30–08:00). Whoever is awake watches the jobs.

**08:00–13:00: real data in**
- A: scores and curves on real GA data; shrinkage + bootstrap CIs; **placebo test** using random fake survey dates, which should show no spike. This is our credibility slide.
- B: real surveys → hazard (should reproduce "74% of surveys fall 40–60 weeks after the last"); risk weights from scores and citations; simulation.
- C: swap fixtures for parquet; add regulator endpoints; add the voice line.
- D: wire to the real API; regulator mode (capacity slider → Generate, sim chart).
- **13:00 integration checkpoint:** end-to-end on real data on `main`. If it isn't there, cut scope (see below).

**13:00–18:00: stretch and polish**
- C: voice polish, API hardening, keep `main` green.
- A + B: cross-review each other's methods; pick 3 real GA facilities for the demo, checking their CIs are tight.
- D: design polish and copy; draft the Devpost write-up.

**18:00–21:30:** feature freeze candidate. First full demo rehearsal at 20:00, then fix list.
**After 21:30:** bugfix only; Devpost + 2–3 min video; final rehearsal. Submit well before 08:00.

## Cut order if behind
1. Voice → text explanation only.
2. Stackelberg LP → risk-weighted proportional probabilities (same constraints).
3. Archive stitching → 3 surveys per home with wider CIs.
4. Simulation → a static before/after chart.

## Agentic workflow rules of thumb
- **Contract first, fixtures always.** Nobody waits on anybody.
- One agent per worktree/branch. Agents never touch another owner's directory.
- Humans review every diff that touches statistics. A and B review each other.
- Give agents small, testable tasks with a done condition ("`make test-pipeline` passes and prints GA survey count").
- Before any parser: make the agent print real headers and check them against the CMS data dictionary.
- Merge to `main` at least every 2–3 h. C resolves conflicts; `main` must always run `make demo`.
- Keep a shared `docs/DECISIONS.md` (survey anchor, window sizes, capacity proxy) so the Devpost write-up nearly writes itself.
- SpaceXAI: make sure real work happens in Cursor and Grok is in the product (explain + voice). Screenshot as you go.
