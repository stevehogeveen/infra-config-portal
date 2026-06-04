.PHONY: check-repo-root codex-audit codex-task codex-next codex-resume test dev lint provider-smoke netapp-real-readiness app-start app-stop app-restart app-status app-check

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
TASK ?= .codex/tasks/001-backend-vm-request-lifecycle.md
CODEX_SANDBOX_MODE ?= workspace-write
CODEX_APPROVAL_POLICY ?= never
PROVIDER_MODE ?= mock

export CODEX_SANDBOX_MODE
export CODEX_APPROVAL_POLICY

check-repo-root:
	$(REPO_ROOT)/scripts/check-repo-root.sh

codex-audit: check-repo-root
	$(REPO_ROOT)/scripts/codex-audit.sh

codex-task: check-repo-root
	$(REPO_ROOT)/scripts/codex-task.sh "$(TASK)"

codex-next: check-repo-root
	$(REPO_ROOT)/scripts/codex-next.sh

codex-resume: check-repo-root
	$(REPO_ROOT)/scripts/codex-resume-last.sh

test: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app backend-test PROVIDER_MODE=mock
	cd $(REPO_ROOT)/app/frontend && PROVIDER_MODE=mock npm run build

dev: check-repo-root
	$(REPO_ROOT)/runit restart

app-start: check-repo-root
	$(REPO_ROOT)/runit start

app-stop: check-repo-root
	$(REPO_ROOT)/runit stop

app-restart: check-repo-root
	$(REPO_ROOT)/runit restart

app-status app-check: check-repo-root
	$(REPO_ROOT)/runit status

lint: check-repo-root
	PROVIDER_MODE=mock bash -n $(REPO_ROOT)/runit
	PROVIDER_MODE=mock bash -n $(REPO_ROOT)/scripts/*.sh
	PROVIDER_MODE=mock python3 -c "import pathlib, tomllib; tomllib.loads(pathlib.Path('$(REPO_ROOT)/.codex/config.toml').read_text())"
	@if [ -x $(REPO_ROOT)/app/backend/.venv/bin/ruff ]; then \
		PROVIDER_MODE=mock $(REPO_ROOT)/app/backend/.venv/bin/ruff check $(REPO_ROOT)/app/backend; \
	else \
		echo "Backend lint: ruff is configured but not installed in app/backend/.venv; skipping."; \
	fi
	cd $(REPO_ROOT)/app/frontend && PROVIDER_MODE=mock npm run build

.PHONY: backend-smoke smoke
backend-smoke:
	$(REPO_ROOT)/scripts/check-repo-root.sh
	$(MAKE) -C $(REPO_ROOT)/app backend-smoke PROVIDER_MODE=mock

smoke: backend-smoke

provider-smoke: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app provider-smoke PROVIDER_MODE="$(PROVIDER_MODE)"

netapp-real-readiness: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app netapp-real-readiness PROVIDER_MODE="$(PROVIDER_MODE)"
