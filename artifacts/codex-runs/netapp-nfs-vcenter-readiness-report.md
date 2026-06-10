# NetApp NFS / vCenter Readiness

Checked at: 2026-06-10T03:04:02.088647+00:00
Status: `blocked`
Provider mode: `mock`
Apply enabled: `False`

## Management Topology
- Single management port mode: `True`
- Connected management ports: `cluster_mgmt`
- Note: Only one NetApp management port is connected at the moment.

## Planned NFS
- SVM management IP: `192.168.1.223`
- NFS LIFs: `192.168.1.230, 192.168.1.231`
- Volume: `esxi_datastore_01`
- Export policy: `esxi_nfs_policy`
- Mount path: `/esxi_datastore_01`
- Datastore: `netapp_nfs_ds01`
- Client match: `192.168.1.0/24`

## Tool / Target State
- NetApp cluster management: `192.168.1.220`
- ESXi management: `192.168.1.203`
- vCenter configured: `False`
- govc available: `False`

## Preview Commands
- `govc datastore.create -type nfs -name netapp_nfs_ds01 -remote-host 192.168.1.230 -remote-path /esxi_datastore_01`
- `esxcli storage nfs add -H 192.168.1.230 -s /esxi_datastore_01 -v netapp_nfs_ds01`

## Blockers
- No live NetApp configured state exists yet; run Validate NetApp Setup.
- NetApp API credentials are missing; values must stay in .env.local.real-lab when ready.
- vCenter/govc target is not configured yet; vCenter datastore validation is blocked.

## Warnings
- Only one NetApp management path is connected; this is acceptable for initial console/API bring-up but not full HA validation.
- NFS/vCenter readiness is preview-only. No ONTAP, vCenter, ESXi, or storage apply action is run.

## Not Attempted
- Ctrl+C, Ctrl+Z, break, boot menu selection, or any boot interruption
- username or password entry
- cluster setup commands
- SP, node, SVM, LIF, volume, export, or datastore creation
- ONTAP API write
- vCenter or ESXi datastore mount
- controller reboot, takeover/giveback, wipe, or upgrade
