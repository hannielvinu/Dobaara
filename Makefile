# Reproduce every number in the README and on the dashboard.
PY ?= python

.PHONY: test eval eval-dev replies export web api

test:
	$(PY) -m pytest -q

eval-dev:
	$(PY) -m dobaara.replies.evaluate --parser baseline --split dev
	$(PY) -m dobaara.experiment --split dev

# Held-out runs. Documented in HELDOUT_LOG.md; run once per frozen policy.
eval:
	$(PY) -m dobaara.replies.evaluate --parser baseline --split heldout
	$(PY) -m dobaara.experiment --split test
	$(PY) -m dobaara.experiment --split shifted
	$(PY) -m dobaara.experiment --sensitivity --n 3000
	$(PY) -m dobaara.experiment --ablations --n 4000
	$(PY) -m dobaara.export

replies-llm:
	$(PY) -m dobaara.replies.evaluate --parser llm --split heldout

export:
	$(PY) -m dobaara.export

api:
	uvicorn dobaara.api:app --reload

web:
	cd web && npm ci && npm run dev
