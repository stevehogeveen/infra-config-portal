# Validation Ready-To-Ship Copy Evidence

Date: 2026-07-18

Slice: Validation normal-mode vocabulary cleanup.

Changed operator-facing normal mode:
- Card title: `Ready to ship?`
- Ready headline: `Ready to ship`
- Ready copy: `All required checks are ready and the report exists.`
- Primary actions: `Review report`, `Create report`, or `Run validation`
- Details label: `Kit readiness details`
- Details section: `Report files`

Kept behind details/advanced:
- Validation reference table
- Raw proof links
- Advanced proof
- Factory reset and rebuild danger zone
- Guarded reset/rebuild controls

Validation:
- `npm run test:e2e -- --grep "remaining operator pages expose simplified setup surfaces|create report primary action|safe read-only page action|validation readiness card hides raw provider-mode|validation no-kit state|advanced proof is collapsed|validation details do not expose"`: 7 passed.
- `npm run build`: passed.
- `npm run test:e2e`: 79 passed, 4 skipped.
- `git diff --check`: passed.
