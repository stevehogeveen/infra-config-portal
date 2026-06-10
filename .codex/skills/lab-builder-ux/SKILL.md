---
name: lab-builder-ux
description: Use when designing or changing Lab Builder or Infra Config Portal operator UI, navigation, setup pages, status colors, blocker presentation, Reports, or next-action UX.
---

# Lab Builder UX

## Use This Skill When

Use this skill before changing visible UI, page structure, navigation,
operator wording, readiness surfaces, blocker displays, reports, evidence
views, or setup workflows.

## Layout Rules

- Use sidebar navigation for top-level app pages.
- Prefer list rows plus one detail panel over many large cards.
- Keep main lab setup pages focused on essentials only: target, readiness,
  current blockers, planned action, and next action.
- Reports, evidence, logs, raw JSON, and verbose artifacts belong in Reports or
  collapsed detail sections.
- Every page needs one clear next action. It should be visible without hunting
  through raw output.
- Do not rely on color alone. Pair color with text labels, icons, or status
  copy that names the state.

## Status Color Semantics

- Red is only for current real blockers.
- Yellow is for warning, stale evidence, or partial readiness.
- Neutral is for not configured yet or not checked yet.
- Green is for ready.

If evidence is stale, label it as stale and offer the recheck command. Do not
make old report links or historical artifact warnings look like live blockers.

## Operator Page Checklist

- Sidebar exposes top-level pages consistently.
- Primary setup pages do not show raw JSON by default.
- Each status includes source, checked time, freshness, and a recheck path when
  the backend provides it.
- Empty states explain what is missing and provide the next action.
- Blocked states show the problem, where to fix it, and a copyable command when
  practical.
