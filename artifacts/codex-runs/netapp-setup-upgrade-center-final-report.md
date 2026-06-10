# NetApp Setup + ONTAP Upgrade Center Final Report

Checked at: 2026-06-10T00:45:00Z

## Scope

- Repository: `/home/administrator/infra-config-portal`
- Provider mode used for real-lab validation: `local-lab-readwrite`
- Env seed: `.env.local.real-lab`
- Setup apply run: `no`
- ONTAP upgrade apply run: `no`
- Mock results used as real lab state: `no`
- Secrets printed or written: `no`

## Current NetApp State

- Console adapter: `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00`
- Baud: `115200`
- Console prompt/state: `cluster_setup_prompt`
- Detected state: `cluster_setup_wizard`
- Planned NetApp addresses scanned for planning: `unused_free`
- NetApp REST/SSH: not configured yet
- NFS datastore: not created yet
- ONTAP current version: unknown
- ONTAP target/image package: not selected

## Implementation Summary

- Added a NetApp setup intent service with setup baseline, setup plan, setup preview, guarded setup apply refusal, remediation items, and redacted report generation.
- Added an ONTAP Upgrade Center backend service with inventory, plan, validation, guarded apply refusal, legacy upgrade-readiness compatibility, local media inventory handling, and button-state modeling.
- Added root/app Make targets:
  - `make provider-lab-netapp-setup-baseline`
  - `make provider-lab-netapp-setup-plan`
  - `make provider-lab-netapp-setup-preview`
  - `make provider-lab-netapp-setup-apply`
  - `make provider-lab-netapp-post-setup-validation`
  - `make provider-lab-netapp-ontap-upgrade-inventory`
  - `make provider-lab-netapp-ontap-upgrade-plan`
  - `make provider-lab-netapp-ontap-upgrade-validate`
  - `make provider-lab-netapp-ontap-upgrade-apply`
- Added API endpoints for setup preview/apply and ONTAP upgrade inventory/plan/validate/apply.
- Added NetApp Setup / ONTAP Upgrade Center controls in Run Center with disabled setup and upgrade apply buttons.
- Added workflow registry/control actions for setup preview/apply, post-setup validation, ONTAP upgrade inventory/plan/validate/apply, and component firmware inventory.
- Added a Lab Validation NetApp ONTAP Upgrade row with current version, target, login hint after setup, evidence links, and next action.

## Reports Saved

- `artifacts/codex-runs/netapp-setup-upgrade-baseline-report.md`
- `artifacts/codex-runs/netapp-setup-plan-report.md`
- `artifacts/codex-runs/netapp-setup-preview-report.md`
- `artifacts/codex-runs/netapp-upgrade-inventory-report.md`
- `artifacts/codex-runs/netapp-ontap-upgrade-plan-report.md`
- `artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md`
- `artifacts/codex-runs/lab-validation-handoff-report.md`
- `artifacts/codex-runs/lab-validation-summary-redacted.json`

## UI Screenshots

- `artifacts/screenshots/netapp-setup-upgrade-center.png`
- `artifacts/screenshots/netapp-setup-preview.png`
- `artifacts/screenshots/netapp-upgrade-disabled-before-setup.png`
- `artifacts/screenshots/netapp-validation-netapp-upgrade.png`

## Safe Validation Commands Run

- `PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-console-read-state`
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-setup-baseline`
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-setup-plan`
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-setup-preview`
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-ontap-upgrade-inventory`
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-ontap-upgrade-plan`
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-ontap-upgrade-validate`
- `PROVIDER_MODE=local-lab-readwrite make provider-lab-validation`

## Final Validation

- `make lint` passed.
- `make test` passed: `344 passed`.
- `cd app/frontend && npm run build` passed.

## Next Action

Set the missing setup intent values in `.env.local.real-lab`, add a real ONTAP image package under the configured media inventory path, rerun setup preview and upgrade inventory/plan/validate, and keep setup/upgrade apply disabled until the exact confirmation flags are intentionally present.

## Skill Improvement Review

- Skills used: `lab-builder-skill-steward`, `lab-builder-real-runtime`, `lab-builder-ux`, `lab-builder-product-craft`, `lab-builder-hardware-run`, `lab-builder-report-remediation`, `lab-builder-toolchain`, `lab-builder-dual-app-architecture`.
- Skills created or updated: none.
- Skill gaps found: a reusable NetApp setup/upgrade execution skill may be useful after a real guarded apply has been run once.
- Candidate skills deferred: NetApp setup apply and ONTAP upgrade apply operator runbook skill.
- Reason no additional skills were created: this pass introduced the workflow surfaces and guards; a reusable execution skill should be based on an observed apply run, not a preview-only pass.
