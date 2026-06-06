# Lab Builder Hardening Report

- Checked at: `2026-06-06T14:13:21Z`
- Worktree: `/home/administrator/infra-config-portal`
- Provider mode: `local-lab-readwrite`
- Env source: `.env.local.real-lab`
- Mock results used as substitutes for real lab evidence: `false`

## Artifacts Written

- `artifacts/codex-runs/lab-builder-hardening-baseline.md`
- `artifacts/codex-runs/lab-ip-profile-hardening-report.md`
- `artifacts/codex-runs/build-verification-classification-report.md`
- `artifacts/codex-runs/failure-case-hardening-report.md`
- `artifacts/codex-runs/cisco-privilege-hardening-report.md` is now emitted by the Cisco real-lab workflow when that workflow runs.
- `artifacts/codex-runs/lab-builder-hardening-report.md`

## Implemented Hardening

- Build Verification now emits staged classifications: `passed`, `hard_fail`, `blocked_by_prior_stage`, `not_configured_yet`, `stale_config`, `operator_action_required`, and `warning`.
- Cisco SSH/SCP is `blocked_by_prior_stage` while `CISCO_MGMT_CONFIGURED=false` instead of a generic port failure.
- ESXi API/SSH are `blocked_by_prior_stage` while `ESXI_CONFIGURED=false` instead of generic port failures.
- NetApp REST/SSH are `not_configured_yet` while `NETAPP_CONFIGURED=false`.
- Active lab IP profile detection uses `192.168.1.0/24` with iLO `192.168.1.201`, embedded NIC `192.168.1.202`, ESXi `192.168.1.203`, Cisco `192.168.1.204`, and Ansible/control host `192.168.1.205`.
- Stale `10.10.8.x` inherited env values are overridden by non-stale `.env.local.real-lab` values during local real-lab loading, preventing old shell env from silently poisoning this run.
- Build Verification now reports credential compatibility by env/config field name while keeping values redacted.
- Build Verification now reports MTU classification and counts for invalid values/path mismatches.
- Product Certification UI now shows lab profile, stale IP detection, staged blocker categories, credential compatibility, MTU consistency, protocol readiness, next actions, and overall certification state.
- Cisco privilege reporting now includes prompt state, whether enable was sent, whether a password prompt was seen, enable rejection inference, password recovery/factory reset guidance, and exact operator next action.

## Current Certification Result

- `make provider-lab-build-verification` exited nonzero because certification is still blocked.
- Overall certification state: `blocked_by_prior_stage`.
- Lab IP profile: `passed`; no active Build Verification inputs contain `10.10.8.x`.
- Cisco console discovery/prompt detection: `passed`.
- iLO Redfish/XML readiness: `passed`.
- ESXi ISO media inventory: `passed`.
- Credential compatibility: `passed` for configured iLO, Cisco, Cisco enable, and ESXi fields.
- MTU consistency: `passed` for configured paths.
- NetApp REST/SSH: `not_configured_yet`.

## Remaining Blockers

- Cisco SSH/SCP: `blocked_by_prior_stage`; complete or confirm Cisco console bootstrap, then set `CISCO_MGMT_CONFIGURED=true` before treating SSH/SCP as a port failure.
- ESXi API: `blocked_by_prior_stage`; install/configure ESXi management at `192.168.1.203`, then set `ESXI_CONFIGURED=true` before API certification.
- ESXi SSH: `blocked_by_prior_stage`; install/configure ESXi management and enable/confirm SSH before ESXi SSH certification.

## Tests And Checks

- `cd app/backend && PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_build_verification.py`: passed, `10 passed`.
- `cd app/backend && PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_build_verification.py tests/test_provider_status_adapters.py`: passed, `87 passed`.
- `cd app/frontend && npm run build`: passed.
- `PROVIDER_MODE=local-lab-readwrite ENV_FILE=.env.local.real-lab make provider-lab-build-verification`: exited nonzero as expected with staged real certification blockers; reports were generated.

## UI Validation

- Frontend production build passed.
- Existing backend on `127.0.0.1:8001` returned the refreshed redacted Build Verification payload.
- Frontend dev server started on `127.0.0.1:5174`.
- Screenshot capture could not complete: Playwright was installed but its managed Firefox browser was missing, and launching system Firefox headless hung until stopped.
- Manual/API validation confirmed the Product Certification payload contains the new lab profile, certification state, staged failures, credential, MTU, and protocol fields consumed by the UI.

## Safety

- No secrets, passwords, tokens, or credential values were printed or written into hardening reports.
- No mock results were used as substitutes for real lab state.
- No new NetApp module work was started.
- Existing dirty worktree changes were preserved.
