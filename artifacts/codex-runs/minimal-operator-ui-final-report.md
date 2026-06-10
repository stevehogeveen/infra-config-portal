# Minimal Operator UI Final Report

Date: 2026-06-09
Scope: presentation-layer UX/product cleanup in `/home/administrator/infra-config-portal`.

No real hardware workflows were run. Screenshots were captured against a mock backend on a temporary local port with browser API requests routed to that mock backend.

## What Changed

- Added a local Operator / Advanced mode preference, defaulting to Operator mode.
- Collapsed commands, report paths, run traces, registry metadata, gate internals, raw evidence, and long diagnostic lists behind Advanced or Evidence sections.
- Reworked Lab Setup into a compact setup list with a selected-step detail panel.
- Simplified NetApp default view to console, ONTAP state, management, NFS datastore, upgrade, next action, one blocker, one primary action, refresh, and collapsed proof.
- Simplified Firmware / Upgrades to status rows, one next action, one blocker, and collapsed proof.
- Reduced Reports default view to summary counts, top fixes, filters, collapsed action links, and collapsed evidence. Full issue rows are Advanced-only.
- Reduced Control Center to a compact action table. Full commands, gates, reports, traces, and action metadata stay in details/Advanced.
- Humanized visible labels such as Real Lab Mode, Previous evidence, Live check, Setup wizard detected, Not configured yet, Waiting on earlier step, and Validate ONTAP upgrade.

## Moved To Advanced / Evidence

- Report paths and raw evidence artifacts.
- JSON payloads and raw probe details.
- Full make commands and command copy text.
- Registry action IDs and metadata.
- Required gates and confirmation flags.
- Run trace internals.
- Long blocker and warning lists.
- Firmware baseline/package internals and raw version comparison detail.
- NetApp local media inventory, planned API calls, upgrade condition details, and disabled action internals.

## Pages Changed

- Dashboard: mode toggle and cleaner test-mode language are available through the app shell.
- Lab Setup: compact list/detail setup workflow.
- Run Center: Operator-mode setup rows and focused NetApp panel.
- Control Center: compact action table in Operator mode, detailed action view in Advanced.
- Firmware / Upgrades: compact firmware status panel in Operator mode.
- Lab Validation: raw command/source/freshness details moved under Advanced.
- Reports: summary-first default with full issue details moved to Advanced.
- Settings / Lab Profile: app-shell mode preference and human labels apply consistently.

## Screenshots

- `artifacts/screenshots/minimal-lab-setup.png`
- `artifacts/screenshots/minimal-netapp.png`
- `artifacts/screenshots/minimal-firmware.png`
- `artifacts/screenshots/minimal-control-center.png`
- `artifacts/screenshots/minimal-reports.png`
- `artifacts/screenshots/minimal-advanced-expanded.png`

## Validation

- `npm run build` from `app/frontend`: passed.
- `make lint`: passed.
- `make test`: passed, including `344 passed in 347.42s (0:05:47)` and frontend production build.

## Remaining Clutter

- `app/frontend/src/App.tsx` is now very large; future UI cleanup should extract the new minimal components into focused files.
- Control Center still has many action rows by design. A later pass could add stage grouping or a "recommended only" filter for Operator mode.
- The Reports top-fix titles now use humanized text, but some source issue names still come from backend report data in Advanced mode.
- The global sidebar issue badges are still always visible. They are useful, but a future pass could make them quieter in Operator mode.

## Next Recommended Cleanup

1. Extract `MinimalStageList`, `MinimalDetailPanel`, `MinimalNetAppPanel`, `FirmwareMinimalOverview`, `ModeToggle`, and report summary components out of `App.tsx`.
2. Move human label maps into a shared frontend helper and cover them with small unit tests.
3. Add a "recommended actions only" filter to Control Center Operator mode.
4. Add a backend-provided minimal summary DTO so the frontend does less display-shaping.
5. Add Playwright smoke tests for Operator mode on Lab Setup, NetApp, Firmware, Control Center, and Reports.

## Skill Improvement Review

Skills used: lab-builder-skill-steward, lab-builder-real-runtime, lab-builder-ux, lab-builder-product-craft, lab-builder-hardware-run, lab-builder-report-remediation, lab-builder-toolchain, and lab-builder-dual-app-architecture.

No skill files were changed. A useful future reusable skill would be a "minimal operator UI review" checklist that combines clutter audit, label humanization, evidence collapse, and screenshot validation.
