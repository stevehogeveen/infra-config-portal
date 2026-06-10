# Sidebar Navigation Design

Date: 2026-06-08

## Architecture

The app now uses a product-shell model:

- Persistent desktop sidebar for top-level destinations.
- Mobile drawer for small screens.
- Page header with title, short description, and one primary next action.
- Page-local `SectionSwitch` for subsections.
- Compact main section surfaces with details behind collapsed `AdvancedDetails`.

## Sidebar Destinations

- Dashboard: `/dashboard`
- Run Center: `/run-center`
- Control Center: `/control-center`
- Firmware / Upgrades: `/firmware`
- Build Verification: `/verification`
- Reports: `/reports`
- Settings / Lab Profile: `/settings`

Compatibility redirects keep `/`, `/artifacts`, and `/providers` usable without preserving the old cluttered destination model.

## Reusable Components Added

- `AppShell`
- `SidebarNav`
- `PageHeader`
- `SectionSwitch`
- `StatusSummaryCard`
- `NextActionCard`
- `BlockerSummary`
- `ReportLinkList`
- `EmptyState`

Existing `AdvancedDetails` is used as the standard place for raw evidence, report paths, action catalogs, provider payloads, and long diagnostics.

## Page Sections

Dashboard:
Overview, Current Blockers, Last Run, Next Actions.

Run Center:
Guided Build, Cisco, HPE / iLO, RAID, ESXi, NetApp.

Control Center:
Lab Profile, Cisco Control, HPE / iLO Control, RAID Control, ESXi Control, NetApp Control, Action Catalog.

Firmware / Upgrades:
Compliance, Inventory, Packages, Waivers, Upgrade Plans.

Build Verification:
Summary, Network, Storage, Firmware, Credentials, MTU / Protocols, Certification Report.

Reports:
Latest, Cisco, HPE / iLO, RAID, ESXi, NetApp, Firmware, Verification.

Settings / Lab Profile:
IP Profile, Credentials Status, Media Paths, Toolchain, Feature Flags, Waivers.

## Main Surface Contract

Each top-level section is designed to show:

- one status summary,
- one next action,
- one primary blocker or clear state,
- a compact fact set,
- collapsed details for long evidence.

## Responsive Behavior

Desktop keeps the sidebar visible and lets the main content scroll. Small screens show a menu button and slide-out drawer with the same navigation and lab profile summary. Section buttons wrap, and content cards stack into a single column.
