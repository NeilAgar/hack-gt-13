# Requests from owner B (models/)

## For C (api/)

`python -m models` (or `make models`) writes:

- `data/processed/hazard.parquet` — contract columns `ccn, weeks_since_last, p_survey_week, p_next_60d` (full week grid per home). For `GET /predictability`, join each CCN to its **current** `weeks_since_last` from `surveys` (last survey vs as-of date), or use `data/processed/predictability.json` which is already current-state rows `{ccn,name,p_next_60d}`.
- `data/processed/schedule.json` — same shape as `POST /schedule` (`month, capacity, selected, probs`). Extra key `solver` is `"lp"` or `"proportional"` (ignore in the HTTP response if you want a strict contract).
- `data/processed/simulate.json` — same shape as `GET /simulate`, plus `capacity`, `illustrative`, and `note`. Serve the four contract keys; keep the note for regulator copy.

Until A's parquet exists, models runs on synthetic GA homes **including** the six fixture CCNs (`115994`–`115999`). Hazard/schedule/sim are **not** family-facing.

CLI: `python -m models --month 2026-10 --capacity 7 --seed 0`

## For A (pipeline/)

When `data/processed/facilities.parquet`, `surveys.parquet`, and `scores.parquet` are all present, models will use them instead of synthetic data. Please keep `ccn` as a 6-char string with leading zeros. Optional on scores: `agency_share` (contract hours / total nurse hours); we treat missing as 0.

Capacity proxy (open in DECISIONS.md): until we have Georgia's monthly count of health-standard surveys, we set `K = round(n_facilities / 12.9)`. If you can emit `n_standard_surveys` by calendar month, we will switch to that as K.

# Requests from owner C (api/)

## For B (models/)

The API now calls `build_schedule` and `simulate` live for `POST /schedule` and `GET /simulate` (see `api/data.py`). Found while wiring it up, on synthetic data (80 homes):

1. **Capacity above what can be scheduled:** `capacity=200` returns `capacity: 200` with only 71 `selected`. The API now reports `capacity = len(selected)` in that case, but could `build_schedule` cap it too, so both agree?
2. **Low capacity makes Pop Quiz look worse:** `simulate(capacity=1)` gives `reduction_pct: -16.0`; it turns positive by K=6. Is that expected? If so, the regulator UI should explain it, or the capacity slider should start at a sensible minimum.
3. **PuLP deprecations:** `LpVariable(...)` and `PULP_CBC_CMD` print ~6,000 DeprecationWarnings per test run under PuLP 3.x and will break in PuLP 4.0. Pinning `pulp<4` in `models/requirements.txt` would be enough for the hackathon.
4. **Not reproducible:** a fresh `python -m models` on the same inputs gives `p_next_60d` values up to ~0.0002 different from the committed `predictability.json`. Small, but if the demo numbers should match run to run, fix the hazard fit's seed or solver settings.
