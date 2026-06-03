PYTHON ?= python3
BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/.venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
REPO_ROOT := $(abspath ..)
PROVIDER_MODE ?= mock
BACKEND_PORT ?= 8001
FRONTEND_PORT ?= 5173

.PHONY: backend-venv backend-run backend-test frontend-install frontend-run up down start stop restart status check codex-audit codex-task codex-next codex-resume test dev lint provider-smoke

backend-venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt

backend-run:
	cd $(BACKEND_DIR) && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port $(BACKEND_PORT)

backend-test:
	cd $(BACKEND_DIR) && PROVIDER_MODE=mock .venv/bin/pytest -q

frontend-install:
	cd $(FRONTEND_DIR) && npm install

frontend-run:
	cd $(FRONTEND_DIR) && npm run dev -- --host 127.0.0.1 --port $(FRONTEND_PORT)

up:
	docker compose up --build

down:
	docker compose down

start:
	$(REPO_ROOT)/runit start

stop:
	$(REPO_ROOT)/runit stop

restart:
	$(REPO_ROOT)/runit restart

status check:
	$(REPO_ROOT)/runit status

codex-audit codex-task codex-next codex-resume test dev lint:
	@echo "Error: Run this from $(REPO_ROOT), not $(CURDIR)." >&2
	@exit 2

.PHONY: backend-smoke smoke
backend-smoke:
	cd backend && PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_smoke_vm_lifecycle.py

smoke: backend-smoke

provider-smoke:
	cd backend && PROVIDER_MODE="$(PROVIDER_MODE)" PYTHONPATH=. $$(if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi) scripts/provider_smoke.py
