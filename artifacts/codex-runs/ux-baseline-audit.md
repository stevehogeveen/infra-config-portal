# UX Baseline Screenshot Audit

Captured: 2026-06-06

## Screenshots

- `artifacts/screenshots/ux-baseline-provider-status.png`
- `artifacts/screenshots/ux-baseline-cisco.png`
- `artifacts/screenshots/ux-baseline-hpe-ilo.png`
- `artifacts/screenshots/ux-baseline-raid.png`
- `artifacts/screenshots/ux-baseline-esxi.png`
- `artifacts/screenshots/ux-baseline-build-verification.png`

## Current Shape

- The page opens on Provider Status with a real-lab warning banner, provider tabs, a lab-wide reports collapsible, and the selected provider panel.
- The default iLO view already includes nested detail sections, but still shows configuration presence flags, readiness facts, action panels, protected actions, and advanced evidence on the first screen.
- Cisco, RAID, ESXi, and Build Verification each require navigating or expanding separate areas instead of following a single build journey.
- Statuses are technically accurate but expose raw backend language such as `local-lab-readwrite`, `blocked_by_prior_stage`, and provider/action IDs.
- Raw report paths, command text, detailed endpoint data, and long diagnostic lists appear too close to the main workflow.

## Baseline Risks

- A new operator has to infer the build order from provider tabs and page sections.
- The highest-priority blocker is not isolated in a single summary.
- The next action competes with provider modes, warnings, protected actions, and diagnostic panels.
- Warnings and blocked states feel equally prominent even when a stage is simply waiting on prior work.
- Build Verification is hidden in a lab-wide evidence collapsible rather than presented as the final workflow stage.
