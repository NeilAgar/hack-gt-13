# DECISIONS.md

One line per decision: what, who, when. The Devpost write-up draws on this.

| Decision | Owner | Status |
|---|---|---|
| Contract v1 frozen. `/simulate` `popquiz` has the same field as `status_quo`: `undetected_shirk_resident_months`. | all | decided |
| Hardware (Call Clock) cut from scope. | all | decided |
| Keep the MIT `LICENSE` in the repo. | all | decided |
| Staffing Consistency: **Low** if `ci_low > 0`; **Watch** if the interval includes 0 and `ci_high > 5`; **High** otherwise (`ci_low <= 0` and `ci_high <= 5`). Trophy = `rbs_proxy_eligible` AND `ci_low > 0`. | A | decided 2026-09-26 |
| Ranges are shrunk by sqrt(w) (posterior SD), not w; see PR #18 follow-up. | A | decided 2026-09-26 |
| Family/API headline must not say staffing rose "before inspections." Scored window −14..−1 on the CMS exit date includes the inspection. Wording: "In the 14 days through the last day of past inspections, nurse hours per resident were X% higher/lower than a month later (range …)." | A | decided 2026-09-26 |
| CMS `Survey Date` is the **exit date**, not the start date. GA state-average `hprd_resid` peaks on rel_day −1 (then −2 and 0) and collapses by +1. Architecture rule: peak on −4..0 ⇒ exit. Shift event-study windows so day 0 is inspection start (exit minus typical survey length) in a follow-up; do not treat CMS date as start. Evidence: `data/processed/ga_state_curve.png`, ~570 facility-surveys/day, PBJ 2024Q1–2026Q1. | A | decided 2026-09-25 ~22:30 |
| Capacity proxy for the scheduler. | B | open |
