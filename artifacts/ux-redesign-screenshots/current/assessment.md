# Operator UI Redesign Assessment

Generated: 2026-06-16

## Active Rendered Files

- `app/frontend/src/App.tsx`
  - App shell, sidebar navigation, route table, mobile shell bar, mode toggle, active lab context.
  - Renders `/config` through `ActiveLabConfigDrawer embedded`.
- `app/frontend/src/operatorPages.tsx`
  - Active side-tab pages:
    - `/overview` -> `OperatorOverviewPage`
    - `/network` -> `OperatorNetworkPage`
    - `/server` -> `OperatorServerPage`
    - `/storage` -> `OperatorStoragePage`
    - `/virtualization` -> `OperatorVirtualizationPage`
    - `/firmware-upgrades` -> `OperatorFirmwareUpgradesPage`
    - `/validation` -> `OperatorValidationPage`
    - `/settings` -> `OperatorSettingsPage`
  - Shared tab state and header controls live here through `OperatorTabStateProvider`, `PageStatusHeader`, `TabSettingsDrawer`, and related helpers.
- `app/frontend/src/styles.css`
  - The rendered app shell, sidebar, operator pages, current-view panels, value grids, tables, settings drawers, and responsive behavior are styled here.
- `app/frontend/tests/safe-action-runner.spec.ts`
  - Existing mocked browser harness used to capture these screenshots without live hardware calls.

## Screenshot Inventory

Desktop screenshots:

- `artifacts/ux-redesign-screenshots/current/desktop/overview.png`
- `artifacts/ux-redesign-screenshots/current/desktop/network.png`
- `artifacts/ux-redesign-screenshots/current/desktop/server.png`
- `artifacts/ux-redesign-screenshots/current/desktop/storage.png`
- `artifacts/ux-redesign-screenshots/current/desktop/virtualization.png`
- `artifacts/ux-redesign-screenshots/current/desktop/firmware-upgrades.png`
- `artifacts/ux-redesign-screenshots/current/desktop/validation.png`
- `artifacts/ux-redesign-screenshots/current/desktop/edit-config.png`
- `artifacts/ux-redesign-screenshots/current/desktop/settings.png`
- `artifacts/ux-redesign-screenshots/current/desktop/media-inventory.png`

Mobile screenshots:

- `artifacts/ux-redesign-screenshots/current/mobile/overview.png`
- `artifacts/ux-redesign-screenshots/current/mobile/network.png`
- `artifacts/ux-redesign-screenshots/current/mobile/server.png`
- `artifacts/ux-redesign-screenshots/current/mobile/storage.png`
- `artifacts/ux-redesign-screenshots/current/mobile/virtualization.png`
- `artifacts/ux-redesign-screenshots/current/mobile/firmware-upgrades.png`
- `artifacts/ux-redesign-screenshots/current/mobile/validation.png`
- `artifacts/ux-redesign-screenshots/current/mobile/edit-config.png`
- `artifacts/ux-redesign-screenshots/current/mobile/settings.png`
- `artifacts/ux-redesign-screenshots/current/mobile/media-inventory.png`

## What Is Not Working

The current UI is organized but still feels like a stacked report, not an operator console.

- Every tab starts with a large hero-like header, then a large current-view panel, then more broad sections. This costs too much vertical space before the user gets to the actionable object list.
- Important entities are not the primary object. Cisco, iLO, ESXi, NetApp, vCenter, firmware components, and validation checks should feel like monitored assets or rows. They are currently buried inside value grids.
- The top-level Run button is visible, but the page does not visually explain what will run against which target before the operator clicks it.
- Settings are present, but they still feel like an extra panel attached to the page instead of an integrated run configuration for the selected target/domain.
- Overview is too long. It repeats lab values and accessibility rows as separate blocks, producing a full-page dashboard that is hard to scan.
- Mobile pages are far too tall:
  - Overview: 5220 px
  - Edit Config: 4269 px
  - Firmware Upgrades: 3767 px
  - Settings: 3553 px
  - Network: 3278 px
- Cards are overused. The UI presents many similar boxes with similar visual weight, so the primary status and next action do not dominate.
- Some pages show successful state and not-checked metadata together in ways that reduce confidence. Example: a page can show overall Ready while Source/Freshness still says Not checked.
- Media Inventory visually does not match the operator side-tab pages, even though firmware links into it.

## Useful Patterns From PRTG/Auvik-Like Tools

Use these as product direction, not as visual cloning.

- Sidebar is an inventory and domain map, not just navigation.
- Primary page shape is list/detail:
  - left or top list of devices/checks/components
  - selected detail pane
  - single action bar for the selected object
- Status colors are compact and repeated consistently:
  - device row status
  - current sensor/check status
  - last checked time
  - next action
- Operators scan tables first, then drill into detail.
- Alarms/blockers are surfaced before descriptive copy.
- A page should answer in one viewport:
  - What is affected?
  - What is the current state?
  - What is stale or blocked?
  - What action will run?
  - Where is the evidence?

## Proposed Product-Level Redesign

Replace the current stacked page model with a compact operator console model.

### App Shell

- Keep sidebar, but make it denser and status-aware.
- Add a persistent top context bar:
  - active lab
  - runtime mode
  - last global refresh
  - global issue count
- Remove large hero treatment from operational pages.
- Page header should be compact:
  - title
  - one-line purpose
  - primary Run button
  - Settings button
  - last run status

### Page Layout

Each side tab should use:

1. `DomainSummaryStrip`
   - compact counts: Ready, Warning, Blocked, Not Checked
   - selected tab runtime/source/freshness
2. `OperatorObjectList`
   - dense rows for devices/checks/components
   - each row includes status, target, source, checked time, next action
3. `OperatorDetailPane`
   - selected row details
   - run target preview
   - blockers/warnings
   - evidence links collapsed
4. `RunConfigDrawer`
   - IP mode, SNMP version, tab-specific run settings
   - explicit note for settings that are UI/session-only until backend persistence exists

### Page-Specific Object Lists

- Overview: rows for Cisco, iLO, ESXi, NetApp, vCenter, Datastore, VM Inventory, Firmware Gate, Validation.
- Network: rows for Cisco Management, Console, SSH/SCP, VLAN, DNS, NTP, SNMP, MTU, Firmware.
- Server: rows for iLO, Power State, RAID, ESXi Management, HPE Service Pack, BIOS/iLO, Smart Array.
- Storage: rows for ONTAP Cluster, Console, SVM, NFS LIFs, Volume, Export Policy, Datastore.
- Virtualization: rows for vCenter, ESXi Attach, Datastore Visibility, VM Inventory, OVF Deployment.
- Firmware: rows for each firmware component; selected detail shows current, target, selected file, path status, evidence, protected upgrade action.
- Validation: rows for validation checks; detail shows drift, blocker, proof, handoff readiness.
- Edit Config: left section selector plus right edit form; no huge all-fields form by default.
- Settings: split into runtime, credentials status, feature toggles, console mappings, media/toolchain.
- Media Inventory: align with firmware layout and make it a side-tab-adjacent inventory table, not a separate visual system.

## Implementation Direction

This should be a real frontend refactor, not more edits to the current stacked layout.

- Build reusable components in `operatorPages.tsx` or split into `app/frontend/src/operator/` modules:
  - `OperatorWorkspace`
  - `OperatorPageHeader`
  - `DomainSummaryStrip`
  - `OperatorObjectList`
  - `OperatorDetailPane`
  - `RunConfigDrawer`
  - `EvidenceDrawer`
- Convert each side tab to produce a list of `OperatorObjectRow` records.
- Keep backend calls mostly unchanged at first.
- Preserve safe run behavior and guarded apply boundaries.
- Remove duplicated value-grid blocks once their data is represented in rows/detail.
- Update Playwright coverage to assert:
  - one primary run button per page
  - settings drawer per page
  - object rows render for every side tab
  - selected row detail changes
  - mobile layout avoids thousands of pixels of repeated cards where possible

## First Code Slice

The first meaningful implementation slice should be:

1. Create the reusable operator console components.
2. Convert Overview, Network, Firmware, and Edit Config first.
3. Preserve old components for Server/Storage/Virtualization/Validation only until converted.
4. Take before/after screenshots from the same Playwright mock harness.
5. Confirm changed components are active through route/component references and browser screenshots.
