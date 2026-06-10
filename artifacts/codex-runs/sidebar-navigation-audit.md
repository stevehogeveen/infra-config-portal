# Sidebar Navigation Audit

Date: 2026-06-08

## Scope

Focused UX/layout/navigation simplification for `/home/administrator/infra-config-portal`.
No real hardware workflow commands were run. Browser validation used the already-running local mock app.

## Baseline Screenshots

- `artifacts/screenshots/nav-before-dashboard.png`
- `artifacts/screenshots/nav-before-run-center.png`
- `artifacts/screenshots/nav-before-control-center.png`

## Main Findings

- Top-level destinations were mixed with task/detail pages in the sidebar, including VM requests, new request, lab profiles, audit events, media inventory, artifacts, and provider status.
- Global mode/profile information was repeated above page content, adding noise before the operator reached the page task.
- Run Center had a second competing tab model (`Choose Run`, `Work Queue`, `Selected Work`, `NetApp Preview`) instead of provider-oriented page sections.
- Control Center rendered every catalog section and the action catalog in one long page, making the active task hard to identify.
- Provider/build verification content was concentrated in a giant Lab Builder/Provider Status surface rather than split into Firmware, Verification, Reports, and Settings destinations.
- Deep report paths, raw payloads, stale-address diagnostics, and provider internals were visible too early.
- Mobile navigation behaved like a wrapped top nav, not a drawer.

## Safety Observations

- The UI continues to present mock/provider mode and active lab profile summary.
- Existing direct-run controls remain disabled where they were disabled before.
- New pages consume existing GET/read metadata and do not introduce provider automation.
- Advanced diagnostics remain available but collapsed by default.
