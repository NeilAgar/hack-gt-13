"""Data access for the API. Family endpoints serve A's tables in data/processed/ once facilities and
scores exist there, otherwise fixtures/. Regulator endpoints call B's models/ live, falling back to
fixtures/ if models can't load."""
import json
import logging
import math
from functools import lru_cache
from pathlib import Path

from api import adjusted

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
PROCESSED = ROOT / "data" / "processed"

LIST_FIELDS = ["ccn", "name", "city", "lat", "lon", "overall_star", "adjusted_star", "staffing_star",
               "score_pct", "ci_low", "ci_high", "label", "trophy_flag"]
SCORE_FIELDS = ["n_surveys", "raw_pct", "score_pct", "ci_low", "ci_high", "surge_pct",
                "weekend_dip_pct", "label", "trophy_flag"]
LABELS = {"High", "Watch", "Low"}

log = logging.getLogger(__name__)


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def _clean(v):
    """NaN / pd.NA -> None, numpy scalars -> Python, so every value is JSON-safe."""
    if v is None:
        return None
    try:
        import pandas as pd
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        v = v.item()
    return None if isinstance(v, float) and math.isnan(v) else v


def _curve(df):
    return [{"d": int(r.rel_day), "v": _clean(r.hprd_resid_mean)} for r in df.sort_values("rel_day").itertuples()]


@lru_cache
def _processed():
    """A's facilities + scores (+ curves), joined once. None until both facilities and scores exist."""
    fac_path, sc_path, cur_path = (PROCESSED / f"{t}.parquet" for t in ("facilities", "scores", "curves"))
    if not (fac_path.exists() and sc_path.exists()):
        return None
    try:
        import pandas as pd
        fac = pd.read_parquet(fac_path)
        scores = pd.read_parquet(sc_path)
        curves = pd.read_parquet(cur_path) if cur_path.exists() else None
    except Exception:
        log.exception("data/processed unreadable; family endpoints serve fixtures")
        return None
    fac["ccn"] = fac["ccn"].astype(str).str.zfill(6)
    scores["ccn"] = scores["ccn"].astype(str).str.zfill(6)
    joined = fac.merge(scores[["ccn", *SCORE_FIELDS]], on="ccn", how="left")
    details = {}
    for rec in joined.to_dict("records"):
        row = {k: _clean(v) for k, v in rec.items()}
        # Labels outside the contract (e.g. A's PLACEHOLDER before cutoffs are set) are served as null.
        if row.get("label") not in LABELS:
            row["label"] = None
        row["trophy_flag"] = bool(row.get("trophy_flag"))
        if row.get("n_surveys") is not None:
            row["n_surveys"] = int(row["n_surveys"])
        details[row["ccn"]] = row
    state_avg = adjusted.state_average(d.get("raw_pct") for d in details.values())
    for row in details.values():
        row["adjusted_star"], row["adjust_reason"] = adjusted.adjust(row, state_avg)
    by_ccn, state_curve = {}, []
    if curves is not None:
        curves["ccn"] = curves["ccn"].astype(str)
        state_curve = _curve(curves[curves["ccn"] == "GA"])
        by_ccn = {c: _curve(g) for c, g in curves[curves["ccn"] != "GA"].groupby("ccn")}
    return {"details": details, "curves": by_ccn, "state_curve": state_curve}


def family_source():
    return "processed" if _processed() else "fixtures"


@lru_cache
def _fixture_facilities():
    return _load("facilities.json")


@lru_cache
def _facility_sample():
    sample = _load("facility_sample.json")
    sample.pop("_note", None)
    return sample


def _unadjusted(row):
    return {**row, "adjusted_star": row.get("overall_star"), "adjust_reason": None}


def facilities():
    p = _processed()
    if p is None:
        return [{k: _unadjusted(f).get(k) for k in LIST_FIELDS} for f in _fixture_facilities()]
    return [{k: d.get(k) for k in LIST_FIELDS} for d in p["details"].values()]


def search_facilities(q, limit):
    q = (q or "").strip().lower()
    rows = [f for f in facilities()
            if not q or q in (f["name"] or "").lower() or q in (f["city"] or "").lower() or q == f["ccn"]]
    return rows[:limit]


def facility(ccn):
    """Full facility record, or None. Homes without a score have null score fields and an empty curve."""
    p = _processed()
    if p is not None:
        row = p["details"].get(ccn)
        if row is None:
            return None
        return {**row, "curve": p["curves"].get(ccn, []), "state_curve": p["state_curve"], "explanation": None}
    sample = _facility_sample()
    if ccn == sample["ccn"]:
        return _unadjusted(sample)
    row = next((f for f in _fixture_facilities() if f["ccn"] == ccn), None)
    if row is None:
        return None
    return {**_unadjusted(row), "curve": [], "state_curve": sample["state_curve"], "explanation": None}


@lru_cache
def _models():
    """B's inputs and hazard fit, loaded once. None if models/ can't run here."""
    try:
        from models.config import DEFAULT_MONTH, PROCESSED_DIR
        from models.hazard import hazard_table
        from models.load import load_inputs
        from models.scheduler import build_schedule
        from models.simulate import simulate as run_simulation

        d = load_inputs(PROCESSED_DIR)
        table, h, lags = hazard_table(d["surveys"], d["facilities"])
    except Exception:
        log.exception("models/ unavailable; regulator endpoints serve fixtures")
        return None
    return {**d, "hazard": table, "h": h, "lags": lags, "month": DEFAULT_MONTH,
            "build_schedule": build_schedule, "simulate": run_simulation}


def regulator_source():
    m = _models()
    return f"models:{m.get('source', 'unknown')}" if m else "fixtures"


def schedule(month, capacity, seed):
    m = _models()
    if m is None:
        return _load("schedule_sample.json")
    plan = m["build_schedule"](m["facilities"], m["scores"], m["lags"], month=month, capacity=capacity, seed=seed)
    # Banned homes can't be picked, so a capacity above the eligible pool yields fewer picks.
    capacity = min(plan["capacity"], len(plan["selected"]))
    return {"month": plan["month"], "capacity": capacity, "selected": plan["selected"], "probs": plan["probs"]}


@lru_cache(maxsize=64)
def simulate(capacity):
    m = _models()
    if m is None:
        return _load("simulate_sample.json")
    sim = m["simulate"](m["facilities"], m["scores"], m["surveys"], m["h"], month=m["month"], capacity=capacity)
    return {k: sim[k] for k in ("months", "status_quo", "popquiz", "reduction_pct")}


def predictability():
    """Current-state p_next_60d per home, from the same model state as /schedule (as models/__main__.py does)."""
    m = _models()
    if m is None:
        return _load("predictability.json")
    names = dict(zip(m["facilities"]["ccn"].astype(str).str.zfill(6), m["facilities"]["name"]))
    cur = m["hazard"].merge(m["lags"][["ccn", "weeks_since_last"]], on=["ccn", "weeks_since_last"])
    rows = [{"ccn": r.ccn, "name": names.get(r.ccn, r.ccn), "p_next_60d": round(float(r.p_next_60d), 6)}
            for r in cur.itertuples(index=False)]
    return sorted(rows, key=lambda r: (-r["p_next_60d"], r["ccn"]))


def trophy():
    p = _processed()
    if p is None:
        return _load("trophy.json")
    rows = [{k: d[k] for k in ("ccn", "name", "overall_star", "score_pct", "ci_low")}
            for d in p["details"].values() if d["trophy_flag"]]
    return sorted(rows, key=lambda r: -(r["score_pct"] or 0))
