# Grand Operation Stage 8 - vCenter And NetApp Datastore Report

Checked at: 2026-06-10T23:11:11Z
Scope: local real lab, vCenter/VCSA, ESXi `192.168.1.203`, NetApp NFS datastore `netapp_nfs_ds01`

## Result

- Status: blocked by prior NetApp setup stage and missing vCenter configuration.
- VCSA/vCenter media: `artifacts/Media/VMware-VCSA-all-8.0.3-24853646.iso` is present.
- NetApp datastore source: not available because NetApp ONTAP/NFS is not configured yet.
- vCenter host/API target: not configured in local ignored env.
- vCenter credentials: not configured in local ignored env.
- `govc`: installed in repo-local `.local/bin`; the vCenter-NetApp readiness service was fixed to discover repo-local tools.
- Datastore apply: not attempted. The current app lane is readiness/preview only and reports that no ONTAP, vCenter, ESXi, NFS, datastore, or storage write action was run.

## Planned Datastore

- Datastore name: `netapp_nfs_ds01`
- Remote host: `192.168.1.230`
- Remote path: `/esxi_datastore_01`
- Export policy: `esxi_nfs_policy`
- Client match: `192.168.1.0/24`

## Blockers

- NetApp ONTAP/NFS is not configured yet; datastore readiness is blocked by prior NetApp setup.
- NetApp API credential fields are missing locally.
- vCenter host/credentials are not configured locally.
- The app does not yet implement a guarded VCSA deployment lane from the VCSA ISO.

## App/Product Fix From This Stage

- `app/backend/app/services/vcenter_netapp_readiness.py`: `govc` discovery now checks PATH, the active Python environment, and repo-local `.local/bin`.
- `app/backend/tests/test_lab_validation.py`: added coverage for repo-local `govc` discovery in vCenter-NetApp readiness.

## Validation

- `make provider-lab-vcenter-netapp-readiness`: `blocked_by_prior_stage`.
- `make provider-lab-vcenter-netapp-datastore-plan`: `blocked_by_prior_stage`.
- Focused vCenter-NetApp validation tests passed.
- Ruff checks passed for changed vCenter-NetApp files.

## Evidence

- `artifacts/codex-runs/vcenter-netapp-readiness-report.md`
- `artifacts/codex-runs/vcenter-netapp-datastore-plan-report.md`
- `artifacts/codex-runs/vcenter-netapp-readiness-redacted.json`
- `artifacts/codex-runs/grand-operation-media-inventory-report.md`

## Exact Next Action

Complete NetApp setup and configure local vCenter/GOVC access values in `.env.local.real-lab`; then rerun `make provider-lab-vcenter-netapp-readiness`.
