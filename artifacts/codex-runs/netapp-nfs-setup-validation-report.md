# NetApp NFS Setup Validation Report

- Checked at: `2026-06-11T02:27:35.202971+00:00`
- Status: `blocked`
- Apply enabled: `False`
- Configured state: `None`
- API access present: `None`
- ONTAP writes attempted: `False`
- ESXi/vCenter writes attempted: `False`

## NFS Plan
- SVM: `None`
- SVM management IP: `192.168.1.223`
- NFS LIFs: `192.168.1.230, 192.168.1.231`
- Volume: `esxi_datastore_01`
- Mount path: `/esxi_datastore_01`
- Export policy: `esxi_nfs_policy`
- Client match: `192.168.1.0/24`
- Datastore: `netapp_nfs_ds01`

## Required Flags

## Blockers
- No live NetApp configured state exists yet; run Validate NetApp Setup.
- NetApp API credentials are missing; values must stay in .env.local.real-lab when ready.
- vCenter/govc target is not configured yet; vCenter datastore validation is blocked.

## Safety
- NFS only. iSCSI is not used by this workflow.
- Secrets are represented only as configured/missing/redacted state.
