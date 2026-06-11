# Grand Operation Stage 10 - App Usability Report

Generated: 2026-06-10T23:37:09Z

## Scope

Operator walk-through covered Dashboard, Lab Setup context, Hardware, Control Center, Firmware Upgrades, Validation & Reports, and Settings shell state in real-lab mode.

Applied skills: lab-builder-skill-steward, lab-builder-real-runtime, lab-builder-hardware-run, lab-builder-toolchain, lab-builder-report-remediation, lab-builder-ux, lab-builder-product-craft, lab-builder-dual-app-architecture.

## Screenshots

- `artifacts/screenshots/grand-operation-dashboard.png`
- `artifacts/screenshots/grand-operation-hardware-list.png`
- `artifacts/screenshots/grand-operation-cisco.png`
- `artifacts/screenshots/grand-operation-ilo.png`
- `artifacts/screenshots/grand-operation-esxi.png`
- `artifacts/screenshots/grand-operation-netapp.png`
- `artifacts/screenshots/grand-operation-firmware.png`
- `artifacts/screenshots/grand-operation-validation.png`

## Fixes Applied

- Dashboard current-state summary now includes Report Center blockers, so the status card no longer says the queue is clear when issue badges show critical blockers.
- Hardware evidence and action dropdown keys are stable; duplicate React key warnings are removed.
- Control Center now waits for the action catalog and workflow registry together before rendering section bodies, avoiding blank operator pages during slow catalog load.
- Hardware page now shows a loading state while live provider status is still loading instead of presenting all rows as not checked.
- Control Center blocker summary now merges section action blockers with workflow-registry blockers, so NetApp no longer shows a false clear state while the section is blocked.

## Validation

- `npm run build` passed after each frontend patch.
- Playwright screenshot pass completed with no browser page errors.
- Console output after screenshot refresh only included Vite connection and React DevTools development messages.

## Operator Findings

- Active lab setup is visible in the shell and matches the `192.168.1.0/24` high-address profile.
- Hardware table now populates live/provider-backed Cisco, iLO, ESXi, and NetApp readiness, with IP and access fields driven by active lab setup and discovery evidence.
- Control Center pages show compact access/config/action sections with advanced evidence collapsed by default.
- Firmware Upgrades shows loaded compliance warnings and proof count after catalog load.
- Validation & Reports still shows stale Cisco blockers from Report Center. Stage 11 must refresh or reclassify reports so historical Cisco bootstrap evidence is not treated as a current blocker after live Cisco validation succeeded.
- ESXi Control saved setup text still says SSH is disabled until enabled, while live validation found SSH reachable. Stage 11 should reconcile saved setup intent versus live state or label the mismatch explicitly.

## Remaining UI Debt

- Report Center needs a current-run refresh path that downgrades historical artifacts unless a fresh check proves the blocker still exists.
- Firmware compliance warning copy for iLO says a live inventory check is needed even though iLO inventory ran; compliance should distinguish live inventory age from missing baseline policy.
- Direct apply/run controls are still mostly copy-command oriented. That is acceptable for the guarded run, but future work should consolidate explicit confirmation actions into one run-center pattern.
