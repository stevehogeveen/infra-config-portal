# Lab Validation / Handoff Report

- Generated at: `2026-06-10T00:37:36.522496+00:00`
- Overall status: `blocked`
- Secrets: not included; credential state is field-name only.
- Hardware workflows: no destructive workflow was run by this report.

## Lab Profile

- Lab subnet: 192.168.1.0/24
- iLO: 192.168.1.201
- Server NIC: 192.168.1.202
- ESXi: 192.168.1.203
- Cisco: 192.168.1.204
- Ansible/control host: 192.168.1.205
- NetApp controller A SP: 192.168.1.210
- NetApp controller B SP: 192.168.1.211
- NetApp cluster: 192.168.1.220
- NetApp node A: 192.168.1.221
- NetApp node B: 192.168.1.222
- NetApp SVM: 192.168.1.223
- NetApp NFS LIFs: 192.168.1.230, 192.168.1.231
- Saved profile `TDC-LAB` remains historical context only until refreshed.

## Setup Status By Component

| Component | Status | Setup Summary | Login / Proof | Next Action |
| --- | --- | --- | --- | --- |
| Lab Profile | `warning` | Known runtime lab addressing is loaded. | No login target; profile defines addresses only. | Refresh the saved active Lab Profile if it should replace the runtime profile. |
| Firmware Compliance | `partial` | Firmware reports are available as supporting evidence. | No direct login; use firmware workflow evidence. | Refresh firmware compliance when certification is in scope. |
| Cisco Network | `ready` | Cisco management is ready for SSH validation. | ssh admin@192.168.1.204 | Validate SSH/SCP from Run Center. |
| HPE / iLO | `partial` | iLO management target is known; credentials are reported by field presence only. | https://192.168.1.201 | Run iLO reachability before auth or inventory. |
| RAID / Storage | `partial` | RAID/storage evidence is supporting proof, not a primary blocker. | No separate login; use iLO/Smart Array workflow. | Refresh RAID plan/pending state before ESXi install work. |
| ESXi Host | `partial` | ESXi management is planned/configured enough to show the validation target. | https://192.168.1.203 | Refresh ESXi install/management readiness. |
| vCenter | `not_configured` | vCenter/govc is not configured yet. | VCENTER_HOST / GOVC_URL not configured; credentials not configured: VCENTER_HOST/GOVC_URL, VCENTER_USERNAME/GOVC_USERNAME, VCENTER_PASSWORD/GOVC_PASSWORD | Configure vCenter/govc fields, then rerun vCenter-NetApp readiness. |
| NetApp Console | `ready` | Console autodiscovery works; NetApp setup has not been applied yet. | /dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00 @ 115200 | Review setup plan; do not enter setup commands without a guarded apply workflow. |
| NetApp ONTAP / Cluster | `blocked` | ONTAP cluster is still in setup wizard. | https://192.168.1.220; credentials not configured: NETAPP_API_USERNAME, NETAPP_API_PASSWORD | Run NetApp setup preview and resolve missing intent before REST/SSH/NFS readiness. |
| NetApp ONTAP Upgrade | `blocked` | Current ONTAP version `unknown`; target `not selected`. | After setup: https://192.168.1.220 and admin@192.168.1.220; values stay redacted. | Resolve blockers, run validation, and keep upgrade apply disabled until all gates pass. |
| NetApp NFS | `blocked` | Planned datastore backing volume `esxi_datastore_01` is not live yet. | Datastore backing target: netapp_nfs_ds01 via 192.168.1.230 | Create/validate NFS after ONTAP setup completes. |
| vCenter-NetApp Datastore | `blocked` | vCenter-NetApp readiness is blocked by prior NetApp/ONTAP/NFS setup. | vCenter: VCENTER_HOST / GOVC_URL not configured; datastore: netapp_nfs_ds01 | Complete NetApp ONTAP setup and NFS readiness before vCenter datastore work. |
| Build Verification | `not_checked` | Current live Build Verification has not run in this runtime. The cached test-fixture summary is historical evidence only. | No login target; use proof/evidence reports. | Run `make provider-lab-build-verification-live`. |

## Current Blockers

- NetApp ONTAP / Cluster: NetApp ONTAP cluster setup has not been applied yet.
  - Next action: `make provider-lab-netapp-validate-setup`

## Evidence Links

- Lab Profile: `artifacts/codex-runs/lab-ip-profile-update-report.md`
- Lab Profile: `artifacts/codex-runs/lab-ip-profile-hardening-report.md`
- Firmware Compliance: `artifacts/codex-runs/firmware-compliance-report.md`
- Firmware Compliance: `artifacts/codex-runs/firmware-compliance-summary-redacted.json`
- Firmware Compliance: `artifacts/codex-runs/toolchain-availability-report.md`
- Cisco Network: `artifacts/codex-runs/serial-console-discovery-report.md`
- Cisco Network: `artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`
- Cisco Network: `artifacts/codex-runs/cisco-bootstrap-apply-report.md`
- HPE / iLO: `artifacts/codex-runs/ilo-real-run-report.md`
- HPE / iLO: `artifacts/codex-runs/ilo-local-readonly-smoke-report.md`
- RAID / Storage: `artifacts/codex-runs/hpe-raid-plan-report.md`
- RAID / Storage: `artifacts/codex-runs/hpe-raid-pending-report.md`
- ESXi Host: `artifacts/codex-runs/esxi-install-readiness-report.md`
- ESXi Host: `artifacts/codex-runs/esxi-installer-boot-report.md`
- NetApp Console: `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- NetApp Console: `artifacts/codex-runs/netapp-console-state-report.md`
- NetApp Console: `artifacts/codex-runs/netapp-console-login-state-report.md`
- NetApp ONTAP / Cluster: `artifacts/codex-runs/netapp-live-state-report.md`
- NetApp ONTAP / Cluster: `artifacts/codex-runs/netapp-setup-plan-report.md`
- NetApp ONTAP / Cluster: `artifacts/codex-runs/netapp-setup-preview-report.md`
- NetApp ONTAP Upgrade: `artifacts/codex-runs/netapp-upgrade-inventory-report.md`
- NetApp ONTAP Upgrade: `artifacts/codex-runs/netapp-ontap-upgrade-plan-report.md`
- NetApp ONTAP Upgrade: `artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md`
- NetApp NFS: `artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md`
- vCenter-NetApp Datastore: `artifacts/codex-runs/vcenter-netapp-readiness-report.md`
- vCenter-NetApp Datastore: `artifacts/codex-runs/vcenter-netapp-datastore-plan-report.md`
- Build Verification: `artifacts/codex-runs/build-verification-report.md`
- Build Verification: `artifacts/codex-runs/build-verification-summary-redacted.json`
- Build Verification: `artifacts/codex-runs/build-verification-evidence-report.md`

## What Remains

- Lab Profile: Refresh the saved active Lab Profile if it should replace the runtime profile.
- Firmware Compliance: Refresh firmware compliance when certification is in scope.
- HPE / iLO: Run iLO reachability before auth or inventory.
- RAID / Storage: Refresh RAID plan/pending state before ESXi install work.
- ESXi Host: Refresh ESXi install/management readiness.
- vCenter: Configure vCenter/govc fields, then rerun vCenter-NetApp readiness.
- NetApp ONTAP / Cluster: Run NetApp setup preview and resolve missing intent before REST/SSH/NFS readiness.
- NetApp ONTAP Upgrade: Resolve blockers, run validation, and keep upgrade apply disabled until all gates pass.
- NetApp NFS: Create/validate NFS after ONTAP setup completes.
- vCenter-NetApp Datastore: Complete NetApp ONTAP setup and NFS readiness before vCenter datastore work.
- Build Verification: Run `make provider-lab-build-verification-live`.

## Skill Improvement Review

- Skills used: lab-builder-skill-steward, lab-builder-real-runtime, lab-builder-ux, lab-builder-product-craft, lab-builder-hardware-run, lab-builder-report-remediation, lab-builder-toolchain, lab-builder-dual-app-architecture
- Skills created or updated: none
- Skill gaps found: none requiring a new reusable skill in this pass
- Candidate skills deferred: none
- No additional skills were created because this work fits the existing Lab Builder skill set.
