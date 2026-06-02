PYTHON ?= python3
BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/.venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

.PHONY: backend-venv backend-run backend-test frontend-install frontend-run up down

backend-venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt

backend-run:
	cd $(BACKEND_DIR) && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

backend-test:
	cd $(BACKEND_DIR) && .venv/bin/pytest -q

frontend-install:
	cd $(FRONTEND_DIR) && npm install

frontend-run:
	cd $(FRONTEND_DIR) && npm run dev -- --host 127.0.0.1

up:
	docker compose up --build

down:
	docker compose down
