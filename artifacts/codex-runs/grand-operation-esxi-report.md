# Grand Operation Stage 6 - ESXi Rebuild/Configuration Report

Checked at: 2026-06-10T23:04:41Z
Scope: local real lab, ESXi target `192.168.1.203`

## Result

- Status: validated existing ESXi install; fresh wipe/reinstall was not executed.
- ESXi management IP: `192.168.1.203`
- HTTPS/API 443: reachable.
- SSH 22: reachable.
- Version: VMware ESXi `8.0.3`, build `24859861`, API `8.0.3.0`.
- Redfish HostOS evidence: `VMware ESXi`, `8.0.3 Build-24859861 Update 3 Patch 79`.
- Local datastore: `datastore1`, VMFS, accessible, capacity `399163523072`, free `374440198144`.
- `govc`: available from repo-local `.local/bin`; `govc about` and `govc datastore.info` succeeded.

## Rebuild Path Attempted

- Install readiness was ready for ProLiant DL360 Gen10 with virtual media, ISO media, one-time boot, and BIOS settings support.
- Selected ISO was the local HPE ESXi 8.0.3 media from `artifacts/Media`.
- The app generated a local media URL and inserted the ESXi ISO via iLO virtual media.
- One-time boot was set to CD.
- Server power was off before the first boot request. The app incorrectly tried `ForceRestart`; iLO rejected that because the host was off.
- The boot workflow was fixed to power on an off server, to fallback from `ForceRestart` to `On` for that iLO response, and to wait for powered state instead of only iLO reachability.
- Retry powered the server on and observed the installed ESXi state.
- Virtual media was ejected after validation.
- No boot override is queued; final boot source override is disabled.

## Why A Fresh Wipe/Reinstall Was Not Performed

- The current app has readiness, virtual-media boot, and detection lanes, but no completed unattended ESXi kickstart/apply lane that can safely wipe and reinstall end to end.
- The host already runs the target ESXi 8.0.3 HPE build matching available media.
- Management, API, SSH, and datastore checks passed live after the boot workflow was exercised.
- Treating this as validated existing install is the accurate current result; unattended rebuild remains product/runtime work.

## App Fixes From This Stage

- `app/backend/app/services/esxi_boot_workflow.py`: handles powered-off servers correctly during installer boot requests and reports failed reset responses as blockers.
- `app/backend/tests/test_esxi_boot_workflow.py`: added coverage for power-on behavior when the server is off.
- `app/backend/app/services/lab_profiles.py`: profile apply no longer forces `CISCO_MGMT_CONFIGURED=false` and `ESXI_CONFIGURED=false`, so active lab setup does not hide completed real-lab configuration.
- `app/backend/tests/test_api.py`: updated profile runtime assertions for the new behavior.
- `.env.local.real-lab`: non-secret local flags were updated to mark Cisco and ESXi management configured for this run.
- `app/backend/app/providers/esxi_readonly.py`: ESXi tool availability now checks active venv and repo-local `.local/bin`, so `govc` installed by the toolchain stage is reported.
- `app/backend/tests/test_provider_status_adapters.py`: added regression coverage for repo-local `govc` discovery.

## Validation

- Focused ESXi boot workflow tests passed.
- Focused provider adapter tests passed.
- Ruff checks passed for changed ESXi/provider files.
- App restarted successfully after the profile/env update.
- Provider smoke for `esxi-readonly` passed in `local-lab-readwrite` mode:
  - provider status: `ready`
  - read-only probe status: `ok`
  - HTTPS reachable: true
  - SSH reachable: true
  - VIM service versions available: true
  - `govc_available`: true

## Evidence

- `artifacts/codex-runs/esxi-install-readiness-report.md`
- `artifacts/codex-runs/esxi-media-url-report.md`
- `artifacts/codex-runs/esxi-virtual-media-report.md`
- `artifacts/codex-runs/esxi-one-time-boot-report.md`
- `artifacts/codex-runs/esxi-installer-boot-report.md`
- `artifacts/codex-runs/esxi-virtual-media-eject-report.md`
- `artifacts/codex-runs/esxi-management-validation-report.md`
- `artifacts/real-lab/provider-smoke-20260610T230441Z.md`

## Remaining ESXi Work

- Implement a guarded unattended ESXi reinstall lane with explicit wipe confirmation, kickstart generation, install progress detection, and post-install host configuration.
- Add product UI language that distinguishes validated existing ESXi from a completed fresh reinstall.
