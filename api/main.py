"""Pop Quiz API. Serves docs/CONTRACTS.md v1 under /api."""
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api import data
from api.explain import explain

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="Pop Quiz API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])


def source_header(response: Response):
    response.headers["X-Data-Source"] = data.SOURCE


def require_regulator(x_demo_role: str | None = Header(default=None)):
    if x_demo_role != "regulator":
        raise HTTPException(403, "Regulator mode only")


public = APIRouter(prefix="/api", dependencies=[Depends(source_header)])
regulator = APIRouter(prefix="/api", dependencies=[Depends(source_header), Depends(require_regulator)])


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
    return _get_facility(ccn)


class ExplainRequest(BaseModel):
    ccn: str


@public.post("/explain")
def explain_endpoint(req: ExplainRequest):
    return {"text": explain(_get_facility(req.ccn))}


class ScheduleRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    capacity: int = Field(ge=1)
    seed: int | None = None


@regulator.post("/schedule")
def schedule(req: ScheduleRequest):
    # Fixture mode returns the sample plan as is; B's scheduler replaces this.
    return data.schedule()


@regulator.get("/simulate")
def simulate(capacity: int = Query(..., ge=1)):
    return data.simulate()


@regulator.get("/predictability")
def predictability():
    return data.predictability()


@regulator.get("/trophy")
def trophy():
    return data.trophy()


app.include_router(public)
app.include_router(regulator)
