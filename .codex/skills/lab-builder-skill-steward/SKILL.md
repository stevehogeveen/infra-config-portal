---
name: lab-builder-skill-steward
description: Use when starting Lab Builder or Infra Config Portal tasks, maintaining project skills, deciding which Lab Builder skills apply, creating reusable skills, or adding skill improvement reviews to run reports.
---

# Lab Builder Skill Steward

## Use This Skill When

Use this skill at the start of project work in `infra-config-portal` or related
Lab Builder comparison runs. Use it again before creating or updating a
project skill.

## Steward Workflow

1. Inspect `.codex/skills/` before starting the task.
2. Select the smallest relevant set of Lab Builder skills automatically.
3. Read each selected `SKILL.md` before editing or reporting.
4. Record the applied skills in internal notes or run reports when the task
   produces an artifact.
5. Do not create or update skills just because a task is large. Create a skill
   only when it will reduce future mistakes or repeated prompt detail.

## Skill Creation Gate

Create or update a skill only when all of these are true:

- The workflow is reusable.
- It applies to multiple future tasks.
- It reduces future prompt length or mistakes.
- It captures a recurring failure mode, product rule, safety rule, or workflow
  shape.
- It includes clear `when to use` and `do not use` guidance.

If the case is useful but not proven reusable, list it as a future skill
candidate in the run report instead of creating it.

## Automatic Loading Rules

- Frontend, navigation, layout, state colors, operator wording, or evidence
  placement: use `lab-builder-ux` and `lab-builder-product-craft`.
- Runtime status, freshness, current-vs-historical state, real-vs-mock
  boundaries, or local lab gates: use `lab-builder-real-runtime`.
- Hardware workflow design, lab profiles, provider sequencing, console
  discovery, or run artifacts: use `lab-builder-hardware-run`.
- Reports, issue cards, blockers, stale evidence, remediation copy, or recheck
  commands: use `lab-builder-report-remediation`.
- External tools, provider CLIs, firmware paths, or Toolchain Readiness: use
  `lab-builder-toolchain`.
- Cross-app comparison between `infra-config-portal` and `lab-builder`: use
  `lab-builder-dual-app-architecture`.
- Skill inventory, skill gaps, or new skill decisions: use this skill.

## Do Not Use This Skill For

- Single-file changes with no Lab Builder context.
- General coding tasks outside this repository family.
- Creating one-off task notes that are better captured in the current report.

## Major Run Report Section

At the end of major runs, add a `Skill Improvement Review` section that states:

- skills used
- skills created or updated
- skill gaps found
- candidate skills deferred
- why no additional skills were created, when applicable
