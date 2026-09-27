"""Adjusted star rating: CMS's published overall star rating plus one more adjustment step for
survey-responsive staffing. Every rule below is taken from CMS's own method or from our data; see
README.md ("Labels and the star drop") for the reasoning.

CMS builds the overall rating in steps: start from the health inspection rating, then add or subtract
exactly one star for staffing and one star for quality measures, and keep the result within 1-5 stars
(Five-Star Technical Users' Guide). The health inspection rating those steps start from is observed
during inspections, which is when our data shows staffing is highest. So we apply one more step of the
same kind.
"""

# CMS moves the overall rating one star per domain; we use the same step size.
STEP = 1
# CMS's scale. A home already at 1 star can't go lower, as in CMS's own steps.
MIN_STAR = 1
# The per-inspection range is only measured across inspections when a home has at least two. With one,
# the range comes from days inside that single inspection and can't show whether the pattern repeats.
MIN_INSPECTIONS = 2


def state_average(raw_pcts):
    """Georgia's average raw score: the value A's pipeline shrinks every home toward."""
    vals = [v for v in raw_pcts if v is not None]
    return sum(vals) / len(vals) if vals else None


def adjust(fac, state_avg):
    """(adjusted_star, reason) for one home. Never raises the rating; never invents a rating."""
    star = fac.get("overall_star")
    if star is None:
        return None, "CMS has not published an overall rating for this home."
    same = f"Same as the CMS overall rating ({star}★)"
    score, lo, hi, n = (fac.get(k) for k in ("score_pct", "ci_low", "ci_high", "n_surveys"))
    if score is None or lo is None or n is None:
        return star, f"{same}: not enough inspections with staffing data to adjust."
    if n < MIN_INSPECTIONS:
        return star, f"{same}: only {n} inspection with staffing data, not enough to show a repeated pattern."
    # Compare with the Georgia average, not with zero: CMS stars rank homes against each other, and the
    # typical Georgia home already staffs up a little around inspections.
    if state_avg is None or lo <= state_avg:
        return star, (f"{same}: staffing around past inspections is not clearly above the Georgia "
                      f"average of {state_avg:.1f}%.")
    evidence = (f"survey-responsive staffing of {score:.1f}% (range {lo:.1f}% to {hi:.1f}%, based on {n} "
                f"inspections) is clearly above the Georgia average of {state_avg:.1f}%")
    if star <= MIN_STAR:
        return star, f"Same as the CMS overall rating ({star}★), already the lowest: {evidence}."
    new = max(MIN_STAR, star - STEP)
    return new, f"CMS overall rating {star}★, adjusted to {new}★: {evidence}."
