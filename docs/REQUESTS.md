# Cross-directory requests

## D (web) + C (api): headline copy
Do **not** say staffing was higher "in the 2 weeks **before** inspections."

CMS `Survey Date` is the inspection **end**. The scored window is days −14..−1 on that calendar, which **includes the inspection**. Use:

> In the 14 days through the last day of past inspections, nurse hours per resident were {score_pct}% {higher\|lower} than a month later (range {ci_low} to {ci_high}%, based on {n_surveys} inspections).

Always show the range. Say "survey-responsive staffing," never "gaming," next to a named facility. Note that PBJ is self-reported.

`pipeline.scores.format_headline()` is the canonical string.
