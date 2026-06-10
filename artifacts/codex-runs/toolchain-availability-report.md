# Toolchain Availability Report

- Checked at: `2026-06-10T21:52:14.343105+00:00`
- Status: `warning`
- Provider mode: `mock`
- Next safe action: Use available tools only through staged readiness, preview, approval, and audit gates.

## Local Tool Checks

- `available` `pyserial` required=`True` check=`import serial` version=`3.5`
  - Purpose: Cisco local serial console first contact.
- `missing` `netmiko` required=`False` check=`import netmiko`
  - Purpose: Cisco SSH command execution after console bootstrap enables management SSH.
- `missing` `ansible` required=`False` check=`ansible --version`
  - Purpose: Cisco, NetApp, and future workflow orchestration after safe inventory is available.
- `missing` `cisco.ios collection` required=`False` check=`ansible-galaxy collection list cisco.ios`
  - Purpose: Cisco IOS managed-state modules after SSH is enabled.
- `missing` `govc` required=`False` check=`govc --version`
  - Purpose: ESXi/vSphere post-install validation and deployment operations.
- `missing` `ilorest` required=`False` check=`ilorest --version`
  - Purpose: HPE iLO inventory, settings, firmware, and Redfish-backed operations.
- `missing` `netapp-ontap` required=`False` check=`import netapp_ontap`
  - Purpose: NetApp ONTAP REST client for managed-state setup and upgrade validation.
- `missing` `pyATS/Genie` required=`False` check=`import pyats and import genie`
  - Purpose: Cisco parsing, learning, and validation when installed.

## Managed-State Plan

### Cisco
- Use console bootstrap first via local_serial or tcp_console/ser2net.
- Enable management SSH only through an explicit guarded bootstrap workflow.
- Use Ansible cisco.ios, Netmiko, and pyATS/Genie parsing for read-only validation and later managed state after SSH is enabled.

### HPE / iLO
- Use Redfish direct as the default API path.
- Use HPE iLOrest when vendor tooling provides better coverage for iLO settings, firmware, or inventory.
- Keep all iLO write lanes behind explicit local-lab-readwrite acknowledgements.

### ESXi / vSphere
- Install ESXi through iLO virtual media and Kickstart readiness gates.
- Use govc after the management network is configured.
- Reserve deployment operations for approved post-install workflows.

### NetApp
- Use local serial console discovery/read-state first for physical/controller state evidence.
- Use netapp-ontap Python client or ONTAP REST as the primary managed-state path.
- Use ONTAP REST direct where simple GET/compare logic is enough after cluster management is configured.
- Keep NFS/vCenter datastore apply and all ONTAP writes behind explicit NetApp stage gates.

## Firmware Strategy

- Baseline source: `config/firmware-baselines/real-lab.yml`
- Rule: Compare local baseline manifest to vendor package inventory before any firmware apply lane is enabled.
- Inventory source: Cisco show version from console or SSH after readiness gates
- Inventory source: HPE iLO Redfish/iLOrest inventory
- Inventory source: ESXi/vSphere version from govc after install
- Inventory source: NetApp ONTAP REST/system version after read-only discovery is approved

## Safety

- This check does not contact real infrastructure or run destructive workflows.
