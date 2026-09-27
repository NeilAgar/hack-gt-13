# CONTRACTS.md: v1.3 (FROZEN)
Change only through a PR labeled `contract` that all 4 owners approve. Bump the version when you change it.

## Keys and conventions
- `ccn`: 6-char string CMS Certification Number (keep leading zeros). The join key everywhere.
- Dates: ISO `YYYY-MM-DD`. Percentages are floats in percent units (11.2 means 11.2%).
- `rel_day`: days relative to the survey anchor date (see A's go/no-go note on start vs. exit date).

## Parquet tables in data/processed/ (A writes, unless noted)
### facilities
ccn, name, city, county, lat, lon, certified_beds:int, avg_residents:float, ownership, overall_star:int,
staffing_star:int, health_star:int, harm_citations_3y:int, ij_citations_3y:int, rbs_proxy_eligible:bool

### daily_staffing
ccn, date, census:int, hrs_rn, hrs_lpn, hrs_cna, hrs_contract, hprd, hprd_resid
(hprd = (rn+lpn+cna)/census; hprd_resid = hprd minus facility day-of-week mean and 90-day rolling trend)

### surveys
ccn, survey_date, survey_type ('health_standard' only), source ('current'|'archive')

### scores
ccn, n_surveys:int, raw_pct, score_pct (shrunk), ci_low, ci_high, surge_pct, weekend_dip_pct,
label ('High'|'Watch'|'Low' consistency; cutoffs set by A in docs/DECISIONS.md), trophy_flag:bool (= rbs_proxy_eligible AND ci_low > 0)

### curves
ccn (or 'GA' for the state average), rel_day:int (-42..56), hprd_resid_mean, n_obs:int

### hazard (B writes, INTERNAL)
ccn, weeks_since_last:int, p_survey_week, p_next_60d

## API (C serves, D consumes). Base /api
GET  /facilities?q=&limit=50
 → [{ccn,name,city,lat,lon,overall_star,adjusted_star,staffing_star,score_pct,ci_low,ci_high,label,trophy_flag}]
GET  /facility/{ccn}
 → {…facility fields, score fields, adjusted_star:int|null, adjust_reason:string|null,
    normal_p95:float|null, normal_days:int|null,
    curve:[{d,v}], state_curve:[{d,v}], explanation:string|null}
 (v1.1) adjusted_star = CMS overall_star, minus one star for clear, repeated survey-responsive staffing;
 never higher than overall_star, never below 1, null when CMS has no overall rating. adjust_reason always
 explains the result in plain language (null only in fixture mode). Rules: docs/DECISIONS.md "Adjusted star rating".
 (v1.2) normal_p95 = this home's "normal day" line for the curve chart, same units as curve.v: the 95th
 percentile of its staffing on ordinary days (>60 days from any inspection), averaged over as many days as
 inspections in its curve. normal_days = ordinary days it is based on. null when there is no curve or <60 days.
 Rules: docs/DECISIONS.md "Normal-day line".
POST /explain {ccn} → {text}   (Grok; facts JSON in, 3 sentences out)
--- regulator (header X-Demo-Role: regulator) ---
POST /schedule {month:"YYYY-MM", capacity:int, seed?:int}
 → {month, capacity, selected:[{ccn,name,prob,forced:bool,off_hours:bool}], probs:[{ccn,prob,forced}]}
GET  /simulate?capacity=int
 → {months:36, status_quo:{undetected_shirk_resident_months}, popquiz:{undetected_shirk_resident_months}, reduction_pct}
GET  /predictability → [{ccn,name,p_next_60d}]   (regulator only)
GET  /trophy → [{ccn,name,overall_star,score_pct,ci_low}]
GET  /backlog → {as_of:"YYYY-MM-DD", forced_weeks:float, homes:[{ccn,weeks_since_last:int,forced:bool}]}
 (v1.3, regulator only) weeks since each home's last standard inspection, as of the scheduler's as-of date.
 forced = weeks_since_last >= forced_weeks (15.9 months), the same test /schedule uses. Past dates only; no prediction.
