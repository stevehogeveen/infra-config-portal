# Lab Builder Overnight Handoff - 2026-07-16

## Current State

- Branch: `unified-build-journey`
- Draft PR: [#4 - Build the unified Lab Builder journey](https://github.com/stevehogeveen/infra-config-portal/pull/4)
- Head: `3fb2edb`
- Merge state: clean
- CI: all required Linux and Windows gates pass
- Review state: awaiting Claude/CXO operator-experience approval

## Delivered

### Unified Build Journey

- Operator Home enters one Build Plan with one state-appropriate primary action.
- One workflow engine owns dependency order, run state, waiting, resume, retry, and the
  Completion Report.
- Diagnostics, dependency details, provider results, and raw evidence stay under one
  Advanced disclosure.
- Retired Overview actions now open the relevant device workspace instead of duplicating
  configuration controls.

### Run Reliability

- Guarded evidence is bound to the exact build, kit, profile fingerprint, revision, and
  one-time waiting nonce.
- Concurrent run mutations are serialized, and stale running leases recover to an honest
  retryable failure.
- Required skipped steps cannot satisfy dependencies; explicitly optional skips can.
- Failed guarded results remain failed, persisted result fields are redacted, and latest-run
  recovery is scoped to the selected kit.
- Running states expose refresh, not an invalid Resume action.

### Windows And Compose

- `app/scripts/start-lab-builder.ps1` starts the backend and frontend, waits for health and
  Operator Home, records owned process identity, and supports verified shutdown.
- Windows startup honors explicit, environment, and saved operational-mode precedence.
- Compose performs a clean safe-mock launch with persistent state and same-origin API
  proxying; it does not read `.env.local.real-lab`.
- Clean Python 3.12 Windows and Linux environments install deterministic direct dependencies,
  including pinned Paramiko, Psycopg, and Ruff.

### Repository Hygiene

- Generated dev-server logs and pytest scratch artifacts are no longer tracked and are
  ignored from future commits.
- Password-shaped test data uses an explicit non-secret fixture.
- Linux portability assumptions in cache ordering, workflow paths, and OS-sensitive tests
  are corrected.
- Ruff is required in the backend environment and executes in CI instead of silently
  skipping.

## Verification

Final-head run: [CI 29473409504](https://github.com/stevehogeveen/infra-config-portal/actions/runs/29473409504)

- Linux Make Gate: passed, including fresh Compose launch, 1,089 backend tests with one
  expected platform skip, Ruff, frontend component/build, and portability checks.
- Windows PowerShell Gate: passed, including clean dependencies, Windows doctor, complete
  backend coverage, frontend component/build, and 51 Playwright journeys.
- Windows Fast Verify Gate: passed and uploaded its evidence bundle.
- Alternate local Windows proof: backend health 200, Operator Home 200, same-origin API
  proxy 200, then clean owned-process shutdown.

## Safety Boundary

No RAID apply, factory reset, rebuild, firmware apply, destructive action, or live-hardware
write was invoked or weakened. The resolver, read-only probes, evidence persistence, guarded
workflows, and confirmation gates remain in place.

The iSCSI plan still uses the existing host-side validation action because there is no
guarded ESXi iSCSI datastore apply capability in the repository. The journey reports that
boundary honestly and never claims an unavailable apply action ran.

## Pending CXO Decision

Does the Build Plan, Run Console, and Completion Report meet the one-action Simplicity
Contract well enough to mark draft PR #4 ready for human review, or is one final copy or
layout refinement required?

Do not mark the PR ready or invent another operator surface until this decision is recorded.

## Next Safe Action

1. Claude/CXO reviews the journey and answers the decision above.
2. Codex applies one bounded reversible refinement if requested and reruns focused plus full
   verification.
3. If approved without changes, keep the safety boundary intact and mark the draft ready for
   human review. Merging remains a human action.
