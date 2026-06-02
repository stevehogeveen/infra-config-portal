# Codex Automation

This folder contains project-scoped automation for running future development
tasks with `codex exec`.

## Layout

- `config.toml`: project defaults for sandboxed, non-interactive Codex runs.
- `tasks/`: small task prompts intended to be run one at a time.
- `prompts/`: reusable prompts for resume or future workflow helpers.
- `runs/`: generated final responses and JSONL logs from Codex runs.
- `task-queue.md`: recommended task order.

## Always Run From Repo Root

The `.codex/` directory is at `/home/administrator/infra-config-portal/.codex`.
Run root automation from the repository root:

```bash
cd /home/administrator/infra-config-portal
```

Do not run root `make` or `git add .codex/...` commands from
`/home/administrator/infra-config-portal/app`; that directory has its own
Makefile and no `.codex/` folder.

## Running A Task

From the repository root:

```bash
./scripts/codex-task.sh .codex/tasks/000-repo-audit.md
```

Or through `make`:

```bash
make codex-task TASK=.codex/tasks/001-backend-vm-request-lifecycle.md
```

Each run defaults to `CODEX_SANDBOX_MODE=workspace-write` and
`CODEX_APPROVAL_POLICY=never`, then writes output under `.codex/runs/`. The
wrappers pass approval policy with
`-c "approval_policy=\"${CODEX_APPROVAL_POLICY}\""`; this Codex CLI does not
use `--ask-for-approval`. The root `Makefile` exports these safe defaults for
`make codex-*` commands and still allows explicit per-command environment
overrides.

If local bwrap sandboxing fails before shell execution, the only approved
fallback is an explicitly acknowledged local run:

```bash
CODEX_SANDBOX_MODE=danger-full-access CODEX_DANGER_ACK=I_UNDERSTAND make codex-next
```

`danger-full-access` is never the default. It should only be used on an
isolated development machine with no real infrastructure credentials, no
secrets, no production SSH keys, and no access to real vSphere, ESXi, iLO,
NetApp, switches, DNS, IPAM, storage, or production networks. Do not export
`CODEX_SANDBOX_MODE=danger-full-access` globally; set it only on the single
fallback command that requires it.

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

- Do not use `--yolo` or sandbox bypass flags.
- Do not use `danger-full-access` by default; it requires
  `CODEX_SANDBOX_MODE=danger-full-access` and
  `CODEX_DANGER_ACK=I_UNDERSTAND`.
- Do not add real credentials, IPs, hostnames, tokens, or secrets.
- Keep `PROVIDER_MODE=mock` unless a human explicitly changes it outside an
  automated Codex task.
- Do not make real vSphere, ESXi, iLO, NetApp, switch, OVF, storage, AWX,
  Terraform, NetBox, Nautobot, or similar provider calls.
- Prefer mock providers, contract tests, dry-run plans, and documented adapter
  boundaries.
