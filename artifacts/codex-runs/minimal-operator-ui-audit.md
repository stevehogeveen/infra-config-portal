# Minimal Operator UI Audit

Date: 2026-06-09

Scope: `/home/administrator/infra-config-portal` frontend presentation only. No real hardware workflow was run.

Applied skills:
- lab-builder-skill-steward
- lab-builder-real-runtime
- lab-builder-ux
- lab-builder-product-craft
- lab-builder-hardware-run
- lab-builder-report-remediation
- lab-builder-toolchain
- lab-builder-dual-app-architecture

## Product Rule

Default pages should answer only:

1. What is the current status?
2. What is blocking me?
3. What is the next action?
4. What button or command moves me forward?
5. Where can I see proof if I need it?

Everything else belongs in Advanced, Evidence, or Reports.

## Dashboard

Findings:
- Mostly aligned with the minimal rule already.
- Recent request and queue counts are correctly behind Advanced details.
- The page issue indicator can still add report-oriented clutter near the title, but this is acceptable as a small status cue.

Move/hide:
- Keep raw request table and queue counts behind Advanced.
- Keep report issue drill-in behind Reports.

## Lab Setup / Run Center

Findings:
- Lab Setup shows registry stage IDs, source/freshness internals, recheck commands, action counts, issue counts, action rows, action IDs, and evidence sections on the default surface.
- The stage detail panel repeats status and next-action content that already appears in the summary.
- Run Center repeats the registry stage list, stage detail panel, NetApp preview, and provider-specific action controls.
- Report links and raw evidence are present close to primary work areas.

Move/hide:
- Hide registry stage IDs, source/freshness internals, recheck commands, action lists, action IDs, command text, run traces, and evidence paths in Simple mode.
- Keep one compact list of setup stages plus one detail panel.
- Keep one primary action visible per selected stage.

## Control Center

Findings:
- The action catalog table exposes Action ID, provider, mode, availability, last-run freshness, command handoff, and detail controls by default.
- Commander mode and legacy control-section diagnostics are available, but the default table still reads like a registry/debug surface.
- Command text appears directly inside action rows.

Move/hide:
- Simple mode should show columns: Action, Stage, Type, Status, Run / Copy.
- Hide full command, gates, report paths, run trace internals, action IDs, provider IDs, and last-run source/freshness unless Advanced mode is enabled or an action is selected.

## Firmware / Upgrades

Findings:
- Compliance summary is reasonable, but it still treats component count, report links, package inventory, waiver details, and upgrade plan internals as page-level sections.
- Upgrade plans can expose action catalog/report details.
- Package path/list details are available from the main flow.

Move/hide:
- Simple mode should summarize iLO, Cisco, ONTAP, packages, and next action only.
- Hide baseline manifest details, waiver internals, package candidate lists, version comparison tables, upgrade command internals, and report links behind Advanced/Evidence.

## Lab Validation

Findings:
- Overview table is dense but operator-oriented.
- Detail panel exposes source/freshness, recheck command, proof points, evidence links, and datastore command previews on the default surface.

Move/hide:
- Keep component, status, summary, and next action visible.
- Move source/freshness, recheck command, proof links, and command previews to Advanced/Evidence.

## Reports

Findings:
- This page is the correct place for details, but it still displays every filtered issue as a full card by default.
- Report links are correctly grouped under Evidence, but issue cards include source stage/action/freshness/recheck command metadata by default.
- "Every report as a row" is reduced compared with older report lists, but full issue cards still dominate the page.

Move/hide:
- Default Reports should show issue summary counts, top 3 fixes, grouped evidence, and filters.
- Show only compact issue rows by default; expand details for source metadata, commands, and evidence.

## Settings / Lab Profile

Findings:
- Mostly uses collapsed details.
- Provider mode exposes restart command directly on the default settings page.
- Feature flags and toolchain details are appropriately collapsed, but labels are still technical.

Move/hide:
- Keep settings simple: current mode, desired mode, restart required, profile summary.
- Move restart command, feature flag keys, tool rows, and media rows under Advanced.

## NetApp Setup / ONTAP Upgrade

Findings:
- NetApp is the largest clutter source after recent setup/upgrade additions.
- Default NetApp view exposes provider ID, runtime mode, apply flag, configured flag, readiness buckets, planned/current target tables, setup/upgrade center, comparison panels, console details, storage/iSCSI preview, upgrade media candidates, artifact placeholders, historical artifact metadata, and disabled actions.
- Console autodiscovery and setup wizard evidence are present but surrounded by raw report paths, candidate counts, selected port/baud/source/confidence, and local metadata.
- Setup preview blockers correctly identify missing intent fields, but the UI exposes field-level details before the simple summary.
- ONTAP upgrade readiness exposes candidates, upgrade chain, disabled actions, validation details, and report links by default.

Move/hide:
- Simple mode should show only Console, ONTAP state, Management, NFS datastore, Upgrade, and Next action.
- Summarize "cluster_setup_wizard" as "Setup wizard detected".
- Summarize console at 115200 as "Console detected".
- Summarize missing setup intent fields as "Setup details missing".
- Summarize upgrade disabled as "Upgrade disabled until ONTAP setup is complete."
- Move report paths, media inventory, make targets, registry action IDs, confirmation flags, planned API call lists, raw ONTAP upgrade conditions, candidate tables, and artifact metadata to Advanced/Evidence.

## Pages Where NetApp/Upgrade Made Clutter Worse

- Run Center: NetApp section combines stage detail, setup/upgrade control, readiness comparison, real-lab console summary, NFS/vCenter readiness, reports, and artifact metadata.
- Firmware / Upgrades: ONTAP upgrade state competes with iLO/Cisco firmware status.
- Control Center: registry action catalog now contains many NetApp setup and upgrade actions.
- Reports: NetApp setup, live state, NFS/vCenter, and ONTAP upgrade reports increase issue/evidence volume.

## High-Priority Cleanup Targets

1. Add Simple/Advanced mode, defaulting to Simple.
2. Use one compact summary contract across stage rows and detail panels.
3. Replace technical labels on main surfaces.
4. Hide evidence paths, commands, report links, trace internals, and registry metadata in Simple mode.
5. Keep Reports as the organized evidence home instead of surfacing reports on setup pages.
