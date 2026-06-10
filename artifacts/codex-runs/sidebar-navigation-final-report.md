# Sidebar Navigation Final Report

Date: 2026-06-08

## What Changed

- Rebuilt the app shell around a persistent desktop sidebar and mobile drawer.
- Moved top-level navigation to the sidebar and limited it to seven product destinations.
- Added direct routes for `/dashboard`, `/run-center`, `/control-center`, `/firmware`, `/verification`, `/reports`, and `/settings`.
- Reworked Dashboard, Run Center, Control Center, Firmware, Verification, Reports, and Settings around page-local section controls.
- Moved long diagnostics, report paths, raw payloads, action catalogs, and provider internals into collapsed advanced/details areas.
- Kept existing request, workflow, lab profile, media, audit, and provider-detail functionality available through internal links or compatibility routes.

## Screenshots Captured

Before:

- `artifacts/screenshots/nav-before-dashboard.png`
- `artifacts/screenshots/nav-before-run-center.png`
- `artifacts/screenshots/nav-before-control-center.png`

After:

- `artifacts/screenshots/nav-after-dashboard.png`
- `artifacts/screenshots/nav-after-run-center.png`
- `artifacts/screenshots/nav-after-control-center.png`
- `artifacts/screenshots/nav-after-firmware.png`
- `artifacts/screenshots/nav-after-verification.png`
- `artifacts/screenshots/nav-after-settings.png`
- `artifacts/screenshots/nav-after-mobile-dashboard.png`
- `artifacts/screenshots/nav-after-mobile-drawer.png`

## Pages And Sections Added

- Firmware / Upgrades: Compliance, Inventory, Packages, Waivers, Upgrade Plans.
- Build Verification: Summary, Network, Storage, Firmware, Credentials, MTU / Protocols, Certification Report.
- Reports: Latest, Cisco, HPE / iLO, RAID, ESXi, NetApp, Firmware, Verification.
- Settings / Lab Profile: IP Profile, Credentials Status, Media Paths, Toolchain, Feature Flags, Waivers.

## Clutter Removed From Main Surfaces

- Repeated top-level navigation controls.
- Repeated provider mode/profile strip above every page.
- Giant all-provider Provider Status surface as a primary destination.
- Control Center all-sections-at-once rendering.
- Long report-path lists on the main surface.
- Raw JSON and raw provider evidence on primary cards.
- Most repeated blockers and diagnostics.

## What Remains Too Busy

- Some expanded advanced sections are still dense because they preserve existing provider controls and diagnostics.
- Control Center action catalog remains table-heavy when selected.
- Firmware and verification blocker text can still be long because backend messages are operator-detailed.
- The hidden full Lab Profiles editor remains dense and should get its own follow-up simplification.

## Validation

- `npm run build` from `app/frontend`: passed.
- `make lint` from repo root: passed.
- Browser screenshots captured through the local mock app on `127.0.0.1:5173`.
- Mobile drawer and mobile dashboard layout checked with Playwright screenshots.

## Recommended Next UX Pass

- Convert expanded provider control details into smaller task cards per action family.
- Add copy/report affordances to `ReportLinkList` consistently.
- Simplify the full Lab Profiles editor under `/lab-profiles`.
- Add URL query/hash persistence for every page-local section, not just Control Center.
- Normalize backend status and blocker message lengths for card display.
