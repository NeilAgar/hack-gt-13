"""Data access for the API. Family endpoints serve fixtures/ until A's tables land in data/processed/.
Regulator endpoints call B's models/ live, falling back to fixtures/ if models can't load."""
import json
import logging
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

SOURCE = "fixtures"

log = logging.getLogger(__name__)


def _load(name):
    return json.loads((FIXTURES / name).read_text())


@lru_cache
def facilities():
    return _load("facilities.json")


@lru_cache
def _facility_sample():
    sample = _load("facility_sample.json")
    sample.pop("_note", None)
    return sample


def search_facilities(q, limit):
    q = (q or "").strip().lower()
    rows = [f for f in facilities() if not q or q in f["name"].lower() or q in f["city"].lower() or q == f["ccn"]]
    return rows[:limit]


def facility(ccn):
    """Full facility record, or None. Fixtures only have a curve for the sample facility (115999)."""
    sample = _facility_sample()
    if ccn == sample["ccn"]:
        return dict(sample)
    row = next((f for f in facilities() if f["ccn"] == ccn), None)
    if row is None:
        return None
    return {**row, "curve": [], "state_curve": sample["state_curve"], "explanation": None}


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
    return _load("trophy.json")
