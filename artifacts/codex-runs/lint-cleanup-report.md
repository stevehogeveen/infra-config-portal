# Backend lint cleanup report

Date: 2026-06-08

## Scope

- Focused backend lint cleanup in `/home/administrator/infra-config-portal`.
- No provider workflow behavior was intentionally changed.
- No destructive provider targets were run.
- No secrets or `.env.local.real-lab` values were printed or recorded.

## Initial Ruff findings

`make lint` initially failed with 32 Ruff findings:

- `F541` `app/backend/app/providers/action_policy.py:204` f-string without any placeholders.
- `F401` `app/backend/app/services/esxi_boot_workflow.py:25` `_response_summary` imported but unused.
- `F401` `app/backend/app/services/esxi_install_readiness.py:3` `json` imported but unused.
- `F401` `app/backend/app/services/esxi_install_readiness.py:5` `Path` imported but unused.
- `F401` `app/backend/app/services/esxi_install_readiness.py:18` `_resource_body_or_error` imported but unused.
- `F401` `app/backend/app/services/ilo_setup_apply.py:19` `PROVIDER_ID` imported but unused.
- `F401` `app/backend/app/services/netapp_real_lab.py:10` `asdict` imported but unused.
- `F401` `app/backend/scripts/cisco_console_ethernet_readiness.py:5` `Path` imported but unused.
- `F401` `app/backend/scripts/cisco_real_lab_workflow.py:20` `CiscoConsoleAdapter` imported but unused.
- `F401` `app/backend/scripts/firmware_compliance.py:7` `get_firmware_compliance` imported but unused.
- `F401` `app/backend/scripts/full_device_rebuild_workflow.py:5` `build_full_rebuild_reports` imported but unused.
- `F401` `app/backend/scripts/hpe_raid_workflow.py:18` `CONFIRMATION_PHRASE` imported but unused.
- `E402` `app/backend/scripts/ilo_real_reachability.py:27` module-level import not at top of file.
- `E402` `app/backend/scripts/ilo_real_reachability.py:28` module-level import not at top of file.
- `E402` `app/backend/scripts/ilo_real_reachability.py:29` module-level import not at top of file.
- `E402` `app/backend/scripts/ilo_real_reachability.py:30` module-level import not at top of file.
- `E402` `app/backend/scripts/netapp_real_run_readiness.py:21` module-level import not at top of file.
- `E402` `app/backend/scripts/netapp_real_run_readiness.py:22` module-level import not at top of file.
- `E402` `app/backend/scripts/netapp_real_run_readiness.py:23` module-level import not at top of file.
- `E402` `app/backend/scripts/netapp_real_run_readiness.py:24` module-level import not at top of file.
- `E402` `app/backend/scripts/netapp_real_run_readiness.py:25` module-level import not at top of file.
- `E402` `app/backend/scripts/netapp_real_run_readiness.py:26` module-level import not at top of file.
- `E402` `app/backend/scripts/netapp_real_run_readiness.py:27` module-level import not at top of file.
- `E402` `app/backend/scripts/provider_smoke.py:33` module-level import not at top of file.
- `E402` `app/backend/scripts/provider_smoke.py:34` module-level import not at top of file.
- `E402` `app/backend/scripts/provider_smoke.py:35` module-level import not at top of file.
- `E402` `app/backend/scripts/provider_smoke.py:36` module-level import not at top of file.
- `E402` `app/backend/scripts/provider_smoke.py:37` module-level import not at top of file.
- `E402` `app/backend/scripts/provider_smoke.py:38` module-level import not at top of file.
- `E402` `app/backend/scripts/provider_smoke.py:39` module-level import not at top of file.
- `E402` `app/backend/scripts/provider_smoke.py:40` module-level import not at top of file.
- `E402` `app/backend/scripts/provider_smoke.py:41` module-level import not at top of file.

## Changes made

- Removed unused imports reported by Ruff.
- Removed the unnecessary f-string prefix in `action_policy.py`.
- Preserved `.env.local.real-lab` load order in:
  - `app/backend/scripts/ilo_real_reachability.py`
  - `app/backend/scripts/netapp_real_run_readiness.py`
  - `app/backend/scripts/provider_smoke.py`
- Added targeted `# noqa: E402` comments to the intentional late app imports in those scripts, with a short comment explaining that local lab env is loaded before app settings imports.

## Verification

- `make lint` passed.
  - Ruff: `All checks passed!`
  - Frontend build invoked by the lint wrapper completed successfully.
- `make test` passed.
  - Backend pytest: `271 passed in 157.47s (0:02:37)`
  - Frontend build invoked by the test wrapper completed successfully.
