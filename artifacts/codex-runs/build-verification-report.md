# Build Verification / Product Certification

- Checked at: `2026-06-07T01:16:49.658689+00:00`
- Status: `blocked`
- Certification state: `blocked_by_prior_stage`
- Provider mode: `local-lab-readwrite`
- Mock results used: `False`

## Lab IP Profile

- Status: `ready`
- iLO: `192.168.1.201`
- Server embedded NIC: `192.168.1.202`
- ESXi management: `192.168.1.203`
- Cisco management: `192.168.1.204`
- Ansible/control host: `192.168.1.205`

## Failure Classification

- `blocked_by_prior_stage` `protocol`: Cisco SSH/SCP is blocked_by_prior_stage. Next action: Complete or confirm Cisco console bootstrap, then set CISCO_MGMT_CONFIGURED=true before treating SSH/SCP as a port failure.
- `blocked_by_prior_stage` `protocol`: ESXi API is blocked_by_prior_stage. Next action: Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification.
- `blocked_by_prior_stage` `protocol`: ESXi SSH is blocked_by_prior_stage. Next action: Install/configure ESXi management and enable/confirm SSH before ESXi SSH certification.
- `not_configured_yet` `protocol`: NetApp REST is not_configured_yet. Next action: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.
- `not_configured_yet` `protocol`: NetApp SSH is not_configured_yet. Next action: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.

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

- `passed` `iLO Redfish`: iLO Redfish readiness passed.
- `passed` `iLO XML fallback`: iLO XML fallback readiness passed.
- `passed` `Cisco console`: Cisco console discovery and prompt detection passed.
- `blocked_by_prior_stage` `Cisco SSH/SCP`: Complete or confirm Cisco console bootstrap, then set CISCO_MGMT_CONFIGURED=true before treating SSH/SCP as a port failure.
- `blocked_by_prior_stage` `ESXi API`: Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification.
- `blocked_by_prior_stage` `ESXi SSH`: Install/configure ESXi management and enable/confirm SSH before ESXi SSH certification.
- `not_configured_yet` `NetApp REST`: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.
- `not_configured_yet` `NetApp SSH`: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.
- `passed` `ESXi ISO media inventory`: ESXi ISO media inventory is ready.

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
- `ready` iLO inventory, health, power, and Redfish are reachable
- `manual-review` RAID layout matches saved intent after reset/validation
- `unknown` ESXi media is inserted or host installer state is detected
- `skipped` NetApp REST/SSH paths are reachable when configured

## Safety

- Credential values, tokens, and secrets are redacted.
