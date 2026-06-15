# Visual Product Overhaul Audit

Date: 2026-06-14

Scope: current app navigation, Control Center, Golden State, Firmware Upgrades, Validation, Hardware, Settings, and Run Center.

No real hardware workflow was run for this audit. Historical artifacts were treated as proof only, not as current blockers.

## Summary

The app has enough backend capability for the validated lab state, but the frontend still reads like an operations console for an IT specialist. The main problem is not missing data. The main problem is that setup, proof, diagnostics, action catalog entries, report paths, and runtime metadata are mixed together on primary pages.

The new model should make Overview the only informational page. Every other top-level page should focus on configuring or acting on one part of the lab: Network, Server, Storage, Virtualization, Firmware Upgrades, Validation, and Settings.

## Redundant Pages

- Dashboard overlaps with Hardware, Golden State, Validation, and Run Center. It should become Overview.
- Lab Setup overlaps with Settings and Control Center lab profile editing. It should become part of Settings.
- Hardware overlaps with Overview inventory, Server, Network, and Storage. It should stop being a top-level page and feed the Overview inventory.
- Control Center is too broad. Its Cisco, iLO, RAID, ESXi, NetApp, vCenter, firmware, reports, and action catalog sections should move into domain pages.
- Run Center is too central. Useful runs should move onto the page where the operator needs them.
- Golden State overlaps with Validation. Keep the term, but explain it as "Expected working lab state" inside Validation.
- Validation & Reports combines validation state, issue triage, proof, handoff, and raw evidence. The default page should be Validation; proof and long evidence should be collapsed.
- Reports and Artifacts are useful for advanced diagnosis, but they should not be top-level operator pages.
- Media Inventory is useful for firmware/package availability, but it belongs inside Firmware Upgrades advanced details.

## Buried Controls

- Cisco access tests, switch config save, VLAN/subnet settings, DNS/NTP/SNMP/MTU, and Cisco firmware scan are buried under Control Center sections and action catalog rows. They belong on Network.
- iLO tests, server power state, RAID validation, ESXi recovery, and reboot controls are split between Control Center, Hardware, and Run Center. They belong on Server.
- NetApp tests, NFS validation, datastore mount, and ONTAP refresh are split across Control Center NetApp, Run Center NetApp preview, Validation, and Firmware. They belong on Storage.
- vCenter tests, ESXi attach, datastore visibility, VM inventory, and OVF/VM deployment are split between Golden State, Validation, and action catalog. They belong on Virtualization.
- Firmware scan, upgrade path review, and apply controls are partially in Firmware Upgrades and partially in Control Center guarded controls. They belong on Firmware Upgrades.
- Full validation and handoff generation are split between Validation & Reports, Golden State, and Build Verification. They belong on Validation.
- Active lab setup, IP offsets, console mappings, credential state, and feature toggles are split between Lab Setup, Settings, Control Center access panels, and the config drawer. They belong on Settings.

## Report Clutter

- Report paths such as `artifacts/codex-runs/...` appear in primary tables and facts. These should be hidden under Advanced proof.
- Evidence artifacts are repeated in Hardware rows, Validation details, report issue cards, and firmware evidence. Primary pages should show proof counts or simple proof labels, not raw paths.
- Action history and reports are visible inside Control Center. This should be advanced-only.
- The app often shows source type, freshness, recheck command, report path, and action metadata in the same visual area. Default pages should show the status, last checked time, and one next action. Everything else belongs in Advanced.

## Mock And Test-Only Clutter

- Provider mode and test fixture wording are too prominent for operator workflows. Default views should say "Real lab", "Read-only lab", or hide mode details unless Advanced is opened.
- Mock/test/historical source labels should never look like live lab truth. If a status is not live, it should read as not checked, previous proof, or needs refresh.
- Registry metadata, action IDs, method names, and API endpoints appear in action catalog and diagnostic areas. They should be hidden from non-IT default views.

## Confusing Labels

- "Dashboard" is too generic. Use "Overview".
- "Hardware" is too broad. Split the work into Network, Server, Storage, and Virtualization.
- "Control Center" sounds like the main workflow, but it contains too many unrelated controls.
- "Run Center" suggests all work starts in one place. This conflicts with the requested page-owned action model.
- "Validation & Reports" should become "Validation". Reports should be advanced proof.
- "Golden State" can stay only with helper copy: "Expected working lab state."
- "Drift" should be "Different from expected."
- "Artifact" should be "Proof."
- "Workflow action" should be "Action."
- Raw statuses like `not_configured_yet`, `manual_review`, and `local-lab-readwrite` should render as "Not set up yet", "Needs review", and "Real lab."

## Run Button Placement

- Network should own Test Cisco Access, Apply Network Config, Save Config, and Scan Firmware.
- Server should own Test iLO, Test ESXi, Recover ESXi, Validate RAID, and Reboot Server.
- Storage should own Test NetApp, Validate NFS, Mount Datastore, and Refresh ONTAP.
- Virtualization should own Test vCenter, Attach ESXi, Validate Datastore, Deploy VM, and Validate VM Inventory.
- Firmware Upgrades should own Scan All Firmware, Review Upgrade Path, and Apply Upgrade.
- Validation should own Run Validation, Generate Handoff, and Refresh Evidence.
- Settings should own Save Setup, Test Credentials, and Refresh Consoles.

## Where A Non-IT User Gets Lost

- The first screen does not clearly answer "What exists, is it working, and what should I do next?"
- Top-level pages expose implementation boundaries instead of real-world domains.
- Many buttons have similar names but live in different places, so the operator has to know whether they need Control Center, Run Center, Firmware, Hardware, or Validation.
- Large tables mix inventory, access, credentials, status, action lists, and proof paths.
- Advanced concepts such as provider mode, action catalog, report classifications, registry actions, and raw proof paths are visible before the operator understands the lab.
- The current UI asks the operator to interpret report paths and action IDs instead of showing a plain next step.

## Target Direction

- Keep Overview read-only and simple.
- Put configuration and action buttons directly on the domain page.
- Use one layout standard: status header, access information, configuration values, action buttons, then collapsed advanced proof.
- Show active lab setup values everywhere.
- Show discovered values as discovered and let the operator save them from Settings when appropriate.
- Keep destructive and write actions disabled unless the guarded lane is explicit and ready.
