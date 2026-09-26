"""Grok explanation. Grok only rephrases the facts it is given (AGENTS.md rule 7);
any reply with a number not in the facts, or the word "gaming", is replaced by a template."""
import json
import os
import re

import httpx

XAI_URL = "https://api.x.ai/v1/chat/completions"

FACT_FIELDS = ["name", "city", "n_surveys", "score_pct", "ci_low", "ci_high", "label",
               "overall_star", "staffing_star"]

SYSTEM_PROMPT = """You write for families choosing a nursing home. You are given a JSON of facts about one facility.
Write exactly 3 plain-language sentences.
Rules:
- Use only the numbers in the JSON. Never compute, round differently, estimate or add any other number.
- score_pct is how much higher nurse hours per resident were in the 2 weeks before past inspections than a month later, in percent. ci_low to ci_high is its uncertainty range; always state it. n_surveys is the number of inspections it is based on.
- Call the pattern "survey-responsive staffing". Never use the words "gaming", "cheating" or "fraud".
- Mention that staffing data is self-reported by the facility.
- Never say anything about when the next inspection might happen."""

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def facts_for(fac):
    """The facts Grok may restate. Floats are rounded to 1 decimal, as the web page shows them."""
    return {k: round(v, 1) if isinstance(v, float) else v
            for k, v in ((k, fac.get(k)) for k in FACT_FIELDS) if v is not None}


def template(f):
    n = f.get("n_surveys")
    based = f", based on {n} inspections" if n else ""
    score = f["score_pct"]
    direction = "higher" if score >= 0 else "lower"
    if f["ci_low"] > 0:
        verdict = "This pattern is called survey-responsive staffing."
    elif f["ci_high"] < 0:
        verdict = "Staffing was lower before inspections, the opposite of survey-responsive staffing."
    else:
        verdict = "The range includes zero, so there is no clear sign of survey-responsive staffing."
    return (f"At {f['name']}, nurse hours per resident in the 2 weeks before past inspections were "
            f"{abs(score):g}% {direction} than a month later (range {f['ci_low']}% to {f['ci_high']}%{based}). "
            f"{verdict} Staffing data is self-reported by the facility through PBJ.")


def _allowed_numbers(facts):
    allowed = {"2", "3"}  # "2 weeks", "3 sentences"-style phrasing from the prompt itself
    for v in facts.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            for x in (v, abs(v)):
                allowed.add(f"{x:g}")
                allowed.add(str(x))
    return allowed


def passes_guardrails(text, facts):
    if re.search(r"\bgam(e|ed|ing)\b", text, re.I):
        return False
    allowed = _allowed_numbers(facts)
    return all(m.lstrip("-") in allowed or m in allowed for m in _NUM.findall(text))


# Web gives up on the API after 4 s (API_TIMEOUT_MS), so Grok must answer well inside that.
GROK_TIMEOUT_S = float(os.environ.get("XAI_TIMEOUT_S", "3"))

# Grok replies that passed the guardrails, keyed by the exact facts sent. Timeouts and
# rejected replies aren't cached, so the next view tries Grok again.
_cache = {}


def _cache_key(facts):
    return json.dumps(facts, sort_keys=True)


def cached(fac):
    """The stored Grok explanation for this facility, or None."""
    return _cache.get(_cache_key(facts_for(fac)))


def _ask_grok(facts, key, client):
    try:
        client = client or httpx.Client(timeout=GROK_TIMEOUT_S)
        r = client.post(XAI_URL, headers={"Authorization": f"Bearer {key}"}, json={
            "model": os.environ.get("XAI_MODEL", "grok-4"),
            "temperature": 0.2,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": json.dumps(facts)}],
        })
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None
    return text if passes_guardrails(text, facts) else None


NO_SCORE = ("There are not enough inspections with staffing data to score this home yet. "
            "Staffing data is self-reported by the facility through PBJ.")


def explain(fac, client=None):
    facts = facts_for(fac)
    if any(facts.get(k) is None for k in ("score_pct", "ci_low", "ci_high")):
        return NO_SCORE
    k = _cache_key(facts)
    if k in _cache:
        return _cache[k]
    key = os.environ.get("XAI_API_KEY")
    text = _ask_grok(facts, key, client) if key else None
    if text is None:
        return template(facts)
    _cache[k] = text
    return text
