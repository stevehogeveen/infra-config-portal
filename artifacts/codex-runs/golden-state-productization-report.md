# Golden State Productization Report

- Generated at: `2026-06-14T18:53:13.113323+00:00`
- Status: `partial`
- Real hardware workflow run by this report: `False`
- Secrets: not included; credentials are configured/tested status only.

## Golden State Rows

| Component | Golden State | Current State | Drift | Repair Action |
| --- | --- | --- | --- | --- |
| Cisco | Reachable and configured | Reachable/configured | `none` | `make provider-lab-cisco-console-ethernet-readiness` |
| iLO | Reachable at 192.168.1.201 | Reachable | `none` | `make provider-lab-ilo-reachability` |
| RAID | Saved RAID intent validated | Validated | `none` | `make provider-lab-hpe-raid-validate-after-reset` |
| ESXi | Reachable at 192.168.1.203 | Reachable | `none` | `make provider-lab-esxi-post-recovery-validation` |
| NetApp | ONTAP 9.17.1 current | ONTAP 9.17.1 | `none` | `make provider-lab-netapp-validate-setup` |
| NetApp NFS datastore | Mounted read/write on ESXi | netapp_nfs_ds01 readWrite | `none` | `make provider-lab-esxi-netapp-datastore-validate` |
| VM deployment | VM deployed on NetApp datastore | VM on netapp_nfs_ds01 | `none` | `make provider-lab-esxi-vm-deploy-validate` |
| vCenter | Configured and reachable | Deployed and authenticated | `none` | `make provider-lab-vcenter-install-readiness` |
| Firmware | Current or accepted after manual baseline review | Needs manual baseline review | `needs_review` | `make provider-lab-firmware-compliance` |

## Credential Status

| Provider | Configured | Tested | Next Action |
| --- | --- | --- | --- |
| iLO | `True` | `True` | No credential action required. |
| Cisco | `True` | `True` | No credential action required. |
| ESXi | `True` | `True` | No credential action required. |
| NetApp | `True` | `True` | No credential action required. |
| vCenter | `True` | `True` | No credential action required. |

## vCenter Readiness

- VCSA ISO: `found`
- vcsa-deploy: `ready`
- ESXi: `ready`
- NetApp datastore: `ready`
- Management IP available: `in_use_by_deployed_vcenter`
- vCenter values: `complete`
- vCenter credentials: `configured`
- vCenter config: `deployed`
- Preview state: `deployed`
- Deploy state: `deployed`
- Deploy enabled: `False`
- Next action: vCenter is deployed and post-install validation is ready.

## Workflow Actions

- Run Full Lab Validation: `make provider-lab-validation`
- Run Full Lab Build Plan: `make provider-lab-full-rebuild-summary`
- Run Full Lab Repair: `make provider-lab-golden-state`
- Generate Handoff Report: `make provider-lab-golden-state`

## Drift

- Firmware: `needs_review` - Needs manual baseline review

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
- `artifacts/codex-runs/vcenter-install-plan-report.md`
- `artifacts/codex-runs/vcenter-install-preview-report.md`
- `artifacts/codex-runs/vcenter-install-apply-report.md`
- `artifacts/codex-runs/vcenter-post-install-validation-report.md`
- `artifacts/codex-runs/firmware-compliance-report.md`

## Skill Improvement Review

- Skills used: lab-builder-skill-steward, lab-builder-real-runtime, lab-builder-hardware-run, lab-builder-toolchain, lab-builder-ux, lab-builder-product-craft, lab-builder-report-remediation
- Skills created or updated: none
- Skill gaps found: none requiring a new reusable skill in this pass
- Candidate skills deferred: none
- No additional skills were created because this work fits the existing Lab Builder skill set.
