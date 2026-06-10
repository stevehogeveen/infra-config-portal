# Minimal Control Surface Audit

Date: 2026-06-10

Scope: `/home/administrator/infra-config-portal` frontend after the Minimal Operator UI pass. No real hardware workflow was run. Mock/test state was treated as UI test data only.

Applied skills:
- lab-builder-skill-steward
- lab-builder-real-runtime
- lab-builder-ux
- lab-builder-product-craft
- lab-builder-hardware-run
- lab-builder-report-remediation
- lab-builder-toolchain
- lab-builder-dual-app-architecture

## Top-Level Pages To Merge

The previous top-level sidebar still exposed three report-like destinations:
- Verification
- Lab Validation
- Reports

These pages duplicated the same operator question: is the lab ready, what is blocked, and where is proof? They should be one top-level destination named `Validation & Reports`.

`Run Center` is still useful as a workflow detail page, but it should not compete with the minimal top-level control surface.

## Duplicate Validation / Report Surfaces

Duplicate report and evidence surfaces were visible in:
- Build Verification certification report sections.
- Lab Validation handoff and proof links.
- Reports & Issues issue cards.
- Control Center legacy section evidence.
- Firmware compliance and upgrade plan details.

The combined destination should own readiness/certification summary, proof/handoff, issue list, evidence links, and validation detail. Other pages should link to it or hide report paths inside Advanced / Evidence.

## Control Sections Still Showing Too Much

The Control Center default device view still exposed registry-backed current/desired/diff tables, action rows, report links, and raw diagnostics too close to the main workflow. NetApp was the largest clutter source because setup, live state, NFS/vCenter, and ONTAP upgrade actions all surfaced report artifacts.

The new default control section layout should be:
1. One firmware warning strip.
2. Access block.
3. Config block.
4. Actions / Configs dropdown.
5. Advanced / Evidence collapsed.

## Sections Needing Access / Config / Action Layout

Required device/control sections:
- Cisco: IP, SSH, console, VLAN 10, ports, SNMP/NTP/DNS/MTU, validation actions.
- iLO / HPE: HTTPS access, hostname/DNS/NTP, boot, virtual media, power policy, firmware checks.
- RAID / Storage: controller through iLO, OS/datastore RAID intent, spare, boot priority, discover/plan/apply/validate.
- ESXi: HTTPS/SSH, management IP, hostname, DNS/NTP, vSwitch, datastore, API/SSH validation.
- NetApp: console/future HTTPS, cluster/node/SVM/NFS/iSCSI IPs, DNS/NTP/SNMP/MTU, NFS/iSCSI protocol choice, setup/upgrade actions.

## Labels Still Too Technical

Labels that needed simplification:
- `Firmware / Upgrades` -> `Firmware Upgrades`.
- `Reports & Issues` plus separate verification/validation pages -> `Validation & Reports`.
- `Control` -> `Control Center`.
- Registry IDs, report paths, make targets, source/freshness internals, and run traces should stay out of default labels.

## Profile Selection Gaps

The backend already supported active lab profiles, and the sidebar showed active profile context, but Dashboard did not provide the required profile selector as a first-class control.

Downstream profile-driven values should prefer the active profile when available. Runtime environment differences should be a live-check alignment warning, not a requirement to edit `.env` for normal profile switching.

## Default UI Rule

Default UI should show:
- one warning strip
- access status
- core config values
- one next action
- action/config dropdown
- details only on demand

Default UI should hide:
- long report paths
- artifact lists
- raw command blocks
- all actions at once
- all blockers at once
- JSON
- registry metadata
- stale historical evidence
