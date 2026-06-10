---
name: lab-builder-product-craft
description: Use when improving Lab Builder or Infra Config Portal product quality, visual coherence, app shell, sidebar navigation, list/detail workflows, action-first controls, state language, clutter reduction, mock-state clarity, evidence placement, or operator confidence.
---

# Lab Builder Product Craft

## Use This Skill When

Use this skill for visible UI, product structure, operator copy, information
architecture, page layout, or workflow presentation work.

Use it with `lab-builder-ux` for frontend changes.

## Product Rules

- Keep the app shell simple: sidebar navigation, clear page title, clear active
  lab/runtime context, and one obvious primary action.
- Prefer list/detail layouts for operational work. Use repeated cards only
  when each card is a real item.
- Main pages show minimal reports. Put logs, raw JSON, and evidence behind
  collapsed details or in Reports.
- Every section should expose one next action. Avoid competing primary buttons.
- Use strong state language:
  - Red: current real blocker.
  - Yellow: warning, partial readiness, or stale evidence.
  - Green: ready.
  - Neutral: not checked, not configured, historical, or disabled.
- Never let mock, test, historical, or placeholder data look like current lab
  truth.
- Keep evidence collapsed by default, but make it easy to open from an issue or
  report row.
- The operator should always know what the app knows, what it does not know,
  and what will happen if they press the next action.

## Page Checklist

- Does the page have a single primary operator action?
- Is the current source type visible when status is shown?
- Are blockers separate from warnings and historical evidence?
- Are raw details collapsed or moved to Reports?
- Is the empty state actionable?
- Is the layout scan-friendly at desktop and mobile widths?
- Is there any duplicate status, duplicate report link, or repeated control
  that should become a shared component?
- Are destructive, write, or apply actions visibly gated or disabled?

## Do Not Use This Skill For

- Backend-only refactors with no product-facing contract or copy.
- Low-level provider protocol implementation.
- Creating marketing pages or decorative visuals.
