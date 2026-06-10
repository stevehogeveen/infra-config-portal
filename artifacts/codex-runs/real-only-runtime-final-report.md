# Real-Only Runtime Cleanup Final Report

- Completed at: `2026-06-09T16:04:30+00:00`
- Repository: `/home/administrator/infra-config-portal`
- Runtime mode: `local-lab-readwrite`
- Operator runtime: `real_lab`

## Scope

This cleanup separates operator runtime state from automated test fixtures:

- Running app surfaces now prefer live or fresh cached lab state.
- Mock/test fixture state remains available for automated tests only.
- Historical artifacts are evidence only and cannot create current blockers by themselves.
- Not-checked states are shown as not checked or run-live-check states, not as fake failures.

## Implemented Changes

- Added a shared source/freshness model with `source_type`, `checked_at`, `freshness`, TTL/stale fields, `is_current`, `is_operator_visible`, `recheck_command`, and `evidence_artifacts`.
- Added source metadata to provider status, Build Verification, firmware compliance, full rebuild reporting, NetApp live state, and the unified report center.
- Updated runtime provider status so `PROVIDER_MODE=mock` is treated as a test fixture mode and is hidden from real-lab operator surfaces.
- Added a dev/test banner path when the backend is serving operator UI while in mock mode.
- Updated Reports and Issues so red means current live blocker, yellow means stale/historical evidence or stage dependency, blue/gray means not checked/not configured, and green means current live pass.
- Updated Build Verification to write:
  - `artifacts/codex-runs/build-verification-current-state-report.md`
  - `artifacts/codex-runs/build-verification-evidence-report.md`
- Updated lab-profile runtime selection so stale saved `10.10.8.x` profiles do not appear as the current real-lab profile. The active operator profile is now the runtime `192.168.1.0/24` profile.
- Updated NetApp and Cisco wording away from preview/mock ambiguity and toward live readiness, apply-disabled, stale evidence, and run-live-check language.
- Removed the legacy mock-results payload flag from runtime summaries.
- Added Make targets:
  - `make provider-lab-live-status`
  - `make provider-lab-refresh-live-state`
  - `make provider-lab-build-verification-live`

## Current Live State

Backend health:

- `provider_mode`: `local-lab-readwrite`
- `operator_runtime_mode`: `real_lab`
- `expected_runtime_mode`: `local-lab-readwrite`
- `dev_test_banner`: none

Build Verification current-state report:

- Source: `live_probe`
- Freshness: `current`
- Current: `True`
- Status: `blocked`
- Recheck: `make provider-lab-build-verification-live`

Current live blockers:

- iLO Redfish port is not reachable.
- iLO XML fallback port is not reachable.
- Cisco SSH/SCP port is not reachable.
- ESXi API port is not reachable.
- ESXi SSH port is not reachable.
- NetApp REST/SSH remain blocked by current live/cached NetApp state.
- NetApp NFS/vCenter readiness is not checked yet and does not count as a live failure.

Current live/cached passes:

- NetApp console is detected from current live/cached evidence.
- NetApp console read-state is ready.
- ESXi ISO media inventory is ready.

Historical evidence:

- The old `10.10.8.x` report is grouped under stale evidence.
- Historical evidence does not create top-level current blockers.

## Validation

Commands run:

- `make lint` passed.
- `make test` passed: `309 passed`, plus frontend production build passed.
- `make provider-lab-build-verification-live` wrote live current/evidence reports and exited nonzero because current live blockers remain.
- `PROVIDER_LAB_LIVE_STAGE_TIMEOUT_SECONDS=20 make provider-lab-refresh-live-state` completed and wrote redacted live status artifacts with product status `blocked`.
- `make app-restart` restarted the app in `local-lab-readwrite` after the mock-only smoke check passed.

Final live artifacts:

- `artifacts/codex-runs/build-verification-current-state-report.md`
- `artifacts/codex-runs/build-verification-evidence-report.md`
- `artifacts/codex-runs/provider-lab-live-status-report.md`
- `artifacts/codex-runs/provider-lab-live-status-redacted.json`
- `artifacts/codex-runs/real-only-runtime-audit.md`

Screenshots captured:

- `artifacts/screenshots/real-only-dashboard.png`
- `artifacts/screenshots/real-only-reports-issues.png`
- `artifacts/screenshots/real-only-build-verification.png`
- `artifacts/screenshots/real-only-netapp-current.png`
- `artifacts/screenshots/real-only-firmware.png`

## Safety

- No destructive hardware workflows were run.
- No provider write/apply workflow was enabled.
- No secrets, raw console transcripts, tokens, or credential values are included in reports or screenshots.
- Mock fixtures remain available for tests, but mock mode is no longer presented as an operator runtime state in the real-lab app.

## Recommended Next Steps

- Restore or validate network reachability for iLO, Cisco management SSH/SCP, and ESXi API/SSH, then rerun `make provider-lab-build-verification-live`.
- Rerun `make provider-lab-refresh-live-state` without the short timeout once console readiness commands are expected to return promptly.
- Configure approved local NetApp API access only through the live validation path if REST/SSH certification is required.
