.PHONY: check-repo-root codex-audit codex-task codex-next codex-resume test dev lint

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
TASK ?= .codex/tasks/001-backend-vm-request-lifecycle.md
CODEX_SANDBOX_MODE ?= workspace-write
CODEX_APPROVAL_POLICY ?= never

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
	$(MAKE) -C $(REPO_ROOT)/app backend-test
	cd $(REPO_ROOT)/app/frontend && npm run build

dev: check-repo-root
	$(MAKE) -C $(REPO_ROOT)/app up

lint: check-repo-root
	bash -n $(REPO_ROOT)/scripts/*.sh
	python3 -c "import pathlib, tomllib; tomllib.loads(pathlib.Path('$(REPO_ROOT)/.codex/config.toml').read_text())"
	@if [ -x $(REPO_ROOT)/app/backend/.venv/bin/ruff ]; then \
		$(REPO_ROOT)/app/backend/.venv/bin/ruff check $(REPO_ROOT)/app/backend; \
	else \
		echo "Backend lint: ruff is configured but not installed in app/backend/.venv; skipping."; \
	fi
	cd $(REPO_ROOT)/app/frontend && npm run build
