# CONTRACTS.md: v1 (FROZEN)
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
 → [{ccn,name,city,lat,lon,overall_star,staffing_star,score_pct,ci_low,ci_high,label,trophy_flag}]
GET  /facility/{ccn}
 → {…facility fields, score fields, curve:[{d,v}], state_curve:[{d,v}], explanation:string|null}
POST /explain {ccn} → {text}   (Grok; facts JSON in, 3 sentences out)
--- regulator (header X-Demo-Role: regulator) ---
POST /schedule {month:"YYYY-MM", capacity:int, seed?:int}
 → {month, capacity, selected:[{ccn,name,prob,forced:bool,off_hours:bool}], probs:[{ccn,prob,forced}]}
GET  /simulate?capacity=int
 → {months:36, status_quo:{undetected_shirk_resident_months}, popquiz:{undetected_shirk_resident_months}, reduction_pct}
GET  /predictability → [{ccn,name,p_next_60d}]   (regulator only)
GET  /trophy → [{ccn,name,overall_star,score_pct,ci_low}]
