# Stubs: each target runs its module once the owner creates it, and is a no-op until then,
# so `make demo` always works on main.
PYTHON ?= python3

.PHONY: data models api web demo test test-pipeline test-models test-api test-web

data:  ## A: pipeline/ -> data/processed/*.parquet
	@if [ -d pipeline ]; then $(PYTHON) -m pipeline; else echo "data: pipeline/ not built yet (stub)"; fi

models:  ## B: models/ -> data/processed/hazard.parquet, schedule + sim outputs
	@if [ -d models ]; then $(PYTHON) -m models; else echo "models: models/ not built yet (stub)"; fi

api:  ## C: FastAPI on :8000
	@if [ -f api/main.py ]; then $(PYTHON) -m uvicorn api.main:app --reload --port 8000; else echo "api: api/main.py not built yet (stub)"; fi

web:  ## D: Next.js on :3000
	@if [ -f web/package.json ]; then cd web && npm run dev; else echo "web: web/ not built yet (stub)"; fi

demo:  ## Everything; the API serves real data from data/processed/ if present, otherwise fixtures/
	@$(MAKE) -j2 api web

test: test-pipeline test-models test-api test-web

test-pipeline test-models test-api:
	@if [ -d $(@:test-%=%) ]; then $(PYTHON) -m pytest $(@:test-%=%); else echo "$@: $(@:test-%=%)/ not built yet (stub)"; fi

test-web:
	@if [ -f web/package.json ]; then cd web && npm test; else echo "test-web: web/ not built yet (stub)"; fi
