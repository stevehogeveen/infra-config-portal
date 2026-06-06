# Build Verification / Product Certification

- Checked at: `2026-06-06T18:52:38.681419+00:00`
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

## Failure Classification

- `stale_config` `lab-ip-profile`: Active lab IP profile contains stale or mismatched target values. Next action: Update active lab inputs to 192.168.1.201-.205 and remove stale 10.10.8.x values before certification.
- `operator_action_required` `protocol`: Cisco console is operator_action_required. Next action: Connect the Cisco console adapter and rerun prompt detection at 9600.
- `operator_action_required` `protocol`: ESXi ISO media inventory is operator_action_required. Next action: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.
- `blocked_by_prior_stage` `protocol`: Cisco SSH/SCP is blocked_by_prior_stage. Next action: Complete or confirm Cisco console bootstrap, then set CISCO_MGMT_CONFIGURED=true before treating SSH/SCP as a port failure.
- `blocked_by_prior_stage` `protocol`: ESXi API is blocked_by_prior_stage. Next action: Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification.
- `blocked_by_prior_stage` `protocol`: ESXi SSH is blocked_by_prior_stage. Next action: Install/configure ESXi management and enable/confirm SSH before ESXi SSH certification.
- `not_configured_yet` `protocol`: NetApp REST is not_configured_yet. Next action: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.
- `not_configured_yet` `protocol`: NetApp SSH is not_configured_yet. Next action: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.
- `warning` `protocol`: iLO Redfish is warning. Next action: Review iLO Redfish readiness.
- `warning` `protocol`: iLO XML fallback is warning. Next action: Review iLO XML fallback readiness.

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
- `operator_action_required` `Cisco console`: Connect the Cisco console adapter and rerun prompt detection at 9600.
- `blocked_by_prior_stage` `Cisco SSH/SCP`: Complete or confirm Cisco console bootstrap, then set CISCO_MGMT_CONFIGURED=true before treating SSH/SCP as a port failure.
- `blocked_by_prior_stage` `ESXi API`: Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification.
- `blocked_by_prior_stage` `ESXi SSH`: Install/configure ESXi management and enable/confirm SSH before ESXi SSH certification.
- `not_configured_yet` `NetApp REST`: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.
- `not_configured_yet` `NetApp SSH`: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.
- `operator_action_required` `ESXi ISO media inventory`: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.

## Post-Build Checklist

- `unknown` Cisco management IP responds and SSH/SCP are ready
- `unknown` iLO inventory, health, power, and Redfish are reachable
- `manual-review` RAID layout matches saved intent after reset/validation
- `unknown` ESXi media is inserted or host installer state is detected
- `skipped` NetApp REST/SSH paths are reachable when configured

## Safety

- Credential values, tokens, and secrets are redacted.
