# Overnight Lab Builder Final Report

## Summary

- Final checked at: `2026-06-06T02:49:16Z`
- Provider mode: `local-lab-readwrite`
- Env file requested: `.env.local.real-lab`
- Mock results used as substitutes for real lab evidence: `false`
- Overall result: `blocked`
- Primary real blocker: Cisco console reaches exec prompt, but privileged exec is not confirmed.

## Implemented Changes

- Split full rebuild targets:
  - `make provider-lab-full-rebuild-summary`: report-only, no live device calls.
  - `make provider-lab-full-rebuild`: real local-lab-readwrite execution path.
- Updated the real full rebuild runner to call live Cisco, iLO, HPE RAID, and ESXi workflow stages and to avoid blocking only because the caller is Codex or `codex exec`.
- Fixed Cisco target IP handling so configured `10.10.8.112` is not remapped to another address.
- Hardened Cisco enable escalation to handle username-first enable challenges, `enable`, and `enable 15` without printing secrets.
- Added Build Verification / Product Certification:
  - backend service
  - `make provider-lab-build-verification`
  - `GET /api/v1/lab/build-verification`
  - Provider Status UI panel
  - tests for credential escaping, MTU consistency, protocol readiness, and failure reporting
- Improved HPE RAID discovery reporting so failed discovery writes explicit blocker sections.
- Updated README and workflow docs for the split real-vs-summary rebuild behavior.

## Real Full Rebuild Result

Latest aggregate report: `artifacts/codex-runs/full-device-rebuild-4h-report.md`

- `baseline`: completed
- `cisco_console_bootstrap`: blocked
- `ilo_reachability_inventory`: completed
- `hpe_raid_discovery`: completed
- `hpe_raid_plan`: completed
- `hpe_raid_pending`: completed
- `esxi_media_url`: completed
- `esxi_insert_virtual_media`: completed
- `esxi_one_time_boot`: completed
- `esxi_reset_installer_boot`: completed
- `esxi_detect_installer`: completed
- `cisco_bootstrap`: blocked
- `hpe_ilo`: completed
- `hpe_raid`: completed
- `esxi_boot`: completed

Blocker:

- Privileged exec prompt is required for Cisco bootstrap apply.

## Cisco

- Console auto-discovery selected `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0`.
- Prompt detection succeeded at `9600` baud.
- Prompt state: `exec`.
- Enable escalation was attempted with the configured redacted credential sources and remained at exec prompt.
- Bootstrap plan is ready and redacted, including hostname, management interface/IP, local admin, SSH v2, SCP enablement, line login local, LLDP, and save config.
- Bootstrap apply did not run because privileged exec was not confirmed.
- Ethernet ping/SSH/SCP validation did not run because bootstrap apply did not run.

Reports:

- `artifacts/codex-runs/cisco-4h-lab-run-report.md`
- `artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json`
- `artifacts/codex-runs/cisco-bootstrap-commands-redacted.json`

## HPE / iLO / RAID

- iLO reachability/inventory stage completed in the final full rebuild run.
- RAID discovery recovered after an intermittent unreachable result.
- Latest RAID discovery found HPE Smart Array P408i-a SR Gen10, 8 physical drives, and 2 logical drives.
- Current logical drives:
  - `ESXi-OS` RAID1, 500.0 GiB, health OK
  - `VM-Datastore` RAID6, 3.27 TiB, health OK
- RAID plan status is warning because destructive apply remains gated by `HPE_RAID_ALLOW_DESTRUCTIVE=true` and confirmation phrase `APPLY HPE RAID PLAN`.

Reports:

- `artifacts/codex-runs/ilo-real-run-report.md`
- `artifacts/codex-runs/hpe-raid-discovery-report.md`
- `artifacts/codex-runs/hpe-raid-plan-report.md`
- `artifacts/codex-runs/hpe-full-rebuild-raid-report.md`

## ESXi

- ESXi media URL stage completed.
- iLO VirtualMedia insert stage completed.
- One-time boot stage completed in the final aggregate run.
- Reset installer boot stage completed in the final aggregate run.
- ESXi installer/host state detection completed through Redfish.

Reports:

- `artifacts/codex-runs/esxi-media-url-report.md`
- `artifacts/codex-runs/esxi-virtual-media-report.md`
- `artifacts/codex-runs/esxi-one-time-boot-report.md`
- `artifacts/codex-runs/esxi-installer-boot-report.md`
- `artifacts/codex-runs/esxi-full-rebuild-boot-report.md`

## Build Verification

Latest report: `artifacts/codex-runs/build-verification-report.md`

Status: `blocked`

Blockers:

- NetApp credential compatibility/configuration is missing; value remains redacted.
- Cisco SSH/SCP required port is not reachable.
- ESXi API required port is not reachable.
- ESXi SSH required port is not reachable.
- NetApp REST required port is not reachable.
- NetApp SSH required port is not reachable.

## Tests And Checks

- `cd app/backend && PROVIDER_MODE=mock .venv/bin/pytest -q`: passed, `201 passed`.
- `cd app/frontend && PROVIDER_MODE=mock npm run build`: passed.
- `make provider-lab-full-rebuild-summary`: passed.
- `make provider-lab-full-rebuild`: completed live stages as far as possible, final status blocked by Cisco privileged exec.
- `make provider-lab-build-verification`: generated report and exited nonzero because certification blockers are present.

## UI Validation

- Provider Status API checks succeeded for `GET /api/v1/lab/build-verification`.
- Frontend production build succeeded.
- Screenshot capture was attempted. Playwright was not installed, and Firefox headless screenshot hung with an isolated profile, so no screenshot artifact was produced.
- Manual HTTP checks confirmed the frontend served `/providers` from Vite and the backend returned the build verification payload.

## Next Actions

1. Resolve Cisco privileged exec on the console path. The app now proves console discovery, prompt detection, and bootstrap planning; it blocks only because enable escalation does not reach `#`.
2. After privileged exec is confirmed, rerun `make provider-lab-full-rebuild` to apply Cisco bootstrap and validate ping/SSH/SCP.
3. Decide whether RAID destructive apply is intended; if yes, set the explicit RAID destructive gate and confirmation phrase before applying.
4. Configure or disable NetApp certification inputs for this lab run so Build Verification can distinguish intentionally absent NetApp from a failed NetApp path.
5. Re-run `make provider-lab-build-verification` after Cisco management and ESXi API/SSH are reachable.
