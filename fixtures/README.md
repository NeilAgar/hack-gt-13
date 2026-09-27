# Fixtures

SYNTHETIC data for building against the API in README.md before real data lands. Not real CMS data:
every facility is named "Sample …". The API serves these until `data/processed/` exists.

| Endpoint | File |
|---|---|
| `GET /facilities` | `facilities.json` |
| `GET /facility/{ccn}` | `facility_sample.json` (ccn 115999) |
| `POST /explain` | `explain_sample.json` |
| `POST /schedule` (regulator) | `schedule_sample.json` |
| `GET /simulate` (regulator) | `simulate_sample.json` |
| `GET /predictability` (regulator only) | `predictability.json` |
| `GET /backlog` (regulator) | `backlog_sample.json` |

The six facilities are consistent across files. Their probabilities in `schedule_sample.json` sum to the capacity (3).
Change these only through a PR labeled `contract`, like the contract itself.
