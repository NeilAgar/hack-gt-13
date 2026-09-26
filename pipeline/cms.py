"""CMS download + column maps. Names come from the live files / PUF spec, not invented."""

from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

UA = {"User-Agent": "PopQuiz-HackGT13/1.0 (academic research; CMS public data)"}

# Latest PBJ quarter first. IDs from https://data.cms.gov/data.json (Daily Nurse Staffing).
PBJ_GA_QUARTERS: list[tuple[str, str]] = [
    ("2026Q1", "7e0d53ba-8f02-4c66-98a5-14a1c997c50d"),
    ("2025Q4", "bde06106-736e-4ac3-9406-c153fd4bc414"),
    ("2025Q3", "2a3e7c33-817d-49cb-8b24-2c26ba5fd520"),
    ("2025Q2", "a4227149-1ed3-41a5-adca-eaa98ea694e5"),
    ("2025Q1", "68c1e519-20b6-46f0-91af-407e35a4cf9d"),
    ("2024Q4", "732744a3-12fb-4cf0-a91d-2acfc3591a3d"),
    ("2024Q3", "989fbc78-1655-487d-9f24-d68e9a0ab3af"),
    ("2024Q2", "dcc467d8-5792-4e5d-95be-04bf9fc930a1"),
    ("2024Q1", "5b84bdf2-b246-4b3c-be1b-cf7c2bcb3391"),
]

SURVEY_DATES_URL = (
    "https://data.cms.gov/provider-data/sites/default/files/resources/"
    "c695a10fcf74e3a839879a307008563e_1786724153/NH_SurveyDates_Aug2026.csv"
)
PROVIDER_INFO_URL = (
    "https://data.cms.gov/provider-data/sites/default/files/resources/"
    "328596835e6db31b2564cd733c3795f4_1786724150/NH_ProviderInfo_Aug2026.csv"
)
HEALTH_CITATIONS_URL = (
    "https://data.cms.gov/provider-data/sites/default/files/resources/"
    "600f5d1861dd2e0280b2e961e8396245_1786724148/NH_HealthCitations_Aug2026.csv"
)

# Real PBJ headers printed from the 2026Q1 GA extract (and the PBJ PUF spec).
PBJ_HEADERS = [
    "PROVNUM",
    "PROVNAME",
    "CITY",
    "STATE",
    "COUNTY_NAME",
    "COUNTY_FIPS",
    "CY_Qtr",
    "WorkDate",
    "MDScensus",
    "Hrs_RNDON",
    "Hrs_RNDON_emp",
    "Hrs_RNDON_ctr",
    "Hrs_RNadmin",
    "Hrs_RNadmin_emp",
    "Hrs_RNadmin_ctr",
    "Hrs_RN",
    "Hrs_RN_emp",
    "Hrs_RN_ctr",
    "Hrs_LPNadmin",
    "Hrs_LPNadmin_emp",
    "Hrs_LPNadmin_ctr",
    "Hrs_LPN",
    "Hrs_LPN_emp",
    "Hrs_LPN_ctr",
    "Hrs_CNA",
    "Hrs_CNA_emp",
    "Hrs_CNA_ctr",
    "Hrs_NAtrn",
    "Hrs_NAtrn_emp",
    "Hrs_NAtrn_ctr",
    "Hrs_MedAide",
    "Hrs_MedAide_emp",
    "Hrs_MedAide_ctr",
]

# CMS total-nurse-staffing job categories in the PBJ nursing PUF (July 2023 spec).
HRS_RN = ["Hrs_RNDON", "Hrs_RNadmin", "Hrs_RN"]
HRS_LPN = ["Hrs_LPNadmin", "Hrs_LPN"]
HRS_CNA = ["Hrs_CNA", "Hrs_NAtrn", "Hrs_MedAide"]
HRS_CONTRACT = [
    "Hrs_RNDON_ctr",
    "Hrs_RNadmin_ctr",
    "Hrs_RN_ctr",
    "Hrs_LPNadmin_ctr",
    "Hrs_LPN_ctr",
    "Hrs_CNA_ctr",
    "Hrs_NAtrn_ctr",
    "Hrs_MedAide_ctr",
]

# Real Inspection Dates headers from NH_SurveyDates_Aug2026.csv
SURVEY_CCN = "CMS Certification Number (CCN)"
SURVEY_DATE = "Survey Date"
SURVEY_TYPE = "Type of Survey"
# Live file value is "Health Standard" (dictionary text says "Health Inspection Standard").
SURVEY_TYPE_HEALTH_STANDARD = "Health Standard"

# Real Provider Info headers from NH_ProviderInfo_Aug2026.csv
PI_CCN = "CMS Certification Number (CCN)"
PI_NAME = "Provider Name"
PI_CITY = "City/Town"
PI_STATE = "State"
PI_COUNTY = "County/Parish"
PI_LAT = "Latitude"
PI_LON = "Longitude"
PI_BEDS = "Number of Certified Beds"
PI_AVG_RES = "Average Number of Residents per Day"
PI_OWNERSHIP = "Ownership Type"
PI_OVERALL = "Overall Rating"
PI_STAFFING = "Staffing Rating"
PI_HEALTH = "Health Inspection Rating"

# Real Health Deficiencies headers from NH_HealthCitations_Aug2026.csv
HD_CCN = "CMS Certification Number (CCN)"
HD_STATE = "State"
HD_SCOPE = "Scope Severity Code"
HARM_CODES = {"G", "H", "I"}
IJ_CODES = {"J", "K", "L"}

FACILITIES_COLS = [
    "ccn",
    "name",
    "city",
    "county",
    "lat",
    "lon",
    "certified_beds",
    "avg_residents",
    "ownership",
    "overall_star",
    "staffing_star",
    "health_star",
    "harm_citations_3y",
    "ij_citations_3y",
    "rbs_proxy_eligible",
]
DAILY_STAFFING_COLS = [
    "ccn",
    "date",
    "census",
    "hrs_rn",
    "hrs_lpn",
    "hrs_cna",
    "hrs_contract",
    "hprd",
    "hprd_resid",
]
SURVEYS_COLS = ["ccn", "survey_date", "survey_type", "source"]
SCORES_COLS = [
    "ccn",
    "n_surveys",
    "raw_pct",
    "score_pct",
    "ci_low",
    "ci_high",
    "surge_pct",
    "weekend_dip_pct",
    "label",
    "trophy_flag",
]
CURVES_COLS = ["ccn", "rel_day", "hprd_resid_mean", "n_obs"]

# Chen & Dillender (NBER w34037): day 0 is inspection END. Do not shift to start.
# CONTRACTS windows, applied on that exit-day calendar.
PRE_RAMP = (-14, -1)
SURGE = (0, 3)
BASELINE = (28, 56)
CURVE_WINDOW = (-42, 56)
OVERLAP_DAYS = 150
# Staffing Consistency (public label). Low = significant survey-responsive staffing.
LABELS = ("High", "Watch", "Low")
WATCH_CI_HIGH_MIN = 5.0  # if CI includes 0 but upper bound > 5 → Watch
BOOTSTRAP_REPS = 500
BOOTSTRAP_SEED = 34037
# Days −14..−1 on the exit calendar include the inspection; do not say "before".
HEADLINE_TEMPLATE = (
    "In the 14 days through the last day of past inspections, nurse hours per "
    "resident were {abs_pct:.1f}% {direction} than a month later "
    "(range {ci_low:.1f} to {ci_high:.1f}%, based on {n} inspections)."
)


def pad_ccn(value: object) -> str:
    return str(value).strip().zfill(6)


def http_get(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def print_csv_headers(path: Path, label: str) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        headers = next(csv.reader(f))
    print(f"===== {label} headers ({path.name}) =====")
    print(headers)
    return headers


def download_pbj_ga(dataset_id: str, quarter: str, dest: Path, page_size: int = 5000) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"skip existing {dest.name}")
        return dest
    rows: list[dict] = []
    offset = 0
    while True:
        url = (
            f"https://data.cms.gov/data-api/v1/dataset/{dataset_id}/data"
            f"?filter[STATE]=GA&size={page_size}&offset={offset}"
        )
        print(f"PBJ {quarter} offset={offset}")
        chunk = json.loads(http_get(url).decode("utf-8"))
        if not isinstance(chunk, list):
            raise RuntimeError(f"Unexpected PBJ payload for {quarter}: {chunk!r}"[:400])
        print(f"  got {len(chunk)}")
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size
    if not rows:
        raise RuntimeError(f"No GA PBJ rows for {quarter}")
    fields = list(rows[0].keys())
    with dest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"saved {dest} rows={len(rows)}")
    return dest


def download_url(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"skip existing {dest.name}")
        return dest
    print(f"download {url}")
    dest.write_bytes(http_get(url, timeout=300))
    print(f"saved {dest} bytes={dest.stat().st_size}")
    return dest


def ensure_raw(latest_quarter_only: bool = False) -> dict[str, Path]:
    RAW.mkdir(parents=True, exist_ok=True)
    quarters = PBJ_GA_QUARTERS[:1] if latest_quarter_only else PBJ_GA_QUARTERS
    pbj_paths = []
    for quarter, dataset_id in quarters:
        path = RAW / f"PBJ_dailynursestaffing_CY{quarter}_GA.csv"
        download_pbj_ga(dataset_id, quarter, path)
        pbj_paths.append(path)
    surveys = download_url(SURVEY_DATES_URL, RAW / "NH_SurveyDates_Aug2026.csv")
    providers = download_url(PROVIDER_INFO_URL, RAW / "NH_ProviderInfo_Aug2026.csv")
    citations = download_url(HEALTH_CITATIONS_URL, RAW / "NH_HealthCitations_Aug2026.csv")
    print_csv_headers(pbj_paths[0], "PBJ Daily Nurse Staffing")
    print_csv_headers(surveys, "Inspection Dates")
    print_csv_headers(providers, "Provider Info")
    print_csv_headers(citations, "Health Deficiencies")
    return {
        "pbj": pbj_paths,
        "surveys": surveys,
        "providers": providers,
        "citations": citations,
    }
