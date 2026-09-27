# DECISIONS.md

One line per decision: what, who, when. The Devpost write-up draws on this.

| Decision | Owner | Status |
|---|---|---|
| Contract v1 frozen. `/simulate` `popquiz` has the same field as `status_quo`: `undetected_shirk_resident_months`. | all | decided |
| Hardware (Call Clock) cut from scope. | all | decided |
| Keep the MIT `LICENSE` in the repo. | all | decided |
| Staffing Consistency uses the same evidence test as the Pop Quiz star drop (`api/adjusted.py`), judged against the Georgia average (`state_avg` = mean of facility-level `raw_pct`, the value scores are shrunk toward): **Low** if `n_surveys >= 2` and `ci_low > state_avg` (strict); **Watch** if not Low and `ci_high > state_avg` (the range crosses the average, or is above it with only one inspection); **High** if `ci_high <= state_avg`. Low no longer uses `ci_low > 0`: every score is shrunk toward a positive average, so on random fake dates that rule labeled 0–100% of homes Low. A home with no CMS rating or already at 1★ can still be Low; those guards only stop the displayed star from changing. Trophy is unchanged: `rbs_proxy_eligible` AND `ci_low > 0`. | A | decided 2026-09-26 |
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

## Normal-day line on the staffing chart (contract v1.2, C)

`normal_p95` gives each facility chart a dotted line: the level this home's staffing stays below on 95% of its
ordinary days. A spike above it is unusual *for this home*. Code: `api/normal_band.py`.

| Choice | Why |
|---|---|
| **The home's own days**, not Georgia's | Homes differ in how much their staffing jumps around; each home is judged against its own normal. |
| **Ordinary = more than 60 days from any inspection** | The chart spans days −42 to +56, so no day that an inspection could affect counts as ordinary. |
| **Average of as many random ordinary days as the home has inspections in its curve** | Each point on the home's curve averages that day across its inspections, and an average of 2 days swings less than 1 day. Using single days would set the bar too high for homes with 2+ inspections. |
| **95th percentile** | Matches the 95% ranges used everywhere else. |
| **Fixed seed per home; null under 60 ordinary days** | The line never moves between runs, and isn't drawn from too little data. |

Calibration on real data: far from inspections (|day| ≥ 15), home curves sit above their own line 6.1% of the
time (a true 95th percentile gives 5%). On days −4 to −1, 199 of 350 homes go above their line at least once
(chance alone ≈ 19% over 4 days). Caveat for the UI: one day above the line is not proof on its own; about 1 day
in 20 crosses it by chance.

## Scheduler risk weights (B's scheduler, changed by C with the team's OK, 2026-09-27)

`risk = residents × (0.25 + S + C + 0.25 × W)` decides each home's chance of being picked. Code:
`risk_weights()` in `models/scheduler.py`; shown on the regulator demo from `web/lib/risk.ts`.

| Choice | Why |
|---|---|
| **S = rank (0–1) on our staffing score, weight 1** | Survey-responsive staffing is what a randomized schedule exists to counter. The old formula used `score ÷ 10`; with most scores at 1–2% it barely moved risk (Spearman correlation with the score: 0.00). |
| **C = min(1, 0.1 × harm + 0.2 × immediate jeopardy), weight 1** | Actual harm, confirmed by inspectors and not self-reported, so it counts as much as our score. Immediate jeopardy counts double, as before. The cap (reached by about 4% of homes) stops one extreme record from dominating. |
| **W = rank (0–1) on weekend dip, weight 0.25** | Almost every Georgia home staffs about 18% less on weekends. In the old formula (`dip ÷ 20`) this weak, indirect signal was about 55% of the multiplier. |
| **Ranks, not raw values** | They put every signal on the same 0–1 scale, so a weight says how much that signal counts, and outliers (scores up to 19%) can't take over. Missing score or weekend data → 0.5, the middle. |
| **Residents stays a plain multiplier** | The simulation counts harm in resident-months, so risk scales with the number of people. √residents would reduce the size effect, but that is a judgement call we can't back up. |
| **Base 0.25** | Every home keeps some chance of being picked. |
| **Agency share dropped** | Not in our data; it was 0 for every home. |

Effect on current data (Spearman correlation of risk with each input, old → new): home size 0.81 → 0.71, our
staffing score 0.00 → 0.41. Low-label homes in the top 50 by risk: 9 → 11 of 30. These weights are still
judgement calls, not fitted to inspection outcomes, and the UI labels them that way.
