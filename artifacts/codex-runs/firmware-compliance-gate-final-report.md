# Firmware Compliance Gate Final Report

Checked: 2026-06-06T17:14:03Z
Provider mode: local-lab-readwrite
Environment file: .env.local.real-lab

## Outcome

Implemented the firmware compliance gate for the real-lab Lab Builder flow.
The gate performs inventory/compliance/reporting only. No firmware update,
upload, flash, or firmware reboot action was added or run.

Current real-lab gate status: blocked.

Primary blocker:

- Cisco IOS XE version is unknown. Required minimum is 17.9. Next action: run
  Cisco read-only show version collection before bootstrap/apply.

Current classified signals:

- iLO firmware: passed, current iLO 5 v3.19, approved 3.19.
- HPE BIOS: warning, current U32 v3.30 (07/31/2024), baseline requires manual
  approval.
- HPE Smart Array firmware: warning, current 1.98, baseline requires manual
  approval.
- Cisco IOS XE: blocked, current unknown, required 17.9.
- Cisco bootloader/ROMMON: warning, current unknown.
- NetApp: not_configured_yet because NETAPP_CONFIGURED=false.
- Waiver: not configured.

## Implemented

- Firmware baseline manifest:
  `config/firmware-baselines/real-lab.yml`
- Firmware inventory/compliance service:
  `app/backend/app/services/firmware_compliance.py`
- Runner:
  `app/backend/scripts/firmware_compliance.py`
- Make targets:
  `provider-lab-firmware-inventory`,
  `provider-lab-firmware-compliance`,
  `provider-lab-firmware-waiver-check`
- API endpoints:
  `/api/v1/lab/firmware-inventory`,
  `/api/v1/lab/firmware-compliance`,
  `/api/v1/lab/firmware-waiver-check`
- Lab Builder Firmware Compliance stage between Lab Profile and Cisco Network.
- Gate checks before Cisco bootstrap/apply, HPE RAID apply/reset, ESXi media
  and boot workflow actions, NetApp setup workflow preview, and full rebuild
  execution.
- Waiver support through `FIRMWARE_WAIVER_CONFIRM`,
  `FIRMWARE_WAIVER_REASON`, `FIRMWARE_WAIVER_EXPIRES`,
  `FIRMWARE_WAIVER_SCOPE`, or local
  `artifacts/codex-runs/firmware-waiver.json`.

## Reports

- `artifacts/codex-runs/firmware-inventory-report.md`
- `artifacts/codex-runs/firmware-compliance-report.md`
- `artifacts/codex-runs/firmware-compliance-summary-redacted.json`
- `artifacts/codex-runs/firmware-waiver-report.md` is not present because no
  waiver is configured.
- `artifacts/screenshots/firmware-compliance-lab-builder.png`

## Verification

- `cd app/backend && PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_firmware_compliance.py tests/test_build_verification.py tests/test_full_rebuild_run.py tests/test_provider_status_adapters.py -q`
  passed.
- `cd app/backend && PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_firmware_compliance.py -q`
  passed after Smart Array version normalization.
- `cd app/frontend && PROVIDER_MODE=mock npm run build`
  passed.
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-firmware-compliance`
  completed real-lab inventory/compliance and exited nonzero because the gate is
  blocked, as expected.
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-firmware-waiver-check`
  passed with no waiver configured.
- `make app-start` confirmed the app was already running, and Playwright
  captured the Lab Builder screenshot showing Firmware Compliance between Lab
  Profile and Cisco Network.

## Next Action

Collect Cisco read-only version evidence (`show version` and boot/ROMMON
details) through the configured Cisco read-only path, then rerun
`make provider-lab-firmware-compliance`.
