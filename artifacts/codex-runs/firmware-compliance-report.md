# Firmware Compliance Report

Checked: 2026-06-06T18:00:05.340391+00:00
Provider mode: local-lab-readwrite
Scope: cisco
Status: blocked
Message: Firmware compliance gate is blocking major configuration workflows.

## Components

### iLO - HPE iLO firmware

- Status: passed
- Current version: iLO 5 v3.19
- Required/minimum: 3.19
- Approved: 3.19
- Reason: Current version matches the firmware baseline.
- Next action: Inventory iLO through Redfish, then stage an approved HPE iLO firmware package if the version is below baseline.

### HPE Server - HPE BIOS version

- Status: warning
- Current version: U32 v3.30 (07/31/2024)
- Required/minimum: manual approval
- Approved: none listed
- Reason: Baseline requires manual approval because no minimum or approved version is set.
- Next action: Confirm BIOS version from iLO Redfish system inventory or the server console before configuration.

### HPE Smart Array - HPE Smart Array controller firmware

- Status: warning
- Current version: 1.98
- Required/minimum: manual approval
- Approved: none listed
- Reason: Baseline requires manual approval because no minimum or approved version is set.
- Next action: Run HPE storage discovery and compare controller firmware with the approved SPP for this host.

### Cisco - Cisco IOS XE version

- Status: blocked
- Current version: unknown
- Required/minimum: 17.9
- Approved: none listed
- Reason: Current firmware or OS version is unknown.
- Next action: Run Cisco firmware inventory from console.

### Cisco - Cisco bootloader/ROMMON

- Status: warning
- Current version: unknown
- Required/minimum: manual approval
- Approved: none listed
- Reason: Current firmware or OS version is unknown.
- Next action: Collect Cisco boot variable and ROMMON details from read-only show commands.

### NetApp - ONTAP version

- Status: not_configured_yet
- Current version: unknown
- Required/minimum: 9.14
- Approved: none listed
- Reason: NETAPP_CONFIGURED=false; NetApp firmware gate is waiting for setup values.
- Next action: Set NETAPP_CURRENT_ONTAP_VERSION from verified ONTAP read-only discovery before setup.

### NetApp - NetApp disk firmware

- Status: not_configured_yet
- Current version: unknown
- Required/minimum: manual approval
- Approved: none listed
- Reason: NETAPP_CONFIGURED=false; NetApp firmware gate is waiting for setup values.
- Next action: Collect disk firmware inventory through an approved read-only NetApp workflow.

### NetApp - NetApp shelf firmware

- Status: not_configured_yet
- Current version: unknown
- Required/minimum: manual approval
- Approved: none listed
- Reason: NETAPP_CONFIGURED=false; NetApp firmware gate is waiting for setup values.
- Next action: Collect shelf firmware inventory through an approved read-only NetApp workflow.

### NetApp - NetApp SP/BMC firmware

- Status: not_configured_yet
- Current version: unknown
- Required/minimum: manual approval
- Approved: none listed
- Reason: NETAPP_CONFIGURED=false; NetApp firmware gate is waiting for setup values.
- Next action: Collect SP/BMC firmware inventory through an approved read-only NetApp workflow.
