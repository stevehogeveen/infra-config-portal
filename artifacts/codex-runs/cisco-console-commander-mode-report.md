# Cisco Console Commander Mode Report

## Summary

- Checked at: `2026-06-06`
- Scope: Cisco real-lab console workflow only.
- Apply gate: `--apply` only.
- Reclaim gate: `PROVIDER_MODE=local-lab-readwrite` plus `CISCO_CONSOLE_RECLAIM=true`.
- Real lab serial access: not run during this implementation pass.

## Implementation

- Added a Cisco console preflight claim stage before serial open.
- Detects process ownership for the selected `/dev/serial/by-id/...` path and its resolved `/dev/ttyUSB*` path.
- Uses `fuser` for PID detection and `ps` for command/argument reporting.
- Reclaims only allowed stale console holders: `screen`, `picocom`, `minicom`, and `python*`.
- Clears stale `LCK..tty*` lock files for the selected tty under `/var/lock` and `/run/lock`.
- Re-runs Cisco console discovery and ownership checks after reclaim before continuing login/bootstrap.
- Reports terminated processes, skipped processes, removed lock files, post-claim ownership, and blockers.
- Keeps configuration apply disabled unless `--apply` is explicitly passed.

## Verification

- `app/backend/.venv/bin/pytest app/backend/tests/test_cisco_real_lab_workflow.py`
  - Result: passed, `4 passed`.
- `python3 -m py_compile app/backend/scripts/cisco_real_lab_workflow.py app/backend/tests/test_cisco_real_lab_workflow.py`
  - Result: passed.
- `app/backend/.venv/bin/pytest app/backend/tests/test_cisco_real_lab_workflow.py app/backend/tests/test_provider_status_adapters.py`
  - Result: failed outside this change path.
  - Failure: `test_new_provider_probe_endpoints_are_explicit_and_blocked_in_mock_mode` expected `blocked`, observed `skipped` for a mock-mode provider probe.

## Safety

- No credentials, raw console logs, or raw running-config were saved.
- No real serial port was opened by the tests.
- No real infrastructure calls were made.
- Reclaim remains opt-in and limited to the explicit readwrite real-lab lane.
