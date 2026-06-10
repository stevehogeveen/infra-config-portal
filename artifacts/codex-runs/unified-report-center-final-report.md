# Unified Report Center Final Report

Date: 2026-06-08

## Outcome

Built a unified Reports & Issues experience that aggregates provider and lab
workflow findings into one issue system. The backend exposes normalized issue
payloads, and the frontend now uses that payload for the Reports & Issues page,
sidebar badges, and top-level page indicators.

No destructive hardware workflows were run. Validation used mock-safe API reads,
unit tests, lint, frontend builds, and screenshots against the local app.

## Implemented

- Added backend report-center aggregation service:
  - `app/backend/app/services/report_center.py`
  - Aggregates build verification, firmware compliance, Cisco readiness
    artifacts, iLO, RAID, ESXi, NetApp, toolchain, lab profile, and serial
    console findings.
  - Normalizes findings into common issue fields with severity,
    classification, next action, recheck command, source report, evidence, and
    linked page.
  - Treats missing optional reports as `not_configured_yet`/not-run instead of
    critical failures unless the stage is required.
  - Redacts sensitive-looking values before returning issues.

- Added API routes and schemas:
  - `GET /api/v1/reports/issues`
  - `GET /api/v1/reports/summary`
  - Schemas added in `app/backend/app/schemas.py`
  - Routes added in `app/backend/app/api/routes.py`

- Added focused backend tests:
  - `app/backend/tests/test_report_center.py`
  - Covers build verification aggregation, firmware critical blocking,
    stale-config detail fields, neutral not-configured state, evidence handling,
    badge source mapping, optional missing reports, and secret redaction.

- Rebuilt the frontend Reports page as Reports & Issues:
  - Summary counts: Critical, Needs Review, Not Configured Yet, Passed.
  - Top Fixes: top three critical/warning issues with next actions.
  - Filters: All, Critical, Warnings, Stale Config, Cisco, ESXi, NetApp,
    Firmware, Lab Profile.
  - Issue cards show severity label/icon, title, problem, next action, source
    stage, last checked, recheck command, source page, stale-config fields, and
    collapsed evidence.
  - Raw report links are grouped under collapsed Evidence instead of being the
    primary page content.

- Added page-level issue indicators:
  - Dashboard
  - Run Center
  - Control Center
  - Firmware / Upgrades
  - Build Verification
  - Reports
  - Settings / Lab Profile

- Added sidebar issue badges:
  - Red blocked counts for critical issues.
  - Yellow review counts when applicable.
  - Green ready state.
  - Neutral not-configured state.

- Updated visual treatment:
  - Red critical/blocked styles.
  - Yellow needs-review styles.
  - Blue neutral not-configured styles.
  - Green ready/passed styles.
  - Labels are explicit and do not rely on color alone.

- Lint-only compatibility fix:
  - `app/backend/scripts/build_verification.py` keeps its local env preload
    before service import and uses `# noqa: E402` on that import so ruff passes
    without changing runtime order.

## Audit Artifact

- `artifacts/codex-runs/unified-report-center-audit.md`

## Screenshots

- `artifacts/screenshots/reports-issues-overview.png`
- `artifacts/screenshots/reports-issues-filter-critical.png`
- `artifacts/screenshots/reports-issues-stale-config.png`
- `artifacts/screenshots/sidebar-issue-badges.png`
- `artifacts/screenshots/firmware-page-red-issue.png`

## Validation

- `app/backend/.venv/bin/python -m pytest tests/test_report_center.py -q`
  - Result: 9 passed
- `npm run build`
  - Result: passed
- `make lint`
  - Result: passed
- `make test`
  - Result: 300 backend tests passed, then frontend production build passed

## Safety Notes

- No destructive hardware workflows were run.
- No provider write/apply/reset workflow was run.
- The report center reads existing payloads, cached/local summaries, and
  artifact metadata; it does not execute live destructive provider actions.
- Secrets are not printed in the report center payload and secret-like values
  are redacted in normalized issue details.
