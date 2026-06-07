# Toolchain Integration Design

Generated: 2026-06-06

## Objective

Stop hand-rolling every vendor operation by introducing a toolchain layer that can select the best available local tool for each provider while preserving the portal safety model:

- Mock-first by default.
- Discovery and readiness before apply.
- Console or out-of-band first contact before network automation.
- No destructive hardware workflows in this run.
- Secrets and raw credentials remain redacted.

## Toolchain Model

The portal should treat vendor tools as provider capabilities behind adapters, not as UI-owned commands. A tool capability describes:

- Provider: Cisco, HPE/iLO, ESXi/vSphere, NetApp, firmware.
- Contact path: local serial, TCP console, Redfish, REST, SSH, govc, local manifest.
- Operation class: readiness, inventory, plan, validation, apply.
- Safety class: mock, local-readonly, local-lab-readwrite.
- Required gates: configuration present, acknowledgements, approval, audit, rollback notes.

The first implemented slice is a local availability check that reports installed packages and CLIs without contacting infrastructure.

## Cisco

Use console bootstrap first, then managed-state tools after management SSH is intentionally enabled.

Primary first-contact paths:

- `local_serial`: existing pyserial-backed USB serial console workflow.
- `tcp_console` / ser2net: TCP socket mapped to a console-server or ser2net endpoint.

Post-bootstrap managed-state paths:

- Ansible `cisco.ios` collection for repeatable intent and validation.
- Netmiko for targeted command execution.
- pyATS/Genie for parsing, learning, and validation when installed.

Safety boundary:

- Console discovery/prompt readiness remains wake-and-classify.
- SSH tooling starts only after `CISCO_MGMT_CONFIGURED=true`.
- Configure, write memory, reload, copy, erase, SSH enablement, and SCP changes remain behind separate guarded workflows.

## HPE / iLO

Use Redfish direct as the default API path because it is already aligned with the app's read-only and guarded-write adapters.

Tool choices:

- Redfish direct for inventory, health, boot, virtual media, and settings where coverage is good.
- HPE iLOrest for operations where vendor tooling is more complete or less error-prone.

Safety boundary:

- Availability checks do not contact iLO.
- iLO write lanes remain explicit local-lab-readwrite operations with acknowledgements.

## ESXi / vSphere

Use iLO/Kickstart for install, then govc after the management network exists.

Sequence:

- Prepare ISO/Kickstart readiness.
- Use iLO virtual media and boot control for install handoff.
- Validate post-install management reachability.
- Use `govc` for version, datastore/network validation, and later deploy operations.

Safety boundary:

- This run adds only local tool awareness and plan text.
- No host install, reset, VM deploy, datastore, or network operation is triggered.

## NetApp

Use ONTAP REST or the `netapp-ontap` Python client as the primary path.

Primary paths:

- `netapp-ontap` Python client for typed ONTAP REST integration.
- ONTAP REST direct where simple GET/compare logic is enough.

Safety boundary:

- NetApp remains preview-only until a future explicit read-only discovery lane is added.

## Firmware

Firmware should be a comparison workflow, not an immediate apply workflow.

Inputs:

- Local baseline manifest: `config/firmware-baselines/real-lab.yml`.
- Vendor inventory sources:
  - Cisco `show version` from console/SSH after readiness gates.
  - HPE iLO Redfish or iLOrest.
  - ESXi/vSphere version from govc after install.
  - NetApp ONTAP REST after read-only discovery is approved.

Rule:

- Compare baseline to inventory first.
- Require explicit approval and provider-specific gates before any package upload, flash, reboot, or activation lane.

## Implemented In This Run

- Added backend local tool availability checks for pyserial, Netmiko, Ansible, Cisco `cisco.ios`, govc, ilorest, netapp-ontap, and pyATS/Genie.
- Added `make provider-lab-toolchain-check`.
- Added Build Verification `Toolchain Readiness` UI panel.
- Added Cisco console transport abstraction fields for `local_serial` and TCP console/ser2net.
- Preserved local serial as the default.
- Added managed-state plan data for Cisco, HPE/iLO, ESXi/vSphere, NetApp, and firmware.

## Not Implemented In This Run

- No destructive hardware workflow was run.
- No live provider endpoint was contacted by the toolchain check.
- No arbitrary command execution was exposed through the UI.
- No vendor apply lane was enabled.
