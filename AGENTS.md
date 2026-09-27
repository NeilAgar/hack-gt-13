# AGENTS.md: rules for every AI agent working in this repo
(Also copy this file to CLAUDE.md and .cursorrules so every tool picks it up.)

## Project
StaffTrace (HackGT 13, Social Good track + SpaceXAI). It scores Georgia nursing homes on
"survey-responsive staffing": staffing that rises around state inspections and falls afterward.
It uses public CMS data: PBJ daily nurse staffing, and Inspection Dates (Health Inspection Standard surveys).
It also generates a randomized, risk-weighted inspection schedule for regulators (a Stackelberg game),
and gives families a lookup of each home's score.
Full spec: docs/ARCHITECTURE.md. Data and API contract: docs/CONTRACTS.md. **The contract is law.**

## Directory ownership (only edit your owner's directory)
| Dir | Owner | What |
|---|---|---|
| `pipeline/` | A (data) | ingest, cleaning, HPRD, event study, scores, curves |
| `models/` | B (models) | hazard model, Stackelberg scheduler, simulation |
| `api/` | C (backend) | FastAPI, Grok explain, voice |
| `web/` | D (frontend) | Next.js family + regulator UI |
| `docs/`, `fixtures/` | shared | change only through a PR labeled `contract` that all owners approve |

If your task needs a change outside your directory, **stop and write a note in `docs/REQUESTS.md`** instead of editing.

## Hard rules
1. Never change a schema in docs/CONTRACTS.md on your own. Code against the contract, and use `fixtures/` until real data lands.
2. Never invent CMS column names. Before writing any parser, download or open the file and print its header,
   and check it against the NH Data Dictionary / PBJ data dictionary.
3. No raw data or secrets in git. `data/raw/` and `.env` are gitignored. Small processed Georgia outputs in
   `data/processed/` (<20 MB) may be committed.
4. Every module needs a runnable smoke test: `make test-<module>`. `main` must always run `make demo`.
5. Small commits, one branch per person (`a/…`, `b/…`, `c/…`, `d/…`). Rebase on main and open a PR at least every 2–3 hours.
6. Language rules for anything user-facing:
   - Say "survey-responsive staffing", never "gaming", next to a named facility.
   - Always show the uncertainty range, and note that PBJ is self-reported.
   - Never expose predicted inspection timing in family mode or in public endpoints.
   - Credit Chen & Dillender (NBER w34037) and Gandhi, Olenski & Shi (NBER w34491).
7. The LLM (Grok) only rephrases numbers it is given. It must not produce any new figure.

## Commands
- `make data`: pipeline/ → data/processed/*.parquet
- `make models`: models/ → data/processed/hazard.parquet, schedule + sim outputs
- `make api`: uvicorn api.main:app --reload (port 8000)
- `make web`: cd web && npm run dev (port 3000)
- `make demo`: everything, using real data if present, otherwise fixtures

## Stack
Python 3.11, DuckDB/pandas, statsmodels/scikit-learn, scipy or PuLP (LP), FastAPI;
Next.js + Leaflet + Recharts; Grok API (xAI) + Grok Voice. Use Cursor for part of the build (SpaceXAI requirement).
