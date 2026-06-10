---
name: lab-builder-report-remediation
description: Use when building or revising Lab Builder reports, blocker summaries, remediation issue cards, evidence links, stale config warnings, or operator fix instructions.
---

# Lab Builder Report Remediation

## Use This Skill When

Use this skill before changing report generation, Report Center, blocker
models, remediation UI, evidence presentation, current-state reports, or final
run summaries.

## Report Rules

- Reports must produce action, not just evidence.
- Report links should not appear as main blockers.
- Evidence belongs collapsed under issue cards or in Reports detail views.
- Historical evidence must be labeled with source and checked time.
- Stale config must show the exact field and the fix path.
- Never print secret values. For secrets, show `configured`, `missing`, or
  `redacted`.

## Blocker Contract

Every blocker must include:

- `problem`: concise statement of what prevents progress.
- `source`: where the blocker came from.
- `current_value`: the current observed or configured value.
- `expected_value`: the required value or state.
- `where_to_fix`: UI path, config field, file path, or host-side location.
- `recommended_action`: what the operator should do next.
- `copyable_command`: command the operator can run, when practical.
- `recheck_command`: command to refresh the status after the fix.
- `evidence_links`: links to relevant artifacts or reports.

If a blocker is based on old evidence, downgrade it to stale evidence until a
fresh check proves it is current.

## Remediation UI Checklist

- One issue card per actionable blocker.
- The top of the report shows current blockers first, then warnings, then
  historical evidence.
- Evidence links live under the issue card, not as the blocker headline.
- Copyable commands are local, explicit, and scoped to the relevant check.
- Recheck commands are shown beside or below the recommended action.
