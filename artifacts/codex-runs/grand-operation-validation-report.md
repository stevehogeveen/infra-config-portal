# Grand Operation Stage 11 - Full Validation Report

Generated: 2026-06-11T00:02:16Z

## Live Runs

- `make provider-lab-live-status`: completed, status `blocked`.
  - Current blockers: Cisco console login credentials missing for that specific probe; NetApp REST unreachable; NetApp API access values missing; NetApp NFS/vCenter blocked by prior NetApp setup state.
  - Artifact: `artifacts/codex-runs/provider-lab-live-status-report.md`
- `make provider-lab-build-verification-live`: completed with exit code 2, status `blocked`.
  - Current blockers are de-duplicated and focused on NetApp API/REST and NetApp NFS/vCenter prior-stage readiness.
  - Artifact: `artifacts/codex-runs/build-verification-report.md`
- `make provider-lab-validation`: completed, status `blocked`.
  - Top blocker: NetApp ONTAP cluster setup has not been applied or verified.
  - Artifact: `artifacts/codex-runs/lab-validation-handoff-report.md`
- `make provider-lab-full-rebuild-summary`: completed, report-only summary. No live device calls were attempted by that target.
- After the broad mock-mode `make test` run, live-lab artifacts were restored by rerunning:
  - `make provider-lab-live-status` at `2026-06-11T00:03:11Z`
  - `make provider-lab-build-verification-live` at `2026-06-11T00:04:34Z`
  - `make provider-lab-validation` at `2026-06-11T00:04:41Z`

## Fixes During Validation

- Report Center now downgrades older Cisco SSH/SCP failures when newer dedicated SSH and SCP validation reports are ready. Stale Cisco failures are evidence, not current critical blockers.
- Report Center now treats Cisco `captured` stage status as successful evidence, avoiding a low-value switch-identification warning.
- Firmware compliance now uses the redacted Cisco firmware inventory report as cached evidence when provider cache lacks IOS XE details and the latest console blocker is login-related rather than an invalid inventory result.
- Build Verification now de-duplicates public blocker text while preserving individual detailed protocol failures.
- Frontend `BlockerSummary` now uses stable keys for repeated blocker text; final browser screenshot pass had no React key warnings.

## Current Report Center State

- Critical: 2
- Current criticals:
  - NetApp REST is operator action required.
  - NetApp SSH is operator action required.
- Stale/historical Cisco SSH/SCP failures are warning/stale evidence only.
- Firmware IOS XE is no longer unknown; Cisco IOS XE is `17.15.05` from redacted firmware inventory evidence.

## Validation Commands

- `app/backend/.venv/bin/python -m pytest app/backend/tests/test_report_center.py`: 15 passed.
- `app/backend/.venv/bin/python -m pytest app/backend/tests/test_firmware_compliance.py`: 22 passed.
- `app/backend/.venv/bin/python -m pytest app/backend/tests/test_build_verification.py`: 19 passed.
- `app/backend/.venv/bin/python -m ruff check ...`: passed for touched backend files.
- `npm run build`: passed after frontend loader/key fixes.
- `make lint`: passed after final frontend key fix.
- `make test`: passed with 382 backend tests and frontend build. This mock-mode test run overwrote some report artifacts, so the live-lab status, Build Verification, and lab validation targets were rerun afterward.

## Remaining Blockers

- NetApp console login/API credentials are not configured for live login/API validation in this session. Values must remain local and redacted.
- NetApp cluster management REST is not reachable.
- NetApp setup intent is incomplete for guarded setup apply. Earlier apply validation exposed missing fields: cluster name, node names, SVM name, DNS servers, NTP servers, search domains, and admin access source.
- vCenter/NetApp datastore validation remains blocked until NetApp setup/API access and vCenter configuration are available.

## Next Action

Populate the missing NetApp setup intent and local redacted NetApp access values, then rerun:

`make provider-lab-netapp-setup-preview`

After preview is complete, use the explicit guarded setup apply command and then rerun:

`make provider-lab-refresh-live-state`
