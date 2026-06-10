---
name: lab-builder-real-runtime
description: Use when working on Lab Builder or Infra Config Portal runtime status, live provider state, freshness, blocker classification, mock-vs-real boundaries, or local-lab-readwrite execution gates.
---

# Lab Builder Real Runtime

## Use This Skill When

Use this skill before changing status models, readiness APIs, provider runtime
state, blocker classification, runtime reports, or UI that claims to show lab
status.

## Runtime Rules

- Mock and test data is test-only. It must never be presented as current real
  lab status.
- Never use mock results as a substitute for real lab status. If the real path
  cannot run, report the real blocker or environment limitation.
- Operator UI must clearly label each status as `live`, `stale`,
  `not_checked`, or `historical`.
- Historical artifacts are evidence. They are not current blockers unless a
  fresh check proves the blocker still exists.
- Running real workflows requires the explicit real-lab write lane:
  `local-lab-readwrite`. Do not silently fall back to mock mode.
- Keep provider integrations mock-first by default. Real runs require explicit
  local configuration and the task must be scoped to real-lab validation or
  operation.

## Status Contract

Every provider, tool, workflow, and lab target status should expose these
fields:

- `source_type`: where the value came from, such as `live_provider`,
  `tool_probe`, `operator_config`, `historical_artifact`, `mock`, or `test`.
- `checked_at`: ISO 8601 timestamp for the check, or `null` when it has not
  been checked.
- `freshness`: `live`, `stale`, `not_checked`, or `historical`.
- `recheck_command`: the exact local command the operator can run to refresh
  the status.

If a value comes from an artifact, include the artifact link as evidence and
show when it was produced. Do not let the existence of an old artifact create a
red current blocker.

## Implementation Checklist

- Keep current-state fields separate from historical evidence fields.
- Preserve redaction. For credentials and secrets, show only `configured`,
  `missing`, or `redacted`.
- Add tests for stale, not-checked, mock/test, and live-status classification
  when changing status logic.
- In final reports, state whether a real workflow was run. If not, say no
  hardware workflow was run.
