# Control Center Control Audit

Generated: 2026-06-08

Scope: `/home/administrator/infra-config-portal`

## Summary

The app now has a calmer Guided View under the Lab Builder / Provider Status page and a guided Run Center chooser. That simplified path works for next-action flow, but it hides many of the controls an operator needs for full lab build, upgrade, recovery, and verification work.

The current UI has three separate control surfaces:

- Run Center: a guided chooser, VM request queue, selected work review, and NetApp preview.
- Provider Status / Lab Builder: simplified build stages plus provider-specific details.
- Lab Profiles: saved address profiles with editable core IP fields.

The missing piece is a single Control Center that shows every device, desired state, diff, action, report, and blocker together without requiring operators to expand advanced diagnostics or know make targets.

## Controls Currently Missing

- A single action catalog showing all known Cisco, iLO, RAID, ESXi, NetApp, firmware, upgrade, and verification actions.
- A unified current state / desired state / plan diff view for each build stage.
- A visible commander mode area for reclaiming console access, forcing fresh discovery, bypassing stale cached artifacts, and running verification.
- A direct Upgrade Center showing iLO firmware, BIOS, Smart Array, Cisco IOS XE, Cisco ROMMON/bootloader, ESXi media/version, ONTAP, and NetApp disk/shelf/SP firmware together.
- A single report/action history panel showing the latest report path per action.
- A visible matrix of write, destructive, and upgrade actions with their required flags and confirmations.
- A lab profile panel that includes subnet, device IPs, NetApp IPs, VLANs, MTU, DNS, gateway, NTP, and configured flags in one place.
- A copyable non-secret environment update command for profile values.
- A stale/invalid profile value report inside the control surface.
- A route-level power-user entry point separate from the simplified Guided View.

## Controls Buried Under Advanced Details

- iLO setup intent editing is under Provider Status -> Advanced diagnostics -> HPE iLO / Redfish -> iLO settings.
- HPE RAID discovery, RAID intent, apply plan, pending state, reset plan, and post-reset validation are under Advanced diagnostics.
- ESXi install readiness, virtual media capability, one-time boot support, BIOS discovery, and ISO readiness are under Advanced diagnostics.
- iLO firmware upgrade readiness and protected firmware actions are under Advanced diagnostics.
- Cisco current discovery, saved planning values, setup wizard plan, bootstrap plan, prompt readiness, SSH/SCP readiness, and disabled actions are under Advanced diagnostics.
- NetApp planned targets, current/discovered targets, readiness buckets, storage/iSCSI preview, upgrade preview, and artifact placeholders are under Advanced diagnostics or the Run Center NetApp preview tab.
- Full rebuild summary, build verification, raw provider evidence, and protected actions are behind the Provider Status advanced diagnostics block.
- Provider safe actions and disabled actions are visible only after opening the provider detail card area.

## Actions Only Available As Make Targets

These root or app make targets are not visible as first-class controls in one UI:

- `make provider-lab-ilo-reachability`
- `make provider-lab-ilo-authentication`
- `make provider-lab-ilo-inventory`
- `make provider-lab-ilo-readiness`
- `make provider-lab-firmware-inventory`
- `make provider-lab-firmware-cisco-inventory`
- `make provider-lab-firmware-compliance`
- `make provider-lab-firmware-compliance-scope-cisco`
- `make provider-lab-firmware-compliance-scope-hpe`
- `make provider-lab-firmware-compliance-scope-full`
- `make provider-lab-firmware-waiver-check`
- `make provider-lab-hpe-storage-discovery`
- `make provider-lab-hpe-raid-discovery`
- `make provider-lab-hpe-raid-plan`
- `make provider-lab-hpe-raid-apply`
- `make provider-lab-hpe-raid-validate-after-reset`
- `make provider-lab-esxi-install-readiness`
- `make provider-lab-esxi-media-url`
- `make provider-lab-esxi-insert-virtual-media`
- `make provider-lab-esxi-eject-virtual-media`
- `make provider-lab-esxi-one-time-boot`
- `make provider-lab-esxi-reset-installer-boot`
- `make provider-lab-esxi-detect-installer`
- `make provider-lab-cisco-console-ethernet-readiness`
- `make provider-lab-cisco-console-recovery`
- `make provider-lab-cisco-privilege-check`
- `make provider-lab-cisco-vlan10-bootstrap-fix`
- `make provider-lab-cisco-vlan10-bootstrap-apply`
- `make provider-lab-full-rebuild-summary`
- `make provider-lab-full-rebuild`
- `make provider-lab-build-verification`
- `make provider-lab-toolchain-check`
- `make provider-lab-serial-console-discovery`
- `make provider-lab-netapp-console-autodiscovery`
- `make provider-lab-netapp-console-discovery`
- `make provider-lab-netapp-console-read-state`
- `make provider-lab-netapp-nfs-vcenter-readiness`
- `make netapp-real-readiness`

## Config Values Only Editable Through Environment

The Lab Profiles page saves address plans, but many operational values still require `.env.local.real-lab` or environment variables:

- `CISCO_MGMT_CONFIGURED`
- `ESXI_CONFIGURED`
- `NETAPP_CONFIGURED`
- `CISCO_TARGET_IP`
- `ANSIBLE_CISCO_HOST`
- `ANSIBLE_CONTROL_HOST`
- `CISCO_MANAGEMENT_GATEWAY`
- `CISCO_MANAGEMENT_VLAN`
- `CISCO_MANAGEMENT_INTERFACE`
- `CISCO_MANAGEMENT_STRATEGY`
- `CISCO_DNS_SERVERS`
- `CISCO_CONSOLE_PORT`
- `CISCO_CONSOLE_BAUD`
- `ILO_TEST_HOST`
- `ILO_TEST_VERIFY_TLS`
- `SERVER_EMBEDDED_NIC_IP`
- `ESXI_TEST_HOST`
- `NETAPP_CONTROLLER_A_SP`
- `NETAPP_CONTROLLER_B_SP`
- `NETAPP_CLUSTER_MGMT_IP`
- `NETAPP_NODE_A_MGMT_IP`
- `NETAPP_NODE_B_MGMT_IP`
- `NETAPP_SVM_MGMT_IP`
- `NETAPP_ISCSI_LIFS`
- `NETAPP_CONSOLE_PORT`
- `NETAPP_CONSOLE_BAUD`
- `NETAPP_CONNECTED_MANAGEMENT_PORTS`
- `NETAPP_STORAGE_PROTOCOL`
- `NETAPP_NFS_LIFS`
- `NETAPP_NFS_VOLUME`
- `NETAPP_NFS_EXPORT_POLICY`
- `NETAPP_NFS_MOUNT_PATH`
- `NETAPP_NFS_DATASTORE_NAME`
- `NETAPP_NFS_CLIENT_MATCH`
- `VCENTER_CONFIGURED`
- `LAB_ENVIRONMENT`
- `LAB_ACKNOWLEDGE_REAL_HARDWARE`
- `LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION`
- `LAB_ACKNOWLEDGE_DATA_LOSS_RISK`
- `LAB_ACKNOWLEDGE_LAB_ONLY`
- `LAB_ALLOW_POWER_ACTIONS`
- `LAB_ALLOW_FIRMWARE_UPDATES`
- `LAB_ALLOW_FACTORY_RESET`
- `ILO_SETUP_APPLY_ENABLED`
- `CISCO_CONSOLE_APPLY_ENABLED`
- `LAB_APPLY_ACK`
- `LAB_TARGET_ACK`
- `LAB_DESTRUCTIVE_ACK`

The UI must show whether these flags are configured without exposing secrets. Secret values remain environment-only and should be represented only as present/missing.

## Upgrade Controls Missing

- There is no single Upgrade Center covering Cisco, HPE/iLO, ESXi media, and NetApp together.
- Firmware compliance is visible as a guided stage, but package inventory, compliance check, waiver check, upgrade planning, and upgrade apply placeholders are not grouped as controls.
- iLO firmware upgrade readiness exists but is buried in iLO advanced details.
- NetApp upgrade readiness exists but is buried in NetApp preview/details.
- Cisco firmware inventory is available through make targets and cached evidence, but not exposed as a visible Cisco control row.
- Firmware apply remains intentionally disabled; the UI should still show the placeholder, required flags, reports, and why it is blocked.

## Device Actions Missing

Cisco:

- Discover console
- Reclaim console
- Reclaim serial port
- Privilege check
- Firmware inventory
- Apply bootstrap
- Validate SSH/SCP
- Save config
- Reload if needed

HPE / iLO:

- Reachability
- Auth
- Inventory
- Virtual media insert
- One-time boot
- Reset server
- Firmware inventory

RAID:

- Discovery
- Plan
- Apply
- Pending check
- Reset/commit
- Validate

ESXi:

- Readiness
- ISO/media check
- Kickstart generation
- Rebuild/install
- Management validation
- SSH/API check

NetApp:

- Console autodiscovery
- Console watch/read-state
- REST/SSH readiness
- Setup preview
- NFS/vCenter readiness

Firmware / Upgrade:

- Firmware inventory
- Compliance check
- Waiver check
- Package inventory
- Upgrade plan
- Upgrade apply placeholder

Build Verification:

- Run full verification
- Run scoped verification
- Export certification report

## Where The User Lacks Control

- The default experience answers "what next?" but not "what exactly can I do now?"
- Operators cannot scan all available actions by device, safety class, availability, blocker, and report.
- Operators cannot see write/destructive/upgrade gates next to the action they gate.
- Operators must know make target names to run many real-lab readiness and verification steps.
- Operators must open advanced diagnostics to see the controls needed for recovery and rebuild.
- Operators cannot compare active lab profile values with the known lab profile in the same place as provider actions.
- Operators cannot see current vs desired vs planned diff for every stage without moving between Provider Status, Run Center, Lab Profiles, and reports.
- Operators cannot clearly distinguish "safe to plan", "copy this command", "blocked until flag", and "direct execution not implemented yet" at the action level.
