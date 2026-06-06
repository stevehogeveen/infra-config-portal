# Lab Builder Hardening Baseline

- Checked at: `2026-06-06T14:05:49Z`
- Worktree: `/home/administrator/infra-config-portal`
- Provider mode for this hardening run: `local-lab-readwrite`
- Env source: `.env.local.real-lab`
- Mock results used as substitutes for real lab evidence: `false`

## Git Baseline

- Worktree was already dirty before this hardening pass.
- Existing modified files include root docs/Makefiles, backend provider and workflow code, frontend provider UI, and multiple run reports.
- Existing untracked files include Build Verification, full rebuild, iLO, RAID, ESXi, Cisco workflow scripts/tests, and redacted run artifacts.
- This pass preserves existing changes and applies narrow hardening edits on top.

## Current Lab IP Profile

- Lab subnet: `192.168.1.0/24`
- iLO: `192.168.1.201`
- Server embedded NIC: `192.168.1.202`
- ESXi management: `192.168.1.203`
- Cisco management: `192.168.1.204`
- Ansible/control host: `192.168.1.205`
- `.env.local.real-lab` was inspected with credential values redacted; the active target fields match the current profile.

## Current Run Evidence

- `artifacts/codex-runs/overnight-lab-builder-final-report.md`
- `artifacts/codex-runs/full-device-rebuild-4h-report.md`
- `artifacts/codex-runs/cisco-4h-lab-run-report.md`
- `artifacts/codex-runs/cisco-privileged-exec-fix-report.md`
- `artifacts/codex-runs/hpe-raid-discovery-report.md`
- `artifacts/codex-runs/hpe-raid-plan-report.md`
- `artifacts/codex-runs/esxi-install-readiness-report.md`
- `artifacts/codex-runs/build-verification-report.md`
- `artifacts/codex-runs/build-verification-summary-redacted.json`
- `artifacts/codex-runs/lab-ip-profile-update-report.md`

## Baseline Findings

- iLO reachability/inventory, HPE RAID discovery/plan, and ESXi media/boot stages have completed in recent real-lab reports.
- Cisco console auto-discovery and prompt detection work at `9600`.
- Cisco privilege state needs careful reporting because overnight evidence showed user exec without confirmed privileged exec, while a later privilege report showed privileged exec.
- Existing Build Verification already checks lab IP profile, credential compatibility, MTU consistency, protocol readiness, and checklist state.
- Existing Build Verification output is too flat for staged certification; unresolved provider protocols are still presented as generic blockers instead of `blocked_by_prior_stage`, `not_configured_yet`, or `stale_config`.

## Safety Baseline

- No real secrets were printed or copied into this report.
- No mock results were used as substitutes for real lab state.
- No new NetApp module work was started.
