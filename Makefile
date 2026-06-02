.PHONY: codex-audit codex-task codex-next codex-resume test dev lint

TASK ?= .codex/tasks/001-backend-vm-request-lifecycle.md

codex-audit:
	./scripts/codex-audit.sh

codex-task:
	./scripts/codex-task.sh "$(TASK)"

codex-next:
	./scripts/codex-next.sh

codex-resume:
	./scripts/codex-resume-last.sh

test:
	$(MAKE) -C app backend-test
	cd app/frontend && npm run build

dev:
	$(MAKE) -C app up

lint:
	bash -n scripts/codex-task.sh scripts/codex-resume-last.sh scripts/codex-audit.sh scripts/codex-next.sh
	python3 -c "import pathlib, tomllib; tomllib.loads(pathlib.Path('.codex/config.toml').read_text())"
	@if [ -x app/backend/.venv/bin/ruff ]; then \
		app/backend/.venv/bin/ruff check app/backend; \
	else \
		echo "Backend lint: ruff is configured but not installed in app/backend/.venv; skipping."; \
	fi
	cd app/frontend && npm run build
