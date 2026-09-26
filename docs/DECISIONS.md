# DECISIONS.md

One line per decision: what, who, when. The Devpost write-up draws on this.

| Decision | Owner | Status |
|---|---|---|
| Contract v1 frozen. `/simulate` `popquiz` has the same field as `status_quo`: `undetected_shirk_resident_months`. | all | decided |
| Hardware (Call Clock) cut from scope. | all | decided |
| Keep the MIT `LICENSE` in the repo. | all | decided |
| Staffing Consistency cutoffs (High / Watch / Low) on `score_pct` and CI. Fixture labels are illustrative until set. | A | due by 13:00 Sat integration checkpoint |
| CMS `Survey Date` is the **exit date**, not the start date. GA state-average `hprd_resid` peaks on rel_day −1 (then −2 and 0) and collapses by +1. Architecture rule: peak on −4..0 ⇒ exit. Shift event-study windows so day 0 is inspection start (exit minus typical survey length) in a follow-up; do not treat CMS date as start. Evidence: `data/processed/ga_state_curve.png`, ~570 facility-surveys/day, PBJ 2024Q1–2026Q1. | A | decided 2026-09-25 ~22:30 |
| Capacity proxy for the scheduler. | B | open |
