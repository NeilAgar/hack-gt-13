# Requests from owner B (models/)

## For C (api/)

`python -m models` (or `make models`) writes:

- `data/processed/hazard.parquet` — contract columns `ccn, weeks_since_last, p_survey_week, p_next_60d` (full week grid per home). For `GET /predictability`, join each CCN to its **current** `weeks_since_last` from `surveys` (last survey vs as-of date), or use `data/processed/predictability.json` which is already current-state rows `{ccn,name,p_next_60d}`.
- `data/processed/schedule.json` — same shape as `POST /schedule` (`month, capacity, selected, probs`). Extra key `solver` is `"lp"` or `"proportional"` (ignore in the HTTP response if you want a strict contract).
- `data/processed/simulate.json` — same shape as `GET /simulate`, plus `capacity`, `illustrative`, and `note`. Serve the four contract keys; keep the note for regulator copy.

Until A's parquet exists, models runs on synthetic GA homes **including** the six fixture CCNs (`115994`–`115999`). Hazard/schedule/sim are **not** family-facing.

CLI: `python -m models --month 2026-10 --capacity 7 --seed 0`

## For A (pipeline/)

When `data/processed/facilities.parquet`, `surveys.parquet`, and `scores.parquet` are all present, models will use them instead of synthetic data. Please keep `ccn` as a 6-char string with leading zeros.
