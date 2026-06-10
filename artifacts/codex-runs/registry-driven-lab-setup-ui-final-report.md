# Registry-Driven Lab Setup UI Final Report

Date: 2026-06-09

## Summary

- Kept Lab Setup driven by `/api/v1/workflows/stages` with a registry stage list and selected-stage detail panel.
- Updated shared registry rows so every stage row shows status, summary, primary next action, source type, freshness, last checked, issue count, and visible recheck command.
- Added a copyable primary recheck command strip to the selected stage detail panel.
- Updated action rows to show recheck command, source/freshness, last run, issue count, and copy/detail controls without expanding raw evidence.
- Kept Control Center focused on the registry action catalog: action, stage, provider, mode, availability, last run, command, and details.
- Kept legacy Control Center state, plan diff, report links, and diagnostics collapsed as evidence.
- Kept Reports issue-to-action links based on registry labels where available, with raw report artifacts under Evidence drawers.
- Historical artifacts remain labeled as `historical_artifact` / `historical` and are treated as evidence requiring recheck, not current live blockers.

## Files Changed

- `app/frontend/src/App.tsx`
- `app/frontend/src/styles.css`
- `artifacts/codex-runs/registry-driven-ui-clutter-audit.md`
- `artifacts/codex-runs/registry-driven-lab-setup-ui-final-report.md`

## Screenshots

- `artifacts/screenshots/registry-lab-setup-list.png`
- `artifacts/screenshots/registry-stage-detail-netapp.png`
- `artifacts/screenshots/registry-control-center-actions.png`
- `artifacts/screenshots/registry-reports-evidence.png`

## Validation

- `npm run build` from `app/frontend`: passed.
- `make lint`: passed.
- `make test`: passed.
  - Backend: `317 passed in 226.24s`
  - Frontend build: passed.

## Safety Notes

- No destructive hardware workflow was run.
- No provider write workflow was run.
- Test validation used `PROVIDER_MODE=mock`.
- The screenshots were captured by navigating local UI pages only.
- Mock/test state was not treated as real lab state.
- Historical artifacts are shown as evidence and require recheck before being considered current.
- No secrets were printed or summarized.

## Skill Improvement Review

- Skills used: `lab-builder-skill-steward`, `lab-builder-real-runtime`, `lab-builder-ux`, `lab-builder-product-craft`, `lab-builder-hardware-run`, `lab-builder-report-remediation`, `lab-builder-toolchain`, `lab-builder-dual-app-architecture`.
- Skills created or updated: none.
- Skill gaps found: none requiring a new reusable skill.
- Candidate skills deferred: none.
- Why no additional skills were created: this cleanup reused existing registry, status, UX, hardware-run, toolchain, report-remediation, and dual-app guidance.
