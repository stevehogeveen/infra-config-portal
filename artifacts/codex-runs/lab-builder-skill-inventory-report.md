# Lab Builder Skill Inventory Report

Date: 2026-06-09

Scope:
- Primary repo: `/home/administrator/infra-config-portal`
- Read-only comparison source: `/home/administrator/lab-builder`
- No hardware workflows were run.
- No secrets or local credential values were inspected or printed.

Applied skills for this run:
- `skill-creator`
- `lab-builder-skill-steward`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`
- `lab-builder-ux`
- `lab-builder-real-runtime`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`

## Inspected Inputs

- `.codex/skills/*/SKILL.md`
- `AGENTS.md`
- `.codex/README.md`
- `README.md`
- `app/docs/*`
- `reference/lab-builder-reference.md`

## Existing Skills Before This Run

| Skill | Purpose | Strongest Use |
| --- | --- | --- |
| `lab-builder-real-runtime` | Keeps runtime status honest: source type, freshness, mock-vs-real boundaries, blocker classification, and real-lab gates. | Any status, provider runtime, freshness, real-vs-mock, or current blocker work. |
| `lab-builder-ux` | Guides operator UI structure, sidebar navigation, status colors, Reports placement, and next-action UX. | Visible UI and operator workflow changes. |
| `lab-builder-hardware-run` | Defines discover, plan, apply, verify, report sequencing for hardware tasks and lab profile handling. | Hardware workflow design and artifact-producing provider runs. |
| `lab-builder-report-remediation` | Defines report, issue-card, blocker, evidence, copyable command, and recheck-command contracts. | Report Center, blocker UI, remediation copy, and evidence presentation. |
| `lab-builder-toolchain` | Defines provider tool choices and Toolchain Readiness fields. | Cisco, iLO, ESXi, NetApp, firmware, and external tooling orchestration. |

## Skills Created In This Run

| Skill | Gap Closed |
| --- | --- |
| `lab-builder-skill-steward` | Makes skill inspection and skill selection automatic and defines when new skills are justified. |
| `lab-builder-dual-app-architecture` | Gives future Codex runs a repeatable method for comparing `infra-config-portal` and `lab-builder`. |
| `lab-builder-product-craft` | Captures product quality rules that are broader than layout-only UX: app shell, clutter, next action, mock ambiguity, and operator control. |

## Gaps Found

- Automatic skill loading was implied but not explicit enough in project docs.
- Cross-app comparison rules did not exist as a reusable skill.
- Product craft guidance was split between `lab-builder-ux`, frontend system guidance, and legacy docs, but there was no project skill for the final product feel.
- The legacy app has useful module/stage patterns that future runs should compare deliberately instead of rediscovering.
- Candidate future skills may be useful, but they should wait until repeated work proves they reduce mistakes.

## Overlaps

- `lab-builder-ux` and `lab-builder-product-craft` both apply to UI work. Use `lab-builder-ux` for concrete operator UI mechanics and `lab-builder-product-craft` for coherence, clutter, next-action discipline, and mock-state clarity.
- `lab-builder-real-runtime` and `lab-builder-report-remediation` both touch blockers. Use runtime for source/freshness/current-state logic and report remediation for issue-card structure and fix instructions.
- `lab-builder-hardware-run` and `lab-builder-toolchain` both touch provider work. Use hardware-run for workflow sequencing and artifacts; use toolchain for external tools and readiness checks.
- `lab-builder-dual-app-architecture` should combine with UX, runtime, report, or toolchain skills only when the comparison touches those areas.

## Recommended Automatic Loading Rules

- Before any task, inspect `.codex/skills/`.
- Use the smallest relevant skill set.
- Frontend/UX: `lab-builder-ux` plus `lab-builder-product-craft`.
- Real runtime/status/reporting: `lab-builder-real-runtime`.
- Hardware workflows: `lab-builder-hardware-run`.
- Blocker/report remediation: `lab-builder-report-remediation`.
- External provider tooling: `lab-builder-toolchain`.
- Cross-app synthesis: `lab-builder-dual-app-architecture`.
- Skill upkeep: `lab-builder-skill-steward`.

## Skill Creation Rule

Create or update a skill only when the workflow is reusable, applies to multiple
future tasks, reduces future prompt length or mistakes, captures a recurring
failure mode or product rule, and includes clear when-to-use and do-not-use
guidance.

## Safety Notes

- Mock/test state must never be treated as real lab state.
- Historical artifacts are evidence, not current blockers.
- Skill reports should name applied skills but must not expose credentials,
  tokens, env values, or local secrets.
