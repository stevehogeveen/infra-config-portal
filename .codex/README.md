# Codex Automation

This folder contains project-scoped automation for running future development
tasks with `codex exec`.

## Layout

- `config.toml`: project defaults for sandboxed, non-interactive Codex runs.
- `tasks/`: small task prompts intended to be run one at a time.
- `prompts/`: reusable prompts for resume or future workflow helpers.
- `runs/`: generated final responses and JSONL logs from Codex runs.
- `task-queue.md`: recommended task order.

## Running A Task

From the repository root:

```bash
./scripts/codex-task.sh .codex/tasks/000-repo-audit.md
```

Or through `make`:

```bash
make codex-task TASK=.codex/tasks/001-backend-vm-request-lifecycle.md
```

Each run uses `codex exec --sandbox workspace-write` and writes output under
`.codex/runs/`. When the installed CLI supports `--json`, the wrapper also
saves a JSONL event log.

## Resume

Resume the most recent `codex exec` session:

```bash
./scripts/codex-resume-last.sh
```

Resume with a specific prompt file:

```bash
./scripts/codex-resume-last.sh .codex/tasks/004-tests-and-quality-gates.md
```

## Safety Rules

- Do not use `--yolo` or `danger-full-access`.
- Do not add real credentials, IPs, hostnames, tokens, or secrets.
- Keep `PROVIDER_MODE=mock` unless a human explicitly changes it outside an
  automated Codex task.
- Do not make real vSphere, ESXi, iLO, NetApp, switch, OVF, storage, AWX,
  Terraform, NetBox, Nautobot, or similar provider calls.
- Prefer mock providers, contract tests, dry-run plans, and documented adapter
  boundaries.
