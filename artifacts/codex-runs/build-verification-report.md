# Build Verification / Product Certification

- Checked at: `2026-06-08T14:47:17.555667+00:00`
- Status: `blocked`
- Certification state: `stale_config`
- Provider mode: `mock`
- Mock results used: `False`

## Lab IP Profile

- Status: `blocked`
- iLO: `192.168.1.201`
- Server embedded NIC: `192.168.1.202`
- ESXi management: `192.168.1.203`
- Cisco management: `192.168.1.204`
- Ansible/control host: `192.168.1.205`
- NetApp Controller A SP: `192.168.1.206`
- NetApp Controller B SP: `192.168.1.207`
- NetApp cluster management: `192.168.1.208`
- NetApp node management: `192.168.1.209` / `192.168.1.210`
- NetApp SVM management: `192.168.1.211`
- NetApp iSCSI LIFs: `192.168.1.212,192.168.1.213,192.168.1.214,192.168.1.215`

## Failure Classification

- `stale_config` `lab-ip-profile`: Active lab IP profile contains stale or mismatched target values. Next action: Update provider environment inputs to match `Runtime environment` and remove stale 10.10.8.x values before certification.
- `operator_action_required` `protocol`: NetApp console is operator_action_required. Next action: Use the selected candidate as the next physical console check, then verify cable placement, adapter ownership, power state, and baud before rerunning discovery.
- `operator_action_required` `protocol`: ESXi ISO media inventory is operator_action_required. Next action: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.
- `blocked_by_prior_stage` `protocol`: NetApp NFS/vCenter is blocked_by_prior_stage. Next action: Use console/API read-only discovery to identify the NetApp state, then configure vCenter/govc before NFS datastore apply is implemented.
- `not_configured_yet` `protocol`: NetApp REST is not_configured_yet. Next action: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.
- `not_configured_yet` `protocol`: NetApp SSH is not_configured_yet. Next action: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.
- `warning` `protocol`: iLO Redfish is warning. Next action: Review iLO Redfish readiness.
- `warning` `protocol`: iLO XML fallback is warning. Next action: Review iLO XML fallback readiness.
- `warning` `protocol`: Cisco SSH/SCP is warning. Next action: Review Cisco SSH/SCP readiness.
- `warning` `protocol`: ESXi API is warning. Next action: Review ESXi API readiness.
- `warning` `protocol`: ESXi SSH is warning. Next action: Review ESXi SSH readiness.

## Credential Compatibility

- `passed` `ILO_TEST_PASSWORD`: configured; values redacted
- `passed` `CISCO_TEST_PASSWORD`: configured; values redacted
- `passed` `CISCO_ENABLE_PASSWORD or ANSIBLE_CISCO_ENABLE_PASSWORD`: configured; values redacted
- `passed` `ESXI_TEST_PASSWORD`: configured; values redacted

## MTU Consistency

- Classification: `passed`
- Invalid values: `0`
- Path mismatches: `0`

## Protocol Readiness

- `warning` `iLO Redfish`: Review iLO Redfish readiness.
- `warning` `iLO XML fallback`: Review iLO XML fallback readiness.
- `passed` `Cisco console`: Cisco console discovery and prompt detection passed.
- `warning` `Cisco SSH/SCP`: Review Cisco SSH/SCP readiness.
- `warning` `ESXi API`: Review ESXi API readiness.
- `warning` `ESXi SSH`: Review ESXi SSH readiness.
- `not_configured_yet` `NetApp REST`: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.
- `not_configured_yet` `NetApp SSH`: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.
- `operator_action_required` `NetApp console`: Use the selected candidate as the next physical console check, then verify cable placement, adapter ownership, power state, and baud before rerunning discovery.
- `blocked_by_prior_stage` `NetApp NFS/vCenter`: Use console/API read-only discovery to identify the NetApp state, then configure vCenter/govc before NFS datastore apply is implemented.
- `operator_action_required` `ESXi ISO media inventory`: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.

## Toolchain Readiness

- Status: `warning`
- Missing required: none
- Missing optional: `netmiko`, `ansible`, `cisco.ios collection`, `govc`, `ilorest`, `netapp-ontap`, `pyATS/Genie`
- `available` `pyserial`: Cisco local serial console first contact.
- `missing` `netmiko`: Cisco SSH command execution after console bootstrap enables management SSH.
- `missing` `ansible`: Cisco, NetApp, and future workflow orchestration after safe inventory is available.
- `missing` `cisco.ios collection`: Cisco IOS managed-state modules after SSH is enabled.
- `missing` `govc`: ESXi/vSphere post-install validation and deployment operations.
- `missing` `ilorest`: HPE iLO inventory, settings, firmware, and Redfish-backed operations.
- `missing` `netapp-ontap`: NetApp ONTAP REST client for managed-state setup and upgrade validation.
- `missing` `pyATS/Genie`: Cisco parsing, learning, and validation when installed.

## Post-Build Checklist

- `unknown` Cisco management IP responds and SSH/SCP are ready
- `unknown` iLO inventory, health, power, and Redfish are reachable
- `manual-review` RAID layout matches saved intent after reset/validation
- `unknown` ESXi media is inserted or host installer state is detected
- `skipped` NetApp REST/SSH paths are reachable when configured
- `unknown` NetApp console discovery/read-state evidence exists
- `unknown` NetApp NFS/vCenter readiness has been reviewed

## Safety

- Credential values, tokens, and secrets are redacted.
