# Golden State Productization Report

- Generated at: `2026-06-17T16:04:09.717030+00:00`
- Status: `blocked`
- Real hardware workflow run by this report: `False`
- Secrets: not included; credentials are configured/tested status only.

## Golden State Rows

| Component | Golden State | Current State | Drift | Repair Action |
| --- | --- | --- | --- | --- |
| Cisco | Reachable and configured | Not checked from this app host; no local IPv4 address is on 10.10.8.0/24. | `not_checked` | `ip -4 -o addr show scope global` |
| iLO | Reachable at 10.10.8.200 | Not checked from this app host; no local IPv4 address is on 10.10.8.0/24. | `not_checked` | `ip -4 -o addr show scope global` |
| RAID | Saved RAID intent validated | Not checked from this app host; no local IPv4 address is on 10.10.8.0/24. | `not_checked` | `ip -4 -o addr show scope global` |
| ESXi | Reachable at 10.10.8.202 | Not checked from this app host; no local IPv4 address is on 10.10.8.0/24. | `not_checked` | `ip -4 -o addr show scope global` |
| NetApp | ONTAP 9.17.1 current | Not checked from this app host; no local IPv4 address is on 10.10.8.0/24. | `not_checked` | `ip -4 -o addr show scope global` |
| NetApp NFS datastore | Mounted read/write on ESXi | Not checked from this app host; no local IPv4 address is on 10.10.8.0/24. | `not_checked` | `ip -4 -o addr show scope global` |
| VM deployment | VM deployed on NetApp datastore | Not checked from this app host; no local IPv4 address is on 10.10.8.0/24. | `not_checked` | `ip -4 -o addr show scope global` |
| vCenter | Enabled only when vCenter is in the active lab setup | Not in scope for the active lab setup | `none` | `make provider-lab-build-verification-live` |
| Firmware / software | Required firmware/software components are current or explicitly accepted | 7 components need manual review: Cisco - Cisco ROMMON / bootloader, iLO - iLO firmware, HPE Server - HPE BIOS, HPE Smart Array - Smart Array firmware, NetApp - NetApp disk firmware | `manual_review` | `make provider-lab-firmware-compliance` |

## Credential Status

| Provider | Configured | Tested | Next Action |
| --- | --- | --- | --- |
| iLO | `False` | `False` | Configure local credential values and rerun the linked validation. |
| Cisco | `False` | `False` | Configure local credential values and rerun the linked validation. |
| ESXi | `True` | `True` | No credential action required. |
| NetApp | `True` | `True` | No credential action required. |
| vCenter | `True` | `True` | No credential action required. |

## vCenter Readiness

- VCSA ISO: `not_in_scope`
- vcsa-deploy: `not_in_scope`
- ESXi: `not_in_scope`
- NetApp datastore: `not_in_scope`
- Management IP available: `not_in_scope`
- vCenter values: `not_in_scope`
- vCenter credentials: `not_in_scope`
- vCenter config: `not_in_scope`
- Preview state: `not_in_scope`
- Deploy state: `not_in_scope`
- Deploy enabled: `False`
- Next action: Enable vCenter in the active lab setup when this lane is intentionally in scope.

## Workflow Actions

- Run Full Lab Validation: `make provider-lab-validation`
- Run Full Lab Build Plan: `make provider-lab-full-rebuild-summary`
- Run Full Lab Repair: `make provider-lab-golden-state`
- Generate Handoff Report: `make provider-lab-golden-state`

## Drift

- Cisco: `not_checked` - Not checked from this app host; no local IPv4 address is on 10.10.8.0/24.
- iLO: `not_checked` - Not checked from this app host; no local IPv4 address is on 10.10.8.0/24.
- RAID: `not_checked` - Not checked from this app host; no local IPv4 address is on 10.10.8.0/24.
- ESXi: `not_checked` - Not checked from this app host; no local IPv4 address is on 10.10.8.0/24.
- NetApp: `not_checked` - Not checked from this app host; no local IPv4 address is on 10.10.8.0/24.
- NetApp NFS datastore: `not_checked` - Not checked from this app host; no local IPv4 address is on 10.10.8.0/24.
- VM deployment: `not_checked` - Not checked from this app host; no local IPv4 address is on 10.10.8.0/24.
- Firmware / software: `manual_review` - 7 components need manual review: Cisco - Cisco ROMMON / bootloader, iLO - iLO firmware, HPE Server - HPE BIOS, HPE Smart Array - Smart Array firmware, NetApp - NetApp disk firmware

## Evidence

- `artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`
- `artifacts/codex-runs/ilo-real-run-report.md`
- `artifacts/codex-runs/hpe-raid-after-reset-validation-report.md`
- `artifacts/codex-runs/esxi-post-recovery-validation-report.md`
- `artifacts/codex-runs/netapp-live-state-report.md`
- `artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md`
- `artifacts/codex-runs/esxi-netapp-nfs-datastore-validation-report.md`
- `artifacts/codex-runs/esxi-vm-deploy-validation-report.md`
- `artifacts/codex-runs/vcenter-install-readiness-report.md`
- `artifacts/codex-runs/vcenter-post-attach-validation-report.md`
- `artifacts/codex-runs/firmware-compliance-report.md`
- `artifacts/codex-runs/firmware-compliance-summary-redacted.json`

## Skill Improvement Review

- Skills used: lab-builder-skill-steward, lab-builder-real-runtime, lab-builder-hardware-run, lab-builder-toolchain, lab-builder-ux, lab-builder-product-craft, lab-builder-report-remediation
- Skills created or updated: none
- Skill gaps found: none requiring a new reusable skill in this pass
- Candidate skills deferred: none
- No additional skills were created because this work fits the existing Lab Builder skill set.
