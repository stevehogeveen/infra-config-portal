# Provider Lab Live Status

- Checked at: `2026-06-09T16:03:13.331103+00:00`
- Status: `blocked`
- Source: `live_probe`
- Runtime mode: `local-lab-readwrite`

## Stages

- `completed` `ilo-reachability` report=`artifacts/codex-runs/ilo-real-run-report.md`
- `blocked` `cisco-console-ethernet` report=`artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`
  - Blocker: cisco-console-ethernet exceeded 20 seconds; rerun the specific live check or inspect `artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`.
- `ready` `netapp-console-autodiscovery` report=`artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- `ready` `netapp-console-read-state` report=`artifacts/codex-runs/netapp-console-state-report.md`
- `blocked` `netapp-live-state` report=`artifacts/codex-runs/netapp-live-state-report.md`
  - Blocker: NetApp cluster management REST is not reachable.
  - Blocker: NetApp API access values are missing; keep any values local and redacted.
- `blocked` `firmware-compliance` report=`artifacts/codex-runs/firmware-compliance-report.md`
  - Blocker: iLO HPE iLO firmware: current unknown, required 3.19; Current firmware or OS version is unknown. Next action: Inventory iLO through Redfish, then stage an approved HPE iLO firmware package if the version is below baseline.
  - Blocker: Cisco Cisco IOS XE version: current unknown, required 17.9; Current firmware or OS version is unknown. Next action: Run Cisco firmware inventory from console.
- `blocked` `build-verification` report=`artifacts/codex-runs/build-verification-current-state-report.md`
  - Blocker: Live check: Restore readiness for iLO Redfish: iLO Redfish required port is not reachable.
  - Blocker: Live check: Restore readiness for iLO XML fallback: iLO XML fallback required port is not reachable.
  - Blocker: Live check: Restore readiness for Cisco SSH/SCP: Cisco SSH/SCP required port is not reachable.
  - Blocker: Live check: Restore readiness for ESXi API: ESXi API required port is not reachable.
  - Blocker: Live check: Restore readiness for ESXi SSH: ESXi SSH required port is not reachable.
  - Blocker: Last live result: Use approved credentials only through the live validation path; do not paste secrets into the UI.
  - Blocker: Last live result: Use approved credentials only through the live validation path; do not paste secrets into the UI.
  - Blocker: Not checked: Use console/API read-only discovery to identify the NetApp state, then configure vCenter/govc before NFS datastore apply is implemented.

## Evidence

- `artifacts/codex-runs/ilo-real-run-report.md`
- `artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`
- `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- `artifacts/codex-runs/netapp-console-state-report.md`
- `artifacts/codex-runs/netapp-live-state-report.md`
- `artifacts/codex-runs/firmware-compliance-report.md`
- `artifacts/codex-runs/build-verification-current-state-report.md`

## Safety

- No secrets or raw console transcripts are printed.
