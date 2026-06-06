# Firmware Gate Accuracy Report

Checked: 2026-06-06
Provider mode: `local-lab-readwrite`
Env file: `.env.local.real-lab` loaded without printing values.

## Changes

- Added Cisco firmware inventory through the serial console path for environments where Cisco SSH is not configured.
- Cisco inventory auto-discovers a usable console candidate, detects prompt state, runs only `show version` from exec/user-exec when available, parses IOS XE numerically, and writes `artifacts/codex-runs/cisco-firmware-inventory-report.md`.
- Firmware compliance now supports scopes: `hpe`, `cisco`, `netapp`, and `full`.
- NetApp `not_configured_yet` remains visible but does not block Cisco or HPE scope.
- Firmware compliance UI now shows gate scope and Cisco evidence source.
- Added root/app Make targets for Cisco inventory and scoped compliance runs.

## Real-Lab Run Results

- `make provider-lab-firmware-cisco-inventory`: blocked. The console port opened, but no prompt text was captured, so no fresh IOS XE version could be parsed in this run.
- `make provider-lab-firmware-compliance-scope-cisco`: blocked by Cisco IOS XE unknown. Next action is `Run Cisco firmware inventory from console.`
- `make provider-lab-firmware-compliance-scope-hpe`: warning-only. iLO firmware passed at `iLO 5 v3.19`; HPE BIOS and Smart Array firmware need manual baseline review. NetApp did not block HPE scope.
- `make provider-lab-firmware-compliance`: blocked for full certification. Cisco IOS XE is unknown, and NetApp remains `not_configured_yet` because `NETAPP_CONFIGURED=false`.

## Artifacts

- Cisco firmware inventory: `artifacts/codex-runs/cisco-firmware-inventory-report.md`
- Firmware inventory: `artifacts/codex-runs/firmware-inventory-report.md`
- Firmware compliance: `artifacts/codex-runs/firmware-compliance-report.md`
- Firmware summary: `artifacts/codex-runs/firmware-compliance-summary-redacted.json`

## Verification

- `cd app/backend && PROVIDER_MODE=mock PYTHONPATH=. .venv/bin/pytest -q tests/test_firmware_compliance.py tests/test_provider_status_adapters.py`: 98 passed.
- `cd app/frontend && npm run build`: passed.

## Safety

- No firmware update commands were run.
- No privileged exec requirement was added for Cisco `show version`.
- Raw console output was not saved.
- Secrets and env values were not printed.
