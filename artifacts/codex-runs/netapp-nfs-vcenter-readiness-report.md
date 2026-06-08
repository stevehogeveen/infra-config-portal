# NetApp NFS / vCenter Readiness

Checked at: 2026-06-07T17:44:30.600531+00:00
Status: `blocked`
Provider mode: `local-lab-readwrite`
Apply enabled: `False`

## Management Topology
- Single management port mode: `True`
- Connected management ports: `cluster_mgmt`
- Note: Only one NetApp management port is connected at the moment.

## Planned NFS
- SVM management IP: `192.168.1.211`
- NFS LIFs: `192.168.1.212, 192.168.1.213`
- Volume: `esxi_datastore_01`
- Export policy: `esxi_nfs_policy`
- Mount path: `/esxi_datastore_01`
- Datastore: `netapp_nfs_ds01`
- Client match: `192.168.1.0/24`

## Tool / Target State
- NetApp cluster management: `192.168.1.208`
- ESXi management: `192.168.1.203`
- vCenter configured: `False`
- govc available: `False`

## Preview Commands
- `govc datastore.create -type nfs -name netapp_nfs_ds01 -remote-host 192.168.1.212 -remote-path /esxi_datastore_01`
- `esxcli storage nfs add -H 192.168.1.212 -s /esxi_datastore_01 -v netapp_nfs_ds01`

## Blockers
- NETAPP_CONFIGURED=false; ONTAP REST/NFS setup is not ready for live validation.
- NetApp API credentials are missing; values must stay in .env.local.real-lab when ready.
- vCenter/govc target is not configured yet; vCenter datastore validation is blocked.

## Warnings
- Only one NetApp management path is connected; this is acceptable for initial console/API bring-up but not full HA validation.
- NFS/vCenter readiness is preview-only. No ONTAP, vCenter, ESXi, or storage apply action is run.

## Not Attempted
- Ctrl+Z, break, boot menu selection, or boot interruption beyond the generic Ctrl+C wake byte
- username or password entry
- cluster setup commands
- SP, node, SVM, LIF, volume, export, or datastore creation
- ONTAP API write
- vCenter or ESXi datastore mount
- controller reboot, takeover/giveback, wipe, or upgrade
