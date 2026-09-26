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

## Adjusted star rating (contract v1.1, C, decided with the team 2026-09-26)

Goal: an overall rating that represents the home as it is on ordinary days, not only as inspectors see it.
`adjusted_star` = CMS overall rating, minus one star when a home shows clear, repeated survey-responsive staffing.
Code: `api/adjusted.py`. Each rule and its reason:

| Rule | Why this and not something else |
|---|---|
| Start from the **CMS overall rating** as published | It's the rating families already use and it bundles inspections, staffing and quality. We only add what CMS can't see. |
| Adjust by **exactly one star** | CMS builds its overall rating the same way: start from the health inspection rating, then add or subtract **one** star for staffing and **one** for quality measures (Five-Star Technical Users' Guide). Ours is one more step of that kind. A weighted blend would need weights we can't justify. |
| **Why a staffing step belongs there** | The health inspection rating that CMS's overall rating starts from is observed during inspections, and our statewide event study shows nurse staffing is +4.3% while inspectors are typically on site (peak +9% on day −1) and back to normal the next day; the placebo shows nothing. CMS's staffing rating uses quarterly averages, so a few days' spike barely moves it. |
| Downgrade only if **`ci_low` > the Georgia average** (1.2%), not `ci_low > 0` | CMS stars rank homes against each other, and the typical Georgia home already staffs up a little around inspections. Scores are also shrunk toward that positive average, so "above zero" mostly flags average homes (93), while "clearly above the average" flags homes that stand out (30). The average is the one A's pipeline shrinks toward (mean `raw_pct`), so the comparison uses the pipeline's own reference point. |
| Use the **95% range** (`ci_low`), not the point score | We are naming real homes, so a downgrade needs the whole range above the average, not just the estimate. The range is A's bootstrap (2.5th–97.5th percentile). |
| Require **at least 2 inspections** | With one inspection, the range is built from days inside that single inspection, so it can't show whether the pattern repeats. With two or more, it is measured across inspections. (This removes 1 home; the range rule already handles most of the uncertainty.) |
| **Never below 1 star; never raise a rating** | 1–5 is CMS's scale. Not seeing a spike isn't evidence of good care (most "High" homes simply have too little data), so the absence of a pattern can't earn a star. |
| No score, no CMS rating | No score or fewer than 2 inspections → CMS rating unchanged, with the reason. No CMS rating → no adjusted rating. |

Result on current data (356 homes): 30 homes meet the rule; 22 go down one star (8 from 2★, 6 from 3★, 4 from 4★,
4 from 5★); 8 are already at 1★. Every home gets a plain-language `adjust_reason`.
