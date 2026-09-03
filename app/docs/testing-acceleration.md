# Testing Acceleration Plan

This app should move fast without watering down the safety model. Use a tiered test strategy:

1. Fast lane while building
   - Run `.\scripts\fast-verify.ps1` from `app/` on Windows.
   - It reads the current git diff and chooses the cheapest useful checks.
   - Frontend changes run `npm run test:component`, a fast server-render component lane for shared UI atoms and pure rendering contracts.
   - Topology/composer changes run frontend build, focused Overview Design Playwright tests, and focused topology draft API tests.
   - Windows helper script or Makefile changes run `backend/tests/test_windows_scripts.py` so local launcher and verification scripts stay parseable and portable.
   - Use `.\scripts\fast-verify.ps1 -WhatIfOnly` to see the planned checks without running them.
   - Executed runs write `artifacts/codex-runs/fast-verify-plan.json` with the changed files, selected steps, per-step routing reasons, command families, and safety notes, so the compact-test decision is inspectable after the fact.
   - Validate the saved plan artifact with `.\scripts\fast-verify.ps1 -ValidatePlan`; validation rejects missing step details and unsafe command families.
   - If a step fails, fast-verify automatically creates a redacted advisory QA failure packet. Pass `-NoFailurePacket` only when you deliberately want raw failure output without packet generation.
   - API route, schema, workflow registry, and workflow allowlist changes run `cd backend && .\.venv\Scripts\python.exe scripts\openapi_contract_probe.py` plus `backend/tests/test_openapi_contract_probe.py`. The probe generates cases from FastAPI OpenAPI and registry metadata, then validates endpoint wiring and guarded-action metadata without calling API endpoints.

2. Full gate before handoff, PR, or deployment
   - Frontend: `cd frontend && npm run build && npm run test:e2e`
   - Backend API: `cd backend && .\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`
   - Real-lab scripts remain explicit operator actions and must stay behind their existing guards.
   - GitHub Actions mirrors this asynchronously: Linux runs `make test`/`make lint`; Windows runs `check-windows.ps1 -E2E`; a dedicated Windows fast-verify job runs `.\scripts\fast-verify.ps1 -Full`.
   - CI uploads `artifacts/codex-runs`, Playwright results, the fast-verify plan, and any redacted QA failure packets so failures can be diagnosed without rerunning the job locally first.
   - Validate all local QA artifact contracts together with `.\scripts\qa-artifact-health.ps1`. Add `-GenerateMissingPlans` when you only need dry-run plan artifacts; it does not run tests, workflow actions, provider probes, hardware commands, or external AI calls.
   - Generate and validate the QA capability audit with `cd backend && .\.venv\Scripts\python.exe scripts\qa_capability_audit.py`. This produces `artifacts/codex-runs/qa-capability-audit.json`, a marker-based proof that the tiered fast lane, hardware lane, component lane, generated tests, visual regression, CI gates, advisory triage, artifact health, and guarded-execution safety evidence are all present.
   - `.\scripts\qa-artifact-health.ps1 -GenerateMissingPlans` also refreshes the capability audit without running tests, workflow actions, provider probes, hardware commands, or external AI calls.

3. Hardware lane on demand
   - Run `.\scripts\hardware-smoke.ps1 -WhatIfOnly` from `app/` to preview real-lab smoke commands without touching hardware.
   - The preview writes `artifacts/codex-runs/hardware-smoke-plan.json` with schema `hardware-smoke-plan/v1`, selected providers, intended steps, and safety notes.
   - Validate the saved hardware plan with `.\scripts\hardware-smoke.ps1 -ValidatePlan`; validation rejects missing step commands and unsafe command families.
   - Run `.\scripts\hardware-smoke.ps1 -AcknowledgeReadOnly` for the default `local-readonly` provider smoke lane after confirming the lab is safe to probe.
   - Add `-Providers ilo-redfish` or another provider list to narrow the run while debugging one device family.
   - Add `-IncludeOperatorSweep` only when you want the broader read-only workflow-action sweep and current evidence quality gate.
   - `local-lab-readwrite` mode is refused unless `-AllowWriteMode` is present. Prefer `local-readonly` for smoke verification; write/destructive workflows stay behind their own exact gates.

4. Keep browser tests scarce and meaningful
   - Playwright should prove navigation, persistence round trips, guarded-run refusals, and visual layout health.
   - Use `frontend/src/**/*.component.test.tsx` for shared component rendering, labels, classes, table semantics, and fallback states that do not require a browser.
   - Do not add browser tests for simple text mapping or pure data transformations when backend/unit/component tests can cover them faster.

5. Add generated and property tests where the app has many valid combinations
   - Good targets: topology draft normalization, subnet/address derivation, storage protocol choices, profile feature resolution, and reset/rebuild guard logic.
   - Property examples: derived IPs stay inside the subnet; draft-only topology edits never mark `hardware_touched`; single-server scenarios cannot persist NetApp as required hardware.
   - Current first slice: `backend/tests/test_topology_design_drafts.py` uses generated scenario/subnet matrices to cover topology draft defaults, malformed placement normalization, lane/connection settings, and draft-only persistence without adding browser tests.
   - Current API-contract slice: `backend/scripts/openapi_contract_probe.py` derives registry endpoint cases from OpenAPI and writes `artifacts/codex-runs/openapi-contract-probe.json`, catching stale workflow action links and missing guard metadata before they become dead buttons.
   - Keep this style for pure logic: generate a compact matrix, assert invariants once, and reserve Playwright for flows that need a browser or reload round trip.

6. Add visual regression for the design surface
   - The topology canvas, rack faceplates, and device editor are visual product surfaces.
   - Use Playwright screenshot assertions once the design stabilizes so desktop/mobile overflow and faceplate regressions are caught automatically.
   - Current first slice: the Overview design-mode blueprint has a committed Playwright locator screenshot. Update it intentionally with `cd frontend && npm run test:e2e -- -g "overview design mode visual blueprint" --update-snapshots` after reviewing the visual change.
   - Keep snapshots focused on stable product surfaces, not the whole page, so the signal stays high.

7. AI-assisted triage, advisory only
   - Run `.\scripts\qa-failure-packet.ps1 -Note "what you saw"` after a failing pytest, Playwright, workflow, or hardware-smoke run.
   - `.\scripts\fast-verify.ps1` also creates this packet automatically when one of its selected steps fails.
   - The packet generator collects recent pytest cache, Playwright failure context, workflow run traces, and hardware-smoke JSON, redacts it, and writes `artifacts/codex-runs/qa-failure-packets/latest.json` plus `.md`.
   - Packets include versioned `schema_version` and `advisory_triage` with evidence kinds, probable area, a safe verification command, suggested focus, and explicitly excluded unsafe action categories.
   - Validate the latest packet contract with `.\scripts\qa-failure-packet.ps1 -ValidateLatest`; validation rejects malformed schema metadata and unsafe suggested commands.
   - The generated prompt is AI-ready, but the script does not call any external AI/API and does not execute tests or hardware actions.
   - Future slice: feed these redacted packets into an optional AI diagnosis service.
   - Output must be labeled advisory, validated into existing blocker/next-action vocabulary, and restricted to safe/read-only suggested actions.
   - The diagnosis service must not import or call workflow runners.

8. AI-assisted product features, same safety contract
   - Useful future features: run failure diagnosis cards, handoff narrative generation, chat-with-your-lab over read-only endpoints, and composer copilot that drafts canvas intent only.
   - AI may draft intent. Humans still commit profiles and run guarded applies.

The guiding rule: fast checks during construction, full checks at gates, and AI only as a redacted advisory layer unless a human explicitly commits through the existing guarded UI.
