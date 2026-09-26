"""Grok Voice line. The browser talks to xAI's realtime API directly with a short-lived token that
this server mints, so the API key never leaves the server. Grok gets facts only through the
lookup_facility tool, which returns the same whitelisted facts as /explain (AGENTS.md rules 6-7)."""
import os
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from api import data
from api.explain import facts_for

CLIENT_SECRETS_URL = "https://api.x.ai/v1/realtime/client_secrets"
REALTIME_URL = "wss://api.x.ai/v1/realtime"
TOKEN_SECONDS = 300
SAMPLE_RATE = 24000
PAGE = Path(__file__).resolve().parent / "static" / "voice.html"

INSTRUCTIONS = """You are the Pop Quiz voice line. You help families understand how a Georgia nursing home staffs
around state inspections. Speak plainly and briefly: two or three sentences per answer.
Rules:
- Before answering about any home, call lookup_facility with the name or city the caller said. If it returns
  several matches, ask which one they mean. If it returns no matches, say you could not find that home; if it
  also returns did_you_mean names, offer those names but give no numbers until the caller picks one.
- Use only the numbers lookup_facility returns. Never compute, round differently, estimate or add any number.
- score_pct is how much higher nurse hours per resident were in the 2 weeks before past inspections than a month
  later, in percent. ci_low to ci_high is its uncertainty range; always say it. n_surveys is how many inspections
  it is based on. If there is no score_pct, say there are not enough inspections to score the home yet.
- Call the pattern "survey-responsive staffing". Never say "gaming", "cheating" or "fraud".
- Mention that staffing data is self-reported by the facility.
- Never say or guess when the next inspection might happen, even if asked. Say you can't share that.
- Suggest questions to ask on a tour: weekend staffing, agency staff, RN coverage at night."""

LOOKUP_TOOL = {
    "type": "function",
    "name": "lookup_facility",
    "description": "Look up a Georgia nursing home's staffing-consistency facts by name or city.",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Home name or city, as the caller said it"}},
        "required": ["query"],
    },
}


def session_config(voice=None):
    """The session.update payload the page sends once the socket opens."""
    return {
        "instructions": INSTRUCTIONS,
        "voice": voice or os.environ.get("XAI_VOICE", "eve"),
        "turn_detection": {"type": "server_vad"},
        "audio": {
            "input": {"format": {"type": "audio/pcm", "rate": SAMPLE_RATE}},
            "output": {"format": {"type": "audio/pcm", "rate": SAMPLE_RATE}},
        },
        "tools": [LOOKUP_TOOL],
    }


# Words that don't tell homes apart, so they don't count toward a match.
_FILLER = {"the", "in", "of", "at", "and", "a", "an", "home", "homes", "nursing", "center", "care", "health",
           "healthcare", "rehab", "rehabilitation", "llc", "inc", "georgia", "ga", "facility", "place"}


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _FILLER and len(w) > 1}


def lookup(query, limit=3):
    """Facts for homes whose name/city contains every distinctive word the caller said, so "Stevens Park in
    Augusta" matches but "Sunrise Manor" never returns some other Manor's numbers. Partial matches come back
    as names only (did_you_mean), with no facts. Only whitelisted fields, so no inspection timing can leak."""
    want = _words(query)
    full, partial = [], []
    for f in data.facilities():
        hits = len(want & _words(f"{f['name']} {f['city']}"))
        if want and hits == len(want):
            full.append(f["ccn"])
        elif hits:
            partial.append((hits, f["name"]))
    if full:
        return {"query": query, "matches": [facts_for(data.facility(c)) | {"ccn": c} for c in sorted(full)[:limit]]}
    partial.sort(key=lambda x: (-x[0], x[1]))
    return {"query": query, "matches": [], "did_you_mean": [n for _, n in partial[:limit]]}


def mint_token(client=None):
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise HTTPException(503, "Voice line needs XAI_API_KEY in .env")
    try:
        client = client or httpx.Client(timeout=10)
        r = client.post(CLIENT_SECRETS_URL, headers={"Authorization": f"Bearer {key}"},
                        json={"expires_after": {"seconds": TOKEN_SECONDS}})
        r.raise_for_status()
        body = r.json()
        return {"token": body["value"], "expires_at": body.get("expires_at")}
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise HTTPException(502, f"Could not start a voice session with xAI: {e}") from e


router = APIRouter()


@router.post("/api/voice/session")
def voice_session():
    return {**mint_token(), "url": REALTIME_URL, "session": session_config()}


@router.get("/api/voice/lookup")
def voice_lookup(q: str = Query(..., min_length=2, max_length=100)):
    return lookup(q)


@router.get("/voice", response_class=HTMLResponse)
def voice_page():
    return PAGE.read_text()
