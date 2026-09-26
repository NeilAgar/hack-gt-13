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

# Requests from H (hardware/: Call Clock, branch `h/call-clock`)

`docs/DECISIONS.md` says "Hardware (Call Clock) cut from scope". This branch brings it back as an
**optional add-on**: nothing existing changes behaviour unless a device (or the simulator) posts events.
It needs the team's OK to merge. Details and the morning checklist: `hardware/README.md`, `hardware/DECISIONS.md`.

## For D (web/)

New files only; nothing is mounted yet:

1. **Facility page:** mount the panel, e.g. after "Questions to ask on a tour" in `app/facility/[ccn]/page.tsx`:
   ```tsx
   import { BedsidePanel } from "@/components/BedsidePanel";
   …
   <BedsidePanel ccn={ccn} />
   ```
   It is a client component: it fetches `{NEXT_PUBLIC_API_BASE}/facility/{ccn}/bedside?include_synthetic=true`,
   refreshes every 15 s, and shows "No Call Clock device has reported from this home yet" when empty.
   It uses the existing `panel / stat-row / stat / chip / meta / note` classes (no new CSS).
2. **`/live`** (`app/live/page.tsx`) is a self-contained full-screen view for the demo screen
   (fixed overlay on top of the layout). Optional: a nav link. Query params: `?ccn=`, `?demo=0`.
3. `npm test` (tsc + smoke + language rules) passes with both files.

## For C (api/)

1. I added **two lines** at the end of `api/main.py` (import + `app.include_router(bedside_router)`).
   Everything else is new files: `api/routes/bedside.py`, `api/bedside_store.py`, `api/tests/test_bedside.py`.
2. No new requirements: the event format lives in `hardware/eventlog.py` (stdlib only); `pandas` (already
   pulled in via models) is used only if `data/processed/surveys.parquet` exists.
3. The SSE broker is in-process: run uvicorn with **one worker** (the Makefile already does).
4. CORS only allows `http://localhost:3000`. If the demo screen opens the web app via a LAN IP, add that origin.
5. **Makefile:** please add
   ```make
   test-hardware:
   	$(PYTHON) -m pytest hardware/tests
   	cd hardware/firmware && pio test -e native
   ```
   (rule 4: every module needs `make test-<module>`). `data/bedside.sqlite` is gitignored.

## For all owners: proposed contract addition v1.1 "Bedside" (needs a `contract` PR)

```
## Bedside (Call Clock), v1.1
Event (one JSON object; device → API):
 {v:1, seq:int≥1, device_id, ccn, call_id, event:'call_on'|'entry'|'cancel'|'timeout', ts:ISO-8601 w/ offset|null,
  ms:int, wait_s:float(1 dp)|null, no_entry:bool|null, night:bool|null, synthetic:bool, prev_hash, hash, sig}
 hash = SHA256(prev_hash + canonical), sig = HMAC_SHA256(device_key, hash); see hardware/eventlog.py
POST /bedside  (one event or a list)
 → one:  {accepted:bool, verified:bool, reason:string|null, duplicate:bool}
 → list: {accepted:int, verified:bool, reason:string|null, results:[{device_id,seq,accepted,verified,reason,duplicate}]}
GET  /facility/{ccn}/bedside?include_synthetic=false
 → {ccn, n_devices, n_calls, median_wait_s, p_over_10m (0–1), night_median_wait_s, day_median_wait_s, n_no_entry,
    verified_all, n_unverified, synthetic_share (0–1), recent:[≤20 events + verified, reason, received_at_ms],
    by_days_since_inspection:[{bucket,median_wait_s,n}]|null}
GET  /bedside/stream?ccn=&backlog=10   text/event-stream; events 'bedside' (event + backlog, server_now_ms) and 'ping'
GET  /bedside/verify?device_id=        → {device_id, ok, n, first_bad_seq, reason} (no device_id → list for all)
GET  /bedside/events?device_id=        → [raw signed events, by seq]
```
Wording: "time until someone arrived", never "time to help". Nothing here exposes predicted inspection timing
(`by_days_since_inspection` looks only at past surveys).

# Requests from C (api/), Saturday 11:30

## For D (web/): the API now serves A's real tables; two display bugs with null values

`X-Data-Source: processed`. 356 real homes. Six have no score yet (e.g. 115711, 115718, 115733, 115778,
11A186, 11A200), and `label` is `null` for every home until A sets the High/Watch/Low cutoffs.

1. **Unscored homes show a made-up score.** `/facility/115711` renders "0% lower than a month later
   (range 0–0%, based on null inspections)". When `score_pct` is `null`, hide the headline, score and range
   and show "Not enough inspections with staffing data to score this home yet." (`/explain` already returns
   that text for these homes.) Map pins for them should be grey/neutral.
2. **`label: null` renders as "Watch".** Every home currently shows "Staffing consistency: Watch". When
   `label` is `null`, show no label (or "Label pending"), and use a neutral pin colour.
