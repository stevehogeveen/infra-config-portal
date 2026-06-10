# Minimal Control Surface Final Report

Date: 2026-06-10

Scope: `/home/administrator/infra-config-portal` frontend control-surface overhaul. No real hardware workflow was run. Screenshots were captured against mocked browser API responses only.

## Pages Merged

Merged the former top-level destinations:
- Verification
- Lab Validation
- Reports

Into:
- Validation & Reports

Legacy routes now redirect:
- `/verification` -> `/validation-reports`
- `/lab-validation` -> `/validation-reports?section=validation`
- `/reports` -> `/validation-reports?section=issues`
- `/artifacts` -> `/validation-reports?section=evidence`

The sidebar top-level structure is now:
- Dashboard
- Lab Setup
- Control Center
- Firmware Upgrades
- Validation & Reports
- Settings / Lab Profile

## Clutter Removed From Default Surfaces

Default device/control views no longer lead with:
- report paths
- raw artifact lists
- registry action rows
- command text
- current/desired/diff debug tables
- JSON diagnostics
- run traces
- all report links

These remain available inside Advanced / Evidence.

## Default UI Now Shows

Each standard control section now shows:
- one firmware warning strip
- access block with management target, URL/SSH/console where applicable, username field name only, live status, and access buttons
- core config block driven by the active lab profile where available
- compact Actions / Configs dropdown
- collapsed Advanced / Evidence details

Dashboard now shows:
- active lab profile selector
- compact profile values
- profile mismatch warning for live runtime alignment
- no `.env` edit requirement for normal profile switching

Firmware Upgrades now shows a global overview for:
- iLO
- Cisco
- ONTAP
- ESXi
- BIOS
- Smart Array

## Hidden Under Advanced / Evidence

Advanced / Evidence contains:
- raw report paths
- artifact links
- registry IDs
- make targets and command handoff
- run traces
- current/desired/diff diagnostic tables
- raw JSON payloads
- long evidence lists

Validation & Reports owns:
- readiness/certification summary
- issue list
- proof/handoff
- evidence/report links
- validation details

## Screenshots

Captured:
- `artifacts/screenshots/min-control-dashboard-profile.png`
- `artifacts/screenshots/min-control-cisco.png`
- `artifacts/screenshots/min-control-netapp.png`
- `artifacts/screenshots/min-control-firmware-upgrades.png`
- `artifacts/screenshots/min-control-validation-reports.png`
- `artifacts/screenshots/min-control-actions-dropdown.png`
- `artifacts/screenshots/min-control-advanced-expanded.png`

## Validation

Passed:
- `npm run build` from `app/frontend`
- `npm run test:e2e` from `app/frontend`: 5 passed
- `make lint`
- `make test`: 344 passed in 211.97s, then frontend production build passed

## Remaining UX Work

- `app/frontend/src/App.tsx` is too large; the new profile, validation/report, and standard control section components should be extracted.
- Standard control sections currently use frontend shaping over existing backend catalog data. A later backend DTO could provide the exact minimal section model.
- Lab Setup still links to Run Center as a secondary workflow detail. A future pass could make that less prominent if the operator flow no longer needs it.
- Settings / Lab Profile can better separate normal profile switching from live runtime alignment tooling.
- Control action options are seeded in the frontend. A later pass should move them behind a backend option contract if other clients need them.

## Next Recommended Implementation Pass

1. Extract `ValidationReportsPage`, standard control section layout, and profile context/components into focused files.
2. Add a backend `control_options` DTO with `option_id`, effect, availability, support path, and linked action IDs.
3. Add active-profile-aware backend values for NFS LIFs and storage protocol choices instead of UI literals.
4. Add a Settings / Lab Profile runtime-alignment panel that explains live-check env alignment without exposing secrets.
5. Add mobile screenshot coverage for Dashboard, NetApp, Firmware Upgrades, and Validation & Reports.

## Skill Improvement Review

Skills used:
- lab-builder-skill-steward
- lab-builder-real-runtime
- lab-builder-ux
- lab-builder-product-craft
- lab-builder-hardware-run
- lab-builder-report-remediation
- lab-builder-toolchain
- lab-builder-dual-app-architecture

No skill files were created or updated. A reusable future skill could capture this specific minimal control surface checklist: merge evidence surfaces, standardize warning/access/config/action/evidence sections, profile-driven values, and screenshot validation.
