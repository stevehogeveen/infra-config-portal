# Build Verification / Product Certification

- Checked at: `2026-06-10T15:39:22.887875+00:00`
- Status: `blocked`
- Certification state: `test_fixture`
- Source: `test_fixture`
- Freshness: `unknown`
- Current: `False`
- Operator visible: `False`
- Recheck command: `make provider-lab-build-verification-live`

## Lab IP Profile

- Status: `blocked`
- Profile: `Runtime environment`
- Topology: `high_address_lab`
- Not in scope: `vcenter, vcenter-netapp`
- iLO: `192.168.1.201`
- Server embedded NIC: `192.168.1.202`
- ESXi management: `192.168.1.203`
- Cisco management: `192.168.1.204`
- Ansible/control host: `192.168.1.205`
- NetApp Controller A SP: `192.168.1.210`
- NetApp Controller B SP: `192.168.1.211`
- NetApp cluster management: `192.168.1.220`
- NetApp node management: `192.168.1.221` / `192.168.1.222`
- NetApp SVM management: `192.168.1.223`
- NetApp NFS LIFs: `192.168.1.230,192.168.1.231`
- NetApp iSCSI LIFs: `192.168.1.240,192.168.1.241,192.168.1.242,192.168.1.243`

## Failure Classification

- `operator_action_required` `runtime-mode`: Build Verification is running in test/mock mode. Next action: Run `make provider-lab-build-verification-live` with PROVIDER_MODE=local-lab-readwrite.
- `hard_fail` `protocol`: NetApp REST is hard_fail. Next action: NetApp cluster management REST is not reachable.
- `hard_fail` `protocol`: NetApp SSH is hard_fail. Next action: NetApp cluster management REST is not reachable.
- `stale_config` `lab-ip-profile`: Active lab IP profile contains stale or mismatched target values. Next action: Update provider environment inputs to match `Runtime environment` or remove out-of-scope overrides before certification.
- `operator_action_required` `protocol`: ESXi ISO media inventory is operator_action_required. Next action: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.
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

## NetApp Live State

- Configured state: `blocked`
- Configured: `False`
- Source: `live_verification`
- Manual env flag required: `False`
- Discovered console port: `/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00`
- Console baud: `none`
- Console confidence: `high`

## Protocol Readiness

- `warning` `iLO Redfish`: Review iLO Redfish readiness.
- `warning` `iLO XML fallback`: Review iLO XML fallback readiness.
- `passed` `Cisco console`: Cisco console discovery and prompt detection passed.
- `warning` `Cisco SSH/SCP`: Review Cisco SSH/SCP readiness.
- `warning` `ESXi API`: Review ESXi API readiness.
- `warning` `ESXi SSH`: Review ESXi SSH readiness.
- `operator_action_required` `ESXi ISO media inventory`: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.
- `hard_fail` `NetApp REST`: NetApp cluster management REST is not reachable.
- `hard_fail` `NetApp SSH`: NetApp cluster management REST is not reachable.
- `passed` `NetApp console`: NetApp console was detected automatically; no .env port update is required.
- `not_in_scope` `NetApp NFS/vCenter`: NetApp or vCenter is disabled by the active lab profile.

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
- `blocked` NetApp REST/SSH paths are reachable when configured
- `ready` NetApp console discovery/read-state evidence exists
- `not_in_scope` NetApp NFS/vCenter readiness has been reviewed

## Safety

- Credential values, tokens, and secrets are redacted.
