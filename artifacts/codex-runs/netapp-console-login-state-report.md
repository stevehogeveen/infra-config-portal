# NetApp Console Login / Read-Only State

Checked at: 2026-06-09T22:31:06.045071+00:00
Status: `ready`
Provider mode: `local-lab-readwrite`

## Current Console
- Selected port: `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00`
- Selected baud: `115200`
- Prompt state: `cluster_setup_prompt`
- Identified state: `cluster_setup_wizard`

## Credential State
- NETAPP_CONSOLE_USERNAME: `missing`
- NETAPP_CONSOLE_PASSWORD: `missing`
- NETAPP_API_USERNAME: `missing`
- NETAPP_API_PASSWORD: `missing`
- Usable credential pair: `False`

## Actions
- Guarded login attempted: `False`
- Read-only commands attempted: `False`

## Fixed Read-Only Command Set
- `ontap_version`: `version`
- `node_identity`: `system node show -fields node,model,health,uptime`
- `cluster_status`: `cluster show`
- `network_interface_summary`: `network interface show -fields vserver,lif,address,role,home-node,home-port,status-admin,status-oper`
- `storage_aggregate_summary`: `storage aggregate show -fields aggregate,node,state,size,available,usedsize`

## Command Results
- No console login or ONTAP shell read-only command was attempted.

## Blockers
- None

## Warnings
- Guarded console login only uses NetApp-specific console credentials or NetApp API credentials as a fallback.
- Read-only commands are fixed and only run after an ONTAP shell prompt is detected.
- No setup, cluster creation, network configuration, storage provisioning, reboot, wipe, or upgrade commands are sent.
- Current console state is `cluster_setup_wizard`; this is identified state, but no setup command is allowed in this stage.

## Not Attempted
- cluster setup commands
- SP, node, SVM, LIF, volume, export, datastore, user, or iSCSI configuration
- ONTAP API write
- vCenter or ESXi datastore mount
- controller reboot, takeover/giveback, wipe, or upgrade

## Next Action

Build and review the setup plan; do not enter setup commands until a guarded apply workflow and explicit apply confirmations exist.
