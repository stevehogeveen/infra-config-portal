# Lab Builder Skill Candidates

Date: 2026-06-09

Scope:
- Skill review after inspecting `infra-config-portal` and GitHub `stevehogeveen/lab-builder`.
- No files were modified in `/home/administrator/lab-builder`.
- No hardware workflows were run.
- Mock/test/historical state was not treated as current real lab state.
- No new skill was created in this run.

Applied skills:
- `lab-builder-real-runtime`
- `lab-builder-ux`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`
- `lab-builder-skill-steward`

## Decision

Do not create or update skills during this synthesis run.

Reason:
- The existing skill set already covers the main recurring mistakes: mock-as-real, stale evidence as current blockers, unsafe hardware workflows, poor operator issue presentation, toolchain readiness, UI clutter, and cross-app synthesis.
- New skills would be speculative until implementation runs reveal repeated failure patterns.
- The next work should produce code and test evidence first, then turn recurring rules into smaller targeted skills.

## Existing Skill Coverage

| Skill | Keep | Coverage |
| --- | --- | --- |
| `lab-builder-real-runtime` | Yes | Source type, freshness, provider runtime state, live-vs-mock boundaries, `local-lab-readwrite` gates. |
| `lab-builder-ux` | Yes | Navigation, setup pages, status colors, Reports, evidence/raw JSON placement, next actions. |
| `lab-builder-hardware-run` | Yes | Discover-plan-apply-verify-report sequencing, lab profiles, console discovery, run artifacts. |
| `lab-builder-report-remediation` | Yes | Issue cards, stale warnings, evidence links, fix/recheck commands. |
| `lab-builder-toolchain` | Yes | External tool readiness and provider-specific tooling. |
| `lab-builder-dual-app-architecture` | Yes | Comparing and synthesizing current app and old Lab Builder. |
| `lab-builder-product-craft` | Yes | Product polish, action-first layout, mock-state clarity, operator confidence. |
| `lab-builder-skill-steward` | Yes | Skill selection and criteria for future skill creation. |

## Candidate Skills

| Candidate | Priority | Create When | Do Not Create Yet Because |
| --- | --- | --- | --- |
| `lab-builder-state-model` | High | Multiple implementation runs touch `source_type`, `freshness`, runtime observations, provider runtime records, historical artifact rules, or DB migrations. | `lab-builder-real-runtime` and `lab-builder-report-remediation` already cover the current rules. |
| `lab-builder-action-catalog` | High | Action/stage metadata becomes a shared implementation across Lab Setup, Control Center, Run Center, and Reports. | The future Action Catalog contract is proposed but not implemented yet. |
| `lab-builder-test-strategy` | Medium | Workflow engine, stage registry, report classification, and frontend states become recurring test design work. | Current backend tests are broad, and test gaps are clearer after workflow substrate work begins. |
| `lab-builder-visual-design-system` | Medium | Shared React components and screenshot validation become repeated UI work. | `lab-builder-ux` and `lab-builder-product-craft` are sufficient until components exist. |
| `lab-builder-netapp-ontap` | Medium | NetApp work moves beyond readiness/preview into deeper ONTAP planning, adaptive discovery, or guarded execution. | Current NetApp posture should stay preview/readiness focused until workflow gates are implemented. |
| `lab-builder-esxi-kickstart` | Medium | ESXi work repeatedly touches kickstart generation, ISO build, virtual media, boot override, and management validation. | Current ESXi work is not yet a unified executable stage workflow. |
| `lab-builder-cisco-network` | Medium | Cisco console, SSH, VLAN, bootstrap, config diff, and recovery workflows become repeated work. | Current Cisco safety is covered by hardware-run, toolchain, UX, and report skills. |
| `lab-builder-firmware-upgrades` | Medium | Firmware baseline, package inventory, waiver, guarded upgrade, rollback, and verification work repeats. | Current firmware upgrade execution is not yet active enough to justify a dedicated skill. |

## Recommended Skill Updates Later

After the workflow substrate implementation, revisit:
- `lab-builder-real-runtime`: add exact new model names and source-state invariants.
- `lab-builder-hardware-run`: add the final stage registry contract.
- `lab-builder-report-remediation`: add the final issue/run/evidence linkage contract.
- `lab-builder-ux`: add final Lab Setup and Run Center component rules.
- `lab-builder-toolchain`: add concrete tool requirement schema once implemented.

## Skill Improvement Review

This run did not reveal a missing skill that would clearly reduce mistakes immediately. It did reveal two likely future high-value skills:
- `lab-builder-state-model`
- `lab-builder-action-catalog`

Create them only after the first implementation run makes the actual contracts concrete.
