# Full Device Rebuild Baseline Report

## Summary

- Checked at: `2026-06-06T02:47:25.186897+00:00`
- Provider mode: `local-lab-readwrite`
- Env file: `.env.local.real-lab`
- Changed file count: `99`
- Real device calls from this run: `attempted`

## Changed Files

- `M .codex/task-queue.md`
- ` M Makefile`
- ` M README.md`
- ` M app/.env.example`
- ` M app/Makefile`
- ` M app/backend/app/api/routes.py`
- ` M app/backend/app/core/config.py`
- ` M app/backend/app/models.py`
- ` M app/backend/app/providers/cisco_ansible.py`
- ` M app/backend/app/providers/esxi_readonly.py`
- ` M app/backend/app/providers/ilo_redfish.py`
- ` M app/backend/app/providers/registry.py`
- ` M app/backend/app/schemas.py`
- ` M app/backend/app/services/lifecycle.py`
- ` M app/backend/app/services/media_inventory.py`
- ` M app/backend/scripts/cisco_real_lab_workflow.py`
- ` M app/backend/scripts/provider_smoke.py`
- ` M app/backend/tests/test_api.py`
- ` M app/backend/tests/test_provider_registry.py`
- ` M app/backend/tests/test_smoke_vm_lifecycle.py`
- ` M app/backend/tests/test_upgrade_decision.py`
- ` M app/backend/tests/test_workflow_execution.py`
- ` M app/docs/provider-adapters.md`
- ` M app/docs/security.md`
- ` M app/docs/workflows.md`
- ` M app/frontend/src/App.tsx`
- ` M app/frontend/src/api.ts`
- ` M app/frontend/src/styles.css`
- ` M artifacts/codex-runs/cisco-4h-lab-run-report.md`
- ` M artifacts/codex-runs/cisco-console-discovery-report.md`
- ` M artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`
- ` M artifacts/codex-runs/esxi-installer-boot-report.md`
- ` M artifacts/codex-runs/esxi-media-url-report.md`
- ` M artifacts/codex-runs/esxi-one-time-boot-report.md`
- ` M artifacts/codex-runs/esxi-virtual-media-report.md`
- ` M scripts/setup-real-lab-env.sh`
- `?? app/backend/alembic/versions/0003_hpe_raid_intent.py`
- `?? app/backend/app/providers/action_policy.py`
- `?? app/backend/app/services/build_verification.py`
- `?? app/backend/app/services/full_rebuild_run.py`
- `?? app/backend/app/services/hpe_raid.py`
- `?? app/backend/app/services/ilo_setup_apply.py`
- `?? app/backend/scripts/build_verification.py`
- `?? app/backend/scripts/esxi_install_workflow.py`
- `?? app/backend/scripts/full_device_rebuild_summary.py`
- `?? app/backend/scripts/full_device_rebuild_workflow.py`
- `?? app/backend/scripts/hpe_raid_plan.py`
- `?? app/backend/scripts/hpe_raid_workflow.py`
- `?? app/backend/scripts/ilo_real_reachability.py`
- `?? app/backend/tests/test_build_verification.py`
- `?? app/backend/tests/test_full_rebuild_run.py`
- `?? app/frontend/artifacts/`
- `?? artifacts/codex-runs/build-verification-report.md`
- `?? artifacts/codex-runs/build-verification-summary-redacted.json`
- `?? artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json`
- `?? artifacts/codex-runs/cisco-4h-lab-run-terminal.log`
- `?? artifacts/codex-runs/cisco-bootstrap-apply-report.md`
- `?? artifacts/codex-runs/cisco-bootstrap-commands-redacted.json`
- `?? artifacts/codex-runs/cisco-console-ethernet-readiness-redacted.json`
- `?? artifacts/codex-runs/cisco-console-samples-redacted.json`
- `?? artifacts/codex-runs/cisco-full-bootstrap-report.md`
- `?? artifacts/codex-runs/cisco-privilege-check-report.md`
- `?? artifacts/codex-runs/esxi-cisco-lab-run-terminal.log`
- `?? artifacts/codex-runs/esxi-full-rebuild-boot-report.md`
- `?? artifacts/codex-runs/esxi-install-readiness-report.md`
- `?? artifacts/codex-runs/esxi-media-http-server.log`
- `?? artifacts/codex-runs/esxi-media-http-server.pid`
- `?? artifacts/codex-runs/esxi-one-time-boot-after.json`
- `?? artifacts/codex-runs/esxi-one-time-boot-before.json`
- `?? artifacts/codex-runs/esxi-virtual-media-state.json`
- `?? artifacts/codex-runs/full-device-rebuild-4h-report.md`
- `?? artifacts/codex-runs/full-device-rebuild-4h-summary-redacted.json`
- `?? artifacts/codex-runs/full-device-rebuild-4h-terminal.log`
- `?? artifacts/codex-runs/full-device-rebuild-baseline-report.md`
- `?? artifacts/codex-runs/full-device-rebuild-execution-redacted.json`
- `?? artifacts/codex-runs/hpe-full-rebuild-ilo-report.md`
- `?? artifacts/codex-runs/hpe-full-rebuild-raid-report.md`
- `?? artifacts/codex-runs/hpe-raid-after-reset-validation-report.md`
- `?? artifacts/codex-runs/hpe-raid-apply-payload-redacted.json`
- `?? artifacts/codex-runs/hpe-raid-apply-report.md`

## Existing Report Inventory

- cisco_console: `present` `artifacts/codex-runs/cisco-4h-lab-run-report.md`
- cisco_privilege: `present` `artifacts/codex-runs/cisco-privilege-check-report.md`
- cisco_bootstrap_apply: `present` `artifacts/codex-runs/cisco-bootstrap-apply-report.md`
- ilo_reachability: `present` `artifacts/codex-runs/ilo-real-run-report.md`
- raid_discovery: `present` `artifacts/codex-runs/hpe-raid-discovery-report.md`
- raid_plan: `present` `artifacts/codex-runs/hpe-raid-plan-report.md`
- raid_pending: `present` `artifacts/codex-runs/hpe-raid-pending-report.md`
- raid_validate_after_reset: `present` `artifacts/codex-runs/hpe-raid-after-reset-validation-report.md`
- esxi_readiness: `present` `artifacts/codex-runs/esxi-install-readiness-report.md`
- esxi_media: `present` `artifacts/codex-runs/esxi-media-url-report.md`
- esxi_virtual_media: `present` `artifacts/codex-runs/esxi-virtual-media-report.md`
- esxi_one_time_boot: `present` `artifacts/codex-runs/esxi-one-time-boot-report.md`
- esxi_installer_boot: `present` `artifacts/codex-runs/esxi-installer-boot-report.md`

## Safety

- No secrets or raw console transcripts are included.
