---
name: lab-builder-dual-app-architecture
description: Use when comparing, migrating, or synthesizing architecture between /home/administrator/infra-config-portal and /home/administrator/lab-builder, including workflows, UI patterns, backend services, hardware orchestration, reports, command structure, reusable modules, and duplicate concepts.
---

# Lab Builder Dual-App Architecture

## Use This Skill When

Use this skill for any task that compares `infra-config-portal` with the
legacy `lab-builder` app or proposes migration between them.

## Safety Boundaries

- Treat `/home/administrator/lab-builder` as read-only unless the user
  explicitly requests edits there.
- Do not run hardware workflows from either app during architecture review.
- Do not print secrets or local credential values.
- Treat historical artifacts as evidence, not current blockers.
- Treat mock and test state as test-only, not real lab state.

## Comparison Workflow

1. Inspect project instructions and applicable Lab Builder skills.
2. Inventory each app separately before synthesizing.
3. Compare by capability, not by file name.
4. Identify which implementation is better for each capability and why.
5. Separate product architecture from migration mechanics.
6. Recommend shared modules only when a real shared abstraction is visible.

## Compare These Areas

- Architecture and app shell shape.
- Workflow model and state transitions.
- UI patterns, navigation, density, and operator next actions.
- Backend service boundaries and route contracts.
- Hardware/device orchestration for iLO, Cisco, ESXi, NetApp, RAID, firmware,
  storage, media, and VM deployment.
- Reports, status state, blockers, evidence, and artifact handling.
- Command and Make/script structure.
- Reusable modules, manifests, registries, and plugin/stage concepts.
- Duplicate concepts that should merge or be discarded.
- Migration opportunities and sequence.

## Output Expectations

When producing a comparison report, include:

- capabilities in each app
- duplicated ideas
- stronger implementation per capability
- what should merge
- what should be discarded
- what should become shared module or service infrastructure
- proposed final product architecture
- proposed UI/navigation architecture
- proposed workflow engine architecture
- proposed reporting/state architecture

Keep recommendations practical. Prefer small migration slices with clear
validation over broad rewrites.

## Do Not Use This Skill For

- Provider-only work that does not touch both apps.
- Frontend polishing that does not require legacy comparison.
- Running or validating live hardware workflows.
