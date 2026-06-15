# Simplify Overview / Firmware Audit

- Generated at: `2026-06-15T15:29:04Z`
- Scope: UI/product audit only
- Hardware workflows run: `false`
- Secret handling: no credentials, tokens, raw env, or raw provider output included

## Current Default Clutter

- Overview still presents a status-dashboard header with `Next action`, `Generate Handoff`, `View Validation`, and an inventory table before the operator sees the full lab values.
- Overview uses "Hardware and software" inventory language where the requested default model is "Active Lab Setup", "Lab Values", and "Currently Accessible".
- Validation still shows proof counts and validation rows by default; this should stay available but belongs under Advanced for the simplified default.
- Page headers across domain pages include a repeated `Next action` panel. For this pass, the most important removal is Overview and Firmware, where the user specifically wants calm default pages.
- Firmware Upgrades shows package count, manual baseline review, current scan, and apply lane as a dashboard-like summary before file location and selected files.
- Firmware Upgrades uses path/status terms such as `manual_review` through raw-ish compliance concepts, then humanizes only part of the table.

## Evidence / Proof Shown Too Early

- Overview has an Advanced proof drawer, which is good, but the header still advertises validation and handoff actions by default.
- Validation shows `Proof count` and a proof list outside the Advanced drawer.
- Firmware proof is already behind an Advanced drawer, but row-level package/path language still reads like compliance evidence rather than file selection.

## Repeated Status Blocks

- Overview duplicates runtime status, validation status, provider status, and inventory status in one viewport.
- Firmware duplicates compliance status, media inventory status, manual baseline review, upgrade path state, and page run action availability.
- Settings repeats active setup values that should be available from Overview's simplified lab values section.

## Lab Setup Content To Move

- Top-level navigation already omits Lab Setup.
- `/lab-setup` currently redirects away from a top-level page, which matches the desired direction.
- Useful pieces to keep surfaced from Overview:
  - Active lab setup name
  - subnet/topology
  - gateway, DNS, NTP, VLAN, MTU
  - core device IPs
  - NetApp LIFs and datastore
  - console mappings when discovered
  - one `Edit Config` entry point
- Detailed saved profile management should remain in Settings or Advanced.

## Firmware Problems

- Firmware page should start with file location, last scanned time, package count, and file actions.
- Current firmware rows are derived from summaries/upgrade paths and can produce multiple rows for the same device/component when backend data repeats component details.
- Selected file identity is not obvious enough; it should show exact selected firmware file name or `No file selected`.
- The UI needs a dropdown for alternate candidate files, even if the first pass stores user selection only in frontend state.
- Status language should be simplified to:
  - Current
  - Upgrade available
  - Scan needed
  - File needed
  - Needs review
  - Not set up
  - Ready to upgrade

## Implementation Direction

- Replace Overview's default structure with:
  - Active Lab Setup
  - Lab Values
  - Currently Accessible
  - Advanced collapsed proof/details
- Keep the global `Edit Config` button and add an Overview-local `Edit Config` button that opens the same drawer.
- Make Firmware Upgrades start with a `Firmware Files` panel:
  - Directory: `/home/administrator/infra-config-portal/artifacts/Media`
  - Last scanned
  - Package count
  - Rescan Files
  - Open Media Inventory
- Build a deduped firmware table with one row per requested equipment/component pair, candidate dropdowns, simple status labels, and disabled upgrade buttons unless gated ready.
- Use frontend selection state for user file overrides in this pass; document backend persistence as next needed work.

## Skill Improvement Review

- Skills used: lab-builder-skill-steward, lab-builder-ux, lab-builder-product-craft, lab-builder-real-runtime, lab-builder-report-remediation, lab-builder-toolchain
- Skills created or updated: none
- Skill gaps found: none requiring a new reusable skill
- Candidate skills deferred: none
