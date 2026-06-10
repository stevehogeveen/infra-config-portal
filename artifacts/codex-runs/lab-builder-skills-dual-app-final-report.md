# Lab Builder Skills Dual-App Final Report

Date: 2026-06-09

Scope:
- Primary repo: `/home/administrator/infra-config-portal`
- Read-only reference: `/home/administrator/lab-builder`
- No hardware workflows were run.
- No secrets, tokens, credentials, env contents, or local credential values were
  printed.
- Mock/test state was not treated as real lab state.
- Historical artifacts were treated as evidence, not current blockers.

## Skills Created

Created:
- `.codex/skills/lab-builder-skill-steward/SKILL.md`
- `.codex/skills/lab-builder-dual-app-architecture/SKILL.md`
- `.codex/skills/lab-builder-product-craft/SKILL.md`

Purpose:
- `lab-builder-skill-steward`: automatic skill inspection, selection, creation criteria, and skill improvement review rules.
- `lab-builder-dual-app-architecture`: repeatable comparison method for `infra-config-portal` and `lab-builder`.
- `lab-builder-product-craft`: product polish rules for app shell, navigation, action-first pages, state language, clutter reduction, mock clarity, and collapsed evidence.

## AGENTS.md Changes

Updated `AGENTS.md` to require:
- inspecting `.codex/skills/` before any task
- automatic use of relevant Lab Builder skills
- frontend/UX loading of `lab-builder-ux` and `lab-builder-product-craft`
- runtime/status loading of `lab-builder-real-runtime`
- hardware workflow loading of `lab-builder-hardware-run`
- blocker/report loading of `lab-builder-report-remediation`
- external tooling loading of `lab-builder-toolchain`
- cross-app synthesis loading of `lab-builder-dual-app-architecture`
- skill upkeep loading of `lab-builder-skill-steward`
- mock/test state never being treated as real lab state
- historical artifacts being evidence, not current blockers

## .codex README Changes

Updated `.codex/README.md` to explain:
- the complete skill list
- when to use each skill
- automatic loading rules
- how to ask Codex to use a skill explicitly
- how new skills are proposed or created
- the rule that promising but unproven patterns should be reported as
  candidates instead of becoming unnecessary skills

## Reports Written

Created:
- `artifacts/codex-runs/lab-builder-skill-inventory-report.md`
- `artifacts/codex-runs/infra-config-portal-app-atlas.md`
- `artifacts/codex-runs/lab-builder-app-atlas.md`
- `artifacts/codex-runs/dual-app-synthesis-report.md`
- `artifacts/codex-runs/lab-builder-skill-candidates.md`
- `artifacts/codex-runs/lab-builder-skills-dual-app-final-report.md`

## Infra Config Portal Summary

`infra-config-portal` is the right long-term control plane. It already has:
- FastAPI routes, Pydantic schemas, SQLAlchemy models, and Alembic migrations.
- Request lifecycle, workflow runs, approvals, audit events, and mock VM deploy flow.
- Provider adapters and local provider status for iLO, Cisco, ESXi, NetApp, and mocks.
- Build Verification, Report Center, Control Center, lab profiles, firmware, NetApp state, RAID, ESXi, Cisco, and iLO services.
- React sidebar shell with Dashboard, Run Center, Control, Firmware, Verification, Reports, Settings, requests, lab profiles, providers, audit, artifacts, and media flows.
- Strong source/freshness/status semantics and explicit mock-vs-real boundaries.

Main concerns:
- `app/frontend/src/App.tsx` is too large and should be split by route and provider module.
- `app/backend/app/api/routes.py` and `app/backend/app/schemas.py` are broad central files.
- Provider actions, Make targets, scripts, Control Center actions, and Run Center choices should converge into a workflow/action registry.
- Historical artifacts need an indexed current/stale/historical/test view so filenames do not imply current state.

## Lab Builder Summary

`/home/administrator/lab-builder` exists and was inspected read-only. It is an
active, dirty worktree and was not modified.

Strong reusable ideas:
- Module manifests with navigation and discover/plan/validate/preview/apply/status/repair capabilities.
- Stage plugin model.
- Run Center live job, progress, stage checklist, and technical log drawers.
- Product shell with kit state, readiness meter, Open Issues, Suggestions, and recommended next step.
- Automation principles around intent, live discovery, safe auto-remediation, block decisions, and diagnostic logs.
- UI/code audit scripts and duplicate function checks.
- Debug bundles and run summaries tied to kit/job/stage context.

Do not port directly:
- Large central `app/main.py` growth.
- Dense templates without component boundaries.
- Real hardware execution paths without portal source/freshness, approval, and safety gates.
- Artifact volume without a current-state index.

## Synthesis Summary

Recommended final direction:
- Keep `infra-config-portal` as the final product/control plane.
- Treat `lab-builder` as the product and workflow reference.
- Move useful legacy ideas into the portal as typed, gated, testable services.

Best merge candidates:
- Lab Builder module/stage manifests -> portal workflow/action registry.
- Lab Builder Run Center live job model -> portal run trace and stage checklist.
- Portal status source/freshness contract -> all current state and imported hardware evidence.
- Portal Report Center blocker contract -> all issue cards and remediation flows.
- Lab Builder setup strip, action feedback banner, Open Issues drawer, and suggestion center -> portal shared UI components.

## Skill Candidates

No extra skills were created. Deferred candidates are listed in
`artifacts/codex-runs/lab-builder-skill-candidates.md`:
- `lab-builder-state-model`
- `lab-builder-action-catalog`
- `lab-builder-visual-design-system`
- `lab-builder-test-strategy`
- `lab-builder-netapp-ontap`
- `lab-builder-esxi-kickstart`
- `lab-builder-cisco-network`
- `lab-builder-firmware-upgrades`

Reason for deferral:
- The new three skills plus the existing five project skills cover the current
  run.
- Extra provider-specific skills should wait until implementation work proves a
  recurring failure mode.

## Validation

Safe checks run:
- `git diff --check -- AGENTS.md .codex/README.md`
- `grep -n '[[:blank:]]$'` on the new skills and new reports
- `LC_ALL=C grep -n '[^ -~]'` on the new skills and new reports
- frontmatter spot check for the three new skills
- `wc -l` for the three new skills and five report files written before this final report

Result:
- Passed.
- No frontend build, backend tests, or hardware checks were run because this
  pass changed docs, skills, and reports only.

## Skill Improvement Review

Skills used:
- `skill-creator`
- `lab-builder-skill-steward`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`
- `lab-builder-ux`
- `lab-builder-real-runtime`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`

Skills created:
- `lab-builder-skill-steward`
- `lab-builder-dual-app-architecture`
- `lab-builder-product-craft`

Skills updated:
- None.

Skill gaps found:
- State model, action catalog, visual design system, test strategy, and
  provider-domain skills may become worthwhile later.

Candidate skills deferred:
- All candidate skills listed above.

Why no additional skills were created:
- The candidate patterns are real, but this run did not perform repeated
  implementation work that proves a new skill would reduce mistakes beyond the
  existing and newly created skills.

## Next Recommended Big Run

Run a workflow/action-registry implementation pass in `infra-config-portal`.

Proposed scope:
1. Create a backend workflow/action registry that absorbs the current Control Center action definitions and maps stages to discover, plan, apply, verify, report, required gates, commands, and reports.
2. Add a run trace/stage event contract inspired by Lab Builder jobs.
3. Make Run Center consume the registry for provider sections instead of hard-coded build choices.
4. Start frontend extraction by splitting `App.tsx` into route modules and shared components for status summary, issue cards, evidence drawers, setup strips, action panels, and run checklists.
5. Keep all real hardware actions disabled or guarded exactly as today.
