# vCenter Post-Install Validation Report

- Checked at: `2026-06-14T18:47:26.196943+00:00`
- Status: `ready`
- vCenter host: `192.168.1.206`
- govc configured: `True`
- ESXi target: `192.168.1.203`
- Datastore: `netapp_nfs_ds01`

## Checks
- ping: `ready`
- tcp_443: `ready`
- api_readiness: `ready` vCenter HTTPS endpoint responded.
- govc_authentication: `ready`
- esxi_visible: `blocked`
- netapp_datastore_visible: `blocked`

## Blockers
- None

## Warnings
- ESXi is not visible in vCenter inventory yet; host add/attach is not implemented in this apply workflow.
- NetApp datastore is not visible through vCenter yet; validate again after ESXi inventory is attached.

## Safety
- Validation uses ping, TCP/443, HTTPS/API, and read-only govc inventory checks.
