# Codex Automation

This folder contains project-scoped automation for running future development
tasks with `codex exec`.

## Layout

- `config.toml`: project defaults for sandboxed, non-interactive Codex runs.
- `skills/`: project-specific Codex skills for Lab Builder runtime, UX,
  hardware-run, report-remediation, toolchain, skill stewardship, dual-app
  architecture, and product craft conventions.
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

## Project Skills

Project-specific skills live under `.codex/skills/`. Future Codex runs should
inspect this directory before starting a task, read the relevant `SKILL.md`
files, and apply the smallest matching set automatically.

Skill list:

- `lab-builder-real-runtime`: runtime status, source type, freshness,
  live-vs-mock boundaries, stale evidence, blocker classification, or
  `local-lab-readwrite` gates.
- `lab-builder-ux`: sidebar navigation, setup page layout, operator next
  actions, status color semantics, Reports, or evidence/raw JSON placement.
- `lab-builder-hardware-run`: discover-plan-apply-verify-report workflows,
  lab profile handling, console autodiscovery, NetApp/Cisco/iLO/ESXi run
  sequencing, or hardware artifacts.
- `lab-builder-report-remediation`: Report Center, issue cards, stale config
  warnings, blocker fields, evidence links, copyable fix commands, or recheck
  commands.
- `lab-builder-toolchain`: Toolchain Readiness, provider tool availability,
  Cisco serial/SSH tooling, iLO Redfish/iLOrest, ESXi install/vSphere tooling,
  NetApp ONTAP tooling, or firmware baseline workflows.
- `lab-builder-skill-steward`: automatic skill selection, skill inventory,
  skill creation criteria, and major-run skill improvement reviews.
- `lab-builder-dual-app-architecture`: architecture comparisons and migration
  planning between `infra-config-portal` and `lab-builder`.
- `lab-builder-product-craft`: product polish, visual coherence, page
  simplification, action-first controls, and mock-state clarity.

Automatic loading rules:

- Frontend/UX: use `lab-builder-ux` and `lab-builder-product-craft`.
- Real runtime/status/reporting: use `lab-builder-real-runtime`.
- Hardware workflows: use `lab-builder-hardware-run`.
- Blocker/report remediation: use `lab-builder-report-remediation`.
- External provider tools and firmware/toolchain checks: use
  `lab-builder-toolchain`.
- Cross-app synthesis: use `lab-builder-dual-app-architecture`.
- Skill upkeep: use `lab-builder-skill-steward`.

Mock/test state must never be treated as real lab state. Historical artifacts
are evidence, not current blockers unless a fresh check proves the blocker is
current.

## Asking Codex To Use Skills

Usually no explicit request is needed. Codex should choose skills automatically
from the task scope. You can still name a skill directly, for example:

```text
Use lab-builder-product-craft and lab-builder-ux for this UI pass.
```

For broad runs, ask for the applied skills to be listed in the generated run
report.

## Creating Or Updating Skills

Use `lab-builder-skill-steward` before creating or updating a skill. A new
skill should be proposed or created only when the workflow is reusable, applies
to multiple future tasks, reduces future prompt length or mistakes, captures a
recurring failure mode or product rule, and includes clear `when to use` and
`do not use` guidance.

When a pattern is promising but not yet proven, record it as a future skill
candidate in the run report instead of creating another skill.

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
