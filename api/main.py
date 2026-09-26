"""Pop Quiz API. Serves docs/CONTRACTS.md v1 under /api."""
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api import data
from api.explain import cached, explain

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@asynccontextmanager
async def lifespan(app):
    data.regulator_source()  # load models/ once at startup, not on the first click
    yield


app = FastAPI(title="Pop Quiz API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])


def source_header(response: Response):
    response.headers["X-Data-Source"] = data.SOURCE


def regulator_source_header(response: Response):
    response.headers["X-Data-Source"] = data.regulator_source()


def require_regulator(x_demo_role: str | None = Header(default=None)):
    if x_demo_role != "regulator":
        raise HTTPException(403, "Regulator mode only")


public = APIRouter(prefix="/api", dependencies=[Depends(source_header)])
regulator = APIRouter(prefix="/api", dependencies=[Depends(require_regulator)])
from_models = [Depends(regulator_source_header)]


def _get_facility(ccn):
    fac = data.facility(ccn)
    if fac is None:
        raise HTTPException(404, f"Unknown ccn {ccn}")
    return fac


@public.get("/facilities")
def facilities(q: str = "", limit: int = Query(50, ge=1, le=500)):
    return data.search_facilities(q, limit)


@public.get("/facility/{ccn}")
def facility(ccn: str):
    fac = _get_facility(ccn)
    return {**fac, "explanation": fac.get("explanation") or cached(fac)}


class ExplainRequest(BaseModel):
    ccn: str


@public.post("/explain")
def explain_endpoint(req: ExplainRequest):
    return {"text": explain(_get_facility(req.ccn))}


class ScheduleRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    capacity: int = Field(ge=1, le=1000)
    seed: int | None = Field(default=None, ge=0)


@regulator.post("/schedule", dependencies=from_models)
def schedule(req: ScheduleRequest):
    # No seed means a fresh draw on every Generate; pass one to reproduce a plan.
    seed = req.seed if req.seed is not None else secrets.randbelow(2**31)
    return data.schedule(req.month, req.capacity, seed)


@regulator.get("/simulate", dependencies=from_models)
def simulate(capacity: int = Query(..., ge=1, le=1000)):
    return data.simulate(capacity)


@regulator.get("/predictability", dependencies=from_models)
def predictability():
    return data.predictability()


@regulator.get("/trophy", dependencies=[Depends(source_header)])
def trophy():
    return data.trophy()


app.include_router(public)
app.include_router(regulator)

from api.routes.bedside import router as bedside_router  # noqa: E402  Call Clock (hardware/)
app.include_router(bedside_router)
