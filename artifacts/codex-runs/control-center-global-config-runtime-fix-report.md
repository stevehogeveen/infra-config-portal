# Control Center Global Config Runtime Fix Report

Generated: 2026-06-10

## Scope

- AGENTS.md UTF-8 validation: passed.
- Skills used: lab-builder-skill-steward, lab-builder-ux, lab-builder-product-craft, lab-builder-real-runtime, lab-builder-toolchain, lab-builder-hardware-run, lab-builder-report-remediation.
- Real hardware action run: one read-only Cisco firmware inventory action through the safe UI runner.
- No apply, reset, reload, firmware update, RAID change, virtual media change, boot-order change, or provider write action was run.

## Results

- Sidebar blocked badge: removed for the current report payload. Report Center now returns `critical: 0` and warning-only page badges for Dashboard, Control Center, Firmware, Verification, and Reports.
- Firmware unknown evidence: Cisco IOS XE unknown version is warning, not critical. Observed below-minimum firmware remains critical.
- Check Firmware timeout: the Cisco read-only firmware action now has a 35s safe runner timeout. The live run returned a failed trace instead of hanging.
- Control Center config UX: global DNS, NTP, SNMP, IPv6, VLAN, MTU, domain, and storage protocol are editable from the active saved lab profile and shown in compact device config rows.
- Actions / Configs UX: replaced large option cards with compact rows showing option, desired global value, status, and execution path.

## Live Safe-Runner Evidence

- Action: `cisco.firmware-inventory`
- Status: `failed`
- Executed: `true`
- Blocker: `Command exceeded the 35s safe action runner timeout.`
- Report artifact: `artifacts/codex-runs/cisco-firmware-inventory-report.md`
- Trace artifact: `artifacts/codex-runs/workflow-action-runs/20260610T193353Z__cisco.firmware-inventory__workflow-action-cisco.firmware-inventory-22e6feeb39b0.json`

## Browser Verification

- Page checked: `/control-center?section=cisco`
- Sidebar contained `Blocked`: `false`
- Inline firmware panel class: `inline-firmware-panel warning`
- Check Firmware button: visible
- Active global config values observed:
  - DNS: `8.8.8.8`
  - NTP: enabled, no server value set
  - SNMP: disabled by global profile
  - IPv6: disabled by global profile
  - Storage protocol: `nfs`

## Validation Commands

- `npm run build`
- `app/backend/.venv/bin/pytest app/backend/tests/test_report_center.py::test_report_center_firmware_unknown_version_issue_is_warning app/backend/tests/test_report_center.py::test_report_center_firmware_observed_below_minimum_stays_critical app/backend/tests/test_workflow_action_runner.py::test_cisco_firmware_inventory_uses_short_ui_timeout`
- `curl -fsS http://127.0.0.1:8001/api/v1/reports/issues`
- `curl -fsS http://127.0.0.1:8001/api/v1/workflows/actions/cisco.firmware-inventory`
- `curl -fsS -X POST http://127.0.0.1:8001/api/v1/workflows/actions/cisco.firmware-inventory/run`
- Playwright browser checks against `http://127.0.0.1:5173/control-center?section=cisco`

## Blockers

- Cisco version collection still does not complete through the live read-only path. It now fails fast with a saved trace instead of timing out the UI.
- Active profile has DNS set to `8.8.8.8`; NTP is enabled but no NTP server is set.

## Skill Improvement Review

- Skills created or updated: none.
- Skill gaps found: none that justify a new skill.
- Candidate skills deferred: none.
