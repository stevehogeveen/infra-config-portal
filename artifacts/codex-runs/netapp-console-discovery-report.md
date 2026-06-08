# NetApp Console Discovery

Checked at: 2026-06-07T14:36:28.183730+00:00
Action: `console-discovery`
Status: `blocked`
Provider mode: `local-lab-readwrite`

## Selection
- Configured port hint: `not set`
- Selected port: `none`
- Selected baud: `none`
- Prompt/state: `not detected`
- Candidate count: `0`
- Last console blocker: `No OS-visible NetApp USB serial adapters were found at /dev/serial/by-id/*, /dev/ttyUSB*, or /dev/ttyACM*. If this is a non-USB serial path such as /dev/ttyS4, set NETAPP_CONSOLE_PORT explicitly.`

## Management Topology
- Connected management ports: `cluster_mgmt`
- Note: Only one NetApp management port is connected at the moment.

## Attempts
- No serial open/read attempts were made.

## Blockers
- No OS-visible NetApp USB serial adapters were found at /dev/serial/by-id/*, /dev/ttyUSB*, or /dev/ttyACM*. If this is a non-USB serial path such as /dev/ttyS4, set NETAPP_CONSOLE_PORT explicitly.

## Warnings
- Only newline/enter wake bytes are allowed for this NetApp console probe.
- No NetApp credentials, commands, boot interrupts, or configuration actions are sent.
- Only one NetApp management port is connected at the moment.

## Not Attempted
- Ctrl+C, Ctrl+Z, break, or boot interruption
- username or password entry
- cluster setup commands
- SP, node, SVM, LIF, volume, export, or datastore creation
- ONTAP API write
- vCenter or ESXi datastore mount
- controller reboot, takeover/giveback, wipe, or upgrade
