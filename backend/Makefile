# Field Shift backend. Override PY to use a specific interpreter, e.g. `make test PY=~/.venvs/x/bin/python`.
PY ?= uv run python

.PHONY: test lint serve offline-demo

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

serve:
	$(PY) -m uvicorn fieldshift.api.app:app --reload

# Reads only data/snapshots/ (Phase 1+). Network access is not needed.
offline-demo:
	FIELDSHIFT_OFFLINE=1 $(PY) -m uvicorn fieldshift.api.app:app
