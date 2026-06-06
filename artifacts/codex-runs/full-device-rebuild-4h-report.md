# Full Device Rebuild 4h Report

## Summary

- Checked at: `2026-06-06T02:47:25.186897+00:00`
- Overall status: `blocked`
- Provider mode: `local-lab-readwrite`
- Mock results used: `False`

## Stage Status

- baseline: `completed` - Baseline captured before live stages.
- cisco_console_bootstrap: `blocked` - Live stage completed with redacted output captured.
- ilo_reachability_inventory: `completed` - redfish_root_available
- hpe_raid_discovery: `completed` - Live stage completed with redacted output captured.
- hpe_raid_plan: `completed` - Live stage completed with redacted output captured.
- hpe_raid_pending: `completed` - Live stage completed with redacted output captured.
- esxi_media_url: `completed` - Selected ESXi ISO media URL is ready.
- esxi_insert_virtual_media: `completed` - ESXi ISO is inserted through iLO VirtualMedia.
- esxi_one_time_boot: `completed` - One-time boot target set to Cd.
- esxi_reset_installer_boot: `completed` - Server reset completed and ESXi installer boot was requested.
- esxi_detect_installer: `completed` - ESXi installer or installed ESXi boot state is visible through iLO Redfish.
- cisco_bootstrap: `blocked` - Live stage completed with redacted output captured.
- hpe_ilo: `completed` - redfish_root_available
- hpe_raid: `completed` - HPE RAID discovery, plan, and pending checks ran.
- esxi_boot: `completed` - ESXi media, VirtualMedia, boot override, and installer detection stages ran.

## Blockers

- Privileged exec prompt is required for bootstrap apply.

## Artifacts

- baseline: `artifacts/codex-runs/full-device-rebuild-baseline-report.md`
- cisco_privilege: `artifacts/codex-runs/cisco-privilege-check-report.md`
- cisco_bootstrap: `artifacts/codex-runs/cisco-full-bootstrap-report.md`
- hpe_ilo: `artifacts/codex-runs/hpe-full-rebuild-ilo-report.md`
- hpe_raid: `artifacts/codex-runs/hpe-full-rebuild-raid-report.md`
- esxi_boot: `artifacts/codex-runs/esxi-full-rebuild-boot-report.md`
- final: `artifacts/codex-runs/full-device-rebuild-4h-report.md`
- execution_summary_json: `artifacts/codex-runs/full-device-rebuild-execution-redacted.json`

## Next Safe Action

Privileged exec prompt is required for bootstrap apply.
